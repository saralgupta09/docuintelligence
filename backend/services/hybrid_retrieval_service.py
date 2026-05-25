"""
services/hybrid_retrieval_service.py
--------------------------------------
Runs vector search and BM25 search in parallel, normalises both score
distributions to [0, 1], then merges them using configurable weights.

Hybrid score formula:
    hybrid_score = SEMANTIC_WEIGHT * vector_sim + BM25_WEIGHT * bm25_norm

where:
  vector_sim  = 1 - cosine_distance   (ChromaDB returns distances, not sims)
  bm25_norm   = bm25_score / max_bm25_score   (linear normalisation)

Both weights are configured in config.py / .env.
Default: SEMANTIC_WEIGHT=0.6, BM25_WEIGHT=0.4.

Fallback behaviour:
  - If BM25 index is empty (ChromaDB was just reset, or build failed):
    the node falls back to vector-only results (bm25_weight contribution = 0).
  - If ChromaDB is empty: returns [] immediately, no BM25 call made.

This service REPLACES RetrievalService inside the retrieve node.
RetrievalService itself is unchanged — it's still used as the vector backend.
"""

from typing import List, Dict, Tuple, Optional

from config import settings
from services.retrieval_service import RetrievalService, RetrievalResult
from services.bm25_service import get_bm25_service, BM25Document
from services.embedding_service import get_embedding_service
from services.vector_store import get_vector_store_service
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


class HybridRetrievalResult:
    """
    One result from the hybrid retrieval pipeline.

    Carries both the original score components and the final merged score,
    which enables debugging and future reranking.
    """

    def __init__(
        self,
        chunk_id: str,
        text: str,
        filename: str,
        page_num: int,
        doc_id: str,
        metadata: dict,
        vector_score: float,    # Normalised to [0, 1]; higher = more similar
        bm25_score: float,      # Normalised to [0, 1]; higher = more relevant
        combined_score: float,  # Weighted sum of vector_score + bm25_score
    ) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.filename = filename
        self.page_num = page_num
        self.doc_id = doc_id
        self.metadata = metadata
        self.vector_score = vector_score
        self.bm25_score = bm25_score
        self.combined_score = combined_score

        # Aliases kept for compatibility with the retrieve node
        # (which checks result.distance on RetrievalResult objects)
        self.distance = 1.0 - vector_score  # Re-derive distance from similarity

    def excerpt(self, max_chars: int = 200) -> str:
        """Short preview of the chunk text."""
        if len(self.text) <= max_chars:
            return self.text
        return self.text[:max_chars].rstrip() + "..."

    def __repr__(self) -> str:
        return (
            f"HybridResult(file={self.filename}, page={self.page_num}, "
            f"combined={self.combined_score:.4f}, "
            f"vec={self.vector_score:.4f}, bm25={self.bm25_score:.4f})"
        )


class HybridRetrievalService:
    """
    Merges vector and BM25 search results into a single ranked list.

    Parameters:
        vector_top_k:     How many candidates to fetch from ChromaDB.
        bm25_top_k:       How many candidates to score via BM25.
        semantic_weight:  Weight for vector similarity component.
        bm25_weight:      Weight for BM25 score component.
        final_top_k:      How many results to return after merging.
    """

    def __init__(
        self,
        vector_top_k: int = 10,
        bm25_top_k: int = 10,
        semantic_weight: float = 0.6,
        bm25_weight: float = 0.4,
        final_top_k: int = 5,
    ) -> None:
        self.vector_top_k = vector_top_k
        self.bm25_top_k = bm25_top_k
        self.semantic_weight = semantic_weight
        self.bm25_weight = bm25_weight
        self.final_top_k = final_top_k

    def retrieve(self, query: str) -> List[HybridRetrievalResult]:
        """
        Runs hybrid retrieval: vector search + BM25, then merges.

        Args:
            query: The retrieval query (may differ from the original user
                   question if query rewriting is enabled).

        Returns:
            Up to final_top_k HybridRetrievalResult objects, sorted by
            combined_score descending.
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")

        logger.info(
            "Hybrid retrieval started",
            extra={
                "query_preview": query[:80],
                "vector_top_k": self.vector_top_k,
                "bm25_top_k": self.bm25_top_k,
                "semantic_weight": self.semantic_weight,
                "bm25_weight": self.bm25_weight,
            },
        )

        # ── Verify ChromaDB has documents ─────────────────────────────────────
        vector_store = get_vector_store_service()
        stats = vector_store.get_collection_stats()
        total_chunks = stats.get("total_chunks", 0)

        if total_chunks == 0:
            logger.warning("ChromaDB is empty — hybrid retrieval returning []")
            return []

        # ── 1. Vector search ──────────────────────────────────────────────────
        with Timer() as vec_timer:
            vector_results = self._run_vector_search(query, total_chunks)

        logger.info(
            "Vector search complete",
            extra={"results": len(vector_results), "elapsed_ms": vec_timer.elapsed_ms},
        )

        # ── 2. BM25 search ────────────────────────────────────────────────────
        with Timer() as bm25_timer:
            bm25_results = self._run_bm25_search(query)

        logger.info(
            "BM25 search complete",
            extra={"results": len(bm25_results), "elapsed_ms": bm25_timer.elapsed_ms},
        )

        # ── 3. Merge and rank ─────────────────────────────────────────────────
        with Timer() as merge_timer:
            merged = self._merge(vector_results, bm25_results)

        logger.info(
            "Hybrid merge complete",
            extra={
                "merged_pool": len(vector_results) + len(bm25_results),
                "unique_after_merge": len(merged),
                "final_top_k": self.final_top_k,
                "elapsed_ms": merge_timer.elapsed_ms,
                "top_score": round(merged[0].combined_score, 4) if merged else None,
            },
        )

        return merged[: self.final_top_k]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _run_vector_search(
        self, query: str, total_chunks: int
    ) -> List[RetrievalResult]:
        """Embeds the query and queries ChromaDB."""
        effective_k = min(self.vector_top_k, total_chunks)
        embedding_service = get_embedding_service()
        query_embedding = embedding_service.embed_query(query)

        vector_store = get_vector_store_service()
        collection = vector_store._get_collection()
        raw = collection.query(
            query_embeddings=[query_embedding],
            n_results=effective_k,
            include=["documents", "metadatas", "distances"],
        )

        ids = raw["ids"][0]
        texts = raw["documents"][0]
        metadatas = raw["metadatas"][0]
        distances = raw["distances"][0]

        results: List[RetrievalResult] = []
        for chunk_id, text, metadata, distance in zip(ids, texts, metadatas, distances):
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    text=text,
                    filename=metadata.get("filename", "unknown"),
                    page_num=int(metadata.get("page_num", 0)),
                    doc_id=metadata.get("doc_id", "unknown"),
                    distance=float(distance),
                    metadata=metadata,
                )
            )
        return results

    def _run_bm25_search(
        self, query: str
    ) -> List[Tuple[BM25Document, float]]:
        """Returns BM25 top-k as (doc, raw_score) tuples."""
        bm25_service = get_bm25_service()
        return bm25_service.search(query, top_k=self.bm25_top_k)

    def _merge(
        self,
        vector_results: List[RetrievalResult],
        bm25_results: List[Tuple[BM25Document, float]],
    ) -> List[HybridRetrievalResult]:
        """
        Normalises both score distributions and computes the hybrid score.

        Normalisation:
          vector: similarity = 1 - distance  (ChromaDB cosine distances ∈ [0, 2])
                  sim clamped to [0, 1], then normalised by max sim in the pool
          bm25:   raw score / max raw score  (linear, also [0, 1])

        Documents that appear in only one list get 0.0 for the missing component.
        This is intentional — a document found by both methods is ranked higher.
        """
        # Build lookup: chunk_id → (vector_similarity, RetrievalResult)
        vec_map: Dict[str, Tuple[float, RetrievalResult]] = {}
        for r in vector_results:
            # cosine distance ∈ [0, 2]; similarity = 1 - distance, clamped
            sim = max(0.0, min(1.0, 1.0 - r.distance))
            vec_map[r.chunk_id] = (sim, r)

        # Build lookup: chunk_id → (raw_bm25_score, BM25Document)
        bm25_map: Dict[str, Tuple[float, BM25Document]] = {}
        for doc, score in bm25_results:
            bm25_map[doc.chunk_id] = (score, doc)

        # Normalise vector similarities to [0, 1]
        if vec_map:
            max_vec = max(sim for sim, _ in vec_map.values()) or 1.0
        else:
            max_vec = 1.0
        vec_norm: Dict[str, float] = {
            cid: sim / max_vec for cid, (sim, _) in vec_map.items()
        }

        # Normalise BM25 raw scores to [0, 1]
        if bm25_map:
            max_bm25 = max(score for score, _ in bm25_map.values()) or 1.0
        else:
            max_bm25 = 1.0
        bm25_norm: Dict[str, float] = {
            cid: score / max_bm25 for cid, (score, _) in bm25_map.items()
        }

        # Union of all chunk_ids seen in either list
        all_ids = set(vec_map.keys()) | set(bm25_map.keys())

        merged: List[HybridRetrievalResult] = []
        for chunk_id in all_ids:
            v_score = vec_norm.get(chunk_id, 0.0)
            b_score = bm25_norm.get(chunk_id, 0.0)
            combined = self.semantic_weight * v_score + self.bm25_weight * b_score

            # Prefer the RetrievalResult for metadata (it has the page_num, etc.)
            # Fall back to BM25Document if this chunk was only found by BM25
            if chunk_id in vec_map:
                _, source = vec_map[chunk_id]
                metadata = source.metadata
                filename = source.filename
                page_num = source.page_num
                doc_id = source.doc_id
                text = source.text
            else:
                _, source = bm25_map[chunk_id]  # type: ignore[assignment]
                metadata = source.metadata
                filename = source.filename
                page_num = source.page_num
                doc_id = source.doc_id
                text = source.text

            merged.append(
                HybridRetrievalResult(
                    chunk_id=chunk_id,
                    text=text,
                    filename=filename,
                    page_num=page_num,
                    doc_id=doc_id,
                    metadata=metadata,
                    vector_score=v_score,
                    bm25_score=b_score,
                    combined_score=combined,
                )
            )

        # Sort by combined score descending
        merged.sort(key=lambda r: r.combined_score, reverse=True)
        return merged


# ── Singleton ─────────────────────────────────────────────────────────────────
_hybrid_retrieval_service: Optional[HybridRetrievalService] = None


def get_hybrid_retrieval_service() -> HybridRetrievalService:
    """Returns the shared HybridRetrievalService instance."""
    global _hybrid_retrieval_service
    if _hybrid_retrieval_service is None:
        _hybrid_retrieval_service = HybridRetrievalService(
            vector_top_k=settings.VECTOR_TOP_K,
            bm25_top_k=settings.BM25_TOP_K,
            semantic_weight=settings.SEMANTIC_WEIGHT,
            bm25_weight=settings.BM25_WEIGHT,
            final_top_k=settings.RETRIEVAL_TOP_K,
        )
    return _hybrid_retrieval_service
