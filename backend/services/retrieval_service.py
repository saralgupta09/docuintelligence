"""
services/retrieval_service.py
------------------------------
Handles semantic similarity search against ChromaDB.

Flow:
  1. Embed the question using BGE-small (same model as ingestion)
  2. Query ChromaDB with the embedded vector
  3. Return top-k matching chunks with metadata

The same embedding model MUST be used at ingestion AND retrieval.
Mixing models produces meaningless similarity scores.
"""

from typing import List, Dict, Any

from config import settings
from services.embedding_service import get_embedding_service
from services.vector_store import get_vector_store_service
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


class RetrievalResult:
    """Represents one retrieved chunk from ChromaDB."""

    def __init__(
        self,
        chunk_id: str,
        text: str,
        filename: str,
        page_num: int,
        doc_id: str,
        distance: float,
        metadata: Dict[str, Any],
        combined_score: float = 0.0,    # Phase 3: populated by HybridRetrievalService
    ) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.filename = filename
        self.page_num = page_num
        self.doc_id = doc_id
        self.distance = distance          # Lower = more similar (cosine space)
        self.metadata = metadata
        self.combined_score = combined_score  # 0.0 when used without hybrid service

    def excerpt(self, max_chars: int = 200) -> str:
        """Short preview of the chunk text."""
        if len(self.text) <= max_chars:
            return self.text
        return self.text[:max_chars].rstrip() + "..."

    def __repr__(self) -> str:
        return (
            f"RetrievalResult(file={self.filename}, page={self.page_num}, "
            f"dist={self.distance:.4f}, chars={len(self.text)})"
        )


class RetrievalService:
    """Embeds questions and searches ChromaDB for relevant chunks."""

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def retrieve(self, question: str) -> List[RetrievalResult]:
        """
        Embeds the question and returns the top-k most similar chunks.

        Returns:
            List of RetrievalResult, ordered by relevance (closest first).
            Returns empty list if ChromaDB has no documents.
        """
        if not question.strip():
            raise ValueError("Question cannot be empty")

        logger.info(
            "Starting retrieval",
            extra={"question_preview": question[:80], "top_k": self.top_k},
        )

        # Check collection has documents
        vector_store = get_vector_store_service()
        stats = vector_store.get_collection_stats()
        total_chunks = stats.get("total_chunks", 0)

        if total_chunks == 0:
            logger.warning("ChromaDB collection is empty — no documents ingested yet")
            return []

        effective_top_k = min(self.top_k, total_chunks)

        # Embed the question
        with Timer() as embed_timer:
            embedding_service = get_embedding_service()
            question_embedding = embedding_service.embed_query(question)

        logger.info(
            "Question embedded",
            extra={"elapsed_ms": embed_timer.elapsed_ms, "dim": len(question_embedding)},
        )

        # Query ChromaDB
        with Timer() as query_timer:
            collection = vector_store._get_collection()
            raw_results = collection.query(
                query_embeddings=[question_embedding],
                n_results=effective_top_k,
                include=["documents", "metadatas", "distances"],
            )

        logger.info(
            "ChromaDB query complete",
            extra={
                "results_found": len(raw_results["ids"][0]),
                "elapsed_ms": query_timer.elapsed_ms,
            },
        )

        results = self._parse_raw_results(raw_results)

        logger.info(
            "Retrieval complete",
            extra={
                "chunks_retrieved": len(results),
                "top_distance": round(results[0].distance, 4) if results else None,
            },
        )

        return results

    def _parse_raw_results(self, raw: Dict[str, Any]) -> List[RetrievalResult]:
        """
        Converts ChromaDB's nested-list response into RetrievalResult objects.

        ChromaDB always returns nested lists because it supports batched queries.
        We send one query, so we index with [0] to unwrap the batch dimension.
          raw["ids"][0]        = ["chunk_id_1", "chunk_id_2", ...]
          raw["documents"][0]  = ["text1", "text2", ...]
          raw["metadatas"][0]  = [{"filename": ..., "page_num": ...}, ...]
          raw["distances"][0]  = [0.12, 0.34, ...]
        """
        ids       = raw["ids"][0]
        texts     = raw["documents"][0]
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


# ── Singleton ─────────────────────────────────────────────────────────────────
_retrieval_service = None


def get_retrieval_service() -> RetrievalService:
    """Returns the shared RetrievalService instance."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(top_k=settings.RETRIEVAL_TOP_K)
    return _retrieval_service
