"""
services/hybrid_retrieval_service.py
--------------------------------------
Runs vector search and BM25 search in parallel, normalises both score
distributions to [0, 1], then merges them using configurable weights.

Feature 1 change: retrieve() accepts an optional doc_id parameter.
  - Vector search: passes where={"doc_id": {"$eq": doc_id}} to ChromaDB
    when doc_id is provided. ChromaDB filters before scoring.
  - BM25 search: results are post-filtered to the same doc_id.
  - When doc_id is None (default), both searches run unfiltered.
    This is the existing behaviour — zero regression.

The scoring formula, normalisation, merge logic, and all other code
are completely unchanged.
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
    Unchanged from Phase 3.
    """

    def __init__(
        self,
        chunk_id: str,
        text: str,
        filename: str,
        page_num: int,
        doc_id: str,
        metadata: dict,
        vector_score: float,
        bm25_score: float,
        combined_score: float,
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
        self.distance = 1.0 - vector_score

    def excerpt(self, max_chars: int = 200) -> str:
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

    def retrieve(
        self,
        query: str,
        doc_id: Optional[str] = None,       # Feature 1: None = all docs
    ) -> List[HybridRetrievalResult]:
        """
        Runs hybrid retrieval: vector search + BM25, then merges.

        Args:
            query:  The retrieval query.
            doc_id: When provided, only chunks from this document are searched.
                    None (default) searches all documents.
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")

        logger.info(
            "Hybrid retrieval started",
            extra={
                "query_preview": query[:80],
                "doc_id_filter": doc_id or "all",
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
            vector_results = self._run_vector_search(query, total_chunks, doc_id)

        logger.info(
            "Vector search complete",
            extra={"results": len(vector_results), "elapsed_ms": vec_timer.elapsed_ms},
        )

        # ── 2. BM25 search ────────────────────────────────────────────────────
        with Timer() as bm25_timer:
            bm25_results = self._run_bm25_search(query, doc_id)

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
        self,
        query: str,
        total_chunks: int,
        doc_id: Optional[str] = None,       # Feature 1
    ) -> List[RetrievalResult]:
        """
        Embeds the query and queries ChromaDB.

        Feature 1: when doc_id is provided, adds a ChromaDB 'where' filter
        so only chunks from that document are considered. ChromaDB applies
        the filter before the HNSW search, so the n_results cap is relative
        to the filtered set.
        """
        effective_k = min(self.vector_top_k, total_chunks)
        embedding_service = get_embedding_service()
        query_embedding = embedding_service.embed_query(query)

        vector_store = get_vector_store_service()
        collection = vector_store._get_collection()

        # Build query kwargs — only add 'where' when filtering
        query_kwargs = dict(
            query_embeddings=[query_embedding],
            n_results=effective_k,
            include=["documents", "metadatas", "distances"],
        )
        if doc_id:
            query_kwargs["where"] = {"doc_id": {"$eq": doc_id}}

        raw = collection.query(**query_kwargs)

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
        self,
        query: str,
        doc_id: Optional[str] = None,       # Feature 1
    ) -> List[Tuple[BM25Document, float]]:
        """
        Returns BM25 top-k as (doc, raw_score) tuples.

        Feature 1: when doc_id is provided, post-filters the BM25 results
        to only include chunks from that document. Post-filtering is correct
        here because BM25 scores every document in its index in O(N) regardless
        — there's no cheaper pre-filter available without rebuilding per-doc
        indexes, which is unnecessary complexity at this scale.
        """
        bm25_service = get_bm25_service()
        results = bm25_service.search(query, top_k=self.bm25_top_k)

        if doc_id:
            results = [(doc, score) for doc, score in results if doc.doc_id == doc_id]

        return results

    def _merge(
        self,
        vector_results: List[RetrievalResult],
        bm25_results: List[Tuple[BM25Document, float]],
    ) -> List[HybridRetrievalResult]:
        """
        Normalises both score distributions and computes the hybrid score.
        Completely unchanged from Phase 3.
        """
        # Build lookup: chunk_id → (vector_similarity, RetrievalResult)
        vec_map: Dict[str, Tuple[float, RetrievalResult]] = {}
        for r in vector_results:
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

            if chunk_id in vec_map:
                _, source = vec_map[chunk_id]
                metadata = source.metadata
                filename = source.filename
                page_num = source.page_num
                doc_id_val = source.doc_id
                text = source.text
            else:
                _, source = bm25_map[chunk_id]  # type: ignore[assignment]
                metadata = source.metadata
                filename = source.filename
                page_num = source.page_num
                doc_id_val = source.doc_id
                text = source.text

            merged.append(
                HybridRetrievalResult(
                    chunk_id=chunk_id,
                    text=text,
                    filename=filename,
                    page_num=page_num,
                    doc_id=doc_id_val,
                    metadata=metadata,
                    vector_score=v_score,
                    bm25_score=b_score,
                    combined_score=combined,
                )
            )

        merged.sort(key=lambda r: r.combined_score, reverse=True)
        return merged


# ── Singleton ─────────────────────────────────────────────────────────────────
_hybrid_retrieval_service: Optional[HybridRetrievalService] = None


def get_hybrid_retrieval_service() -> HybridRetrievalService:
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
