"""
services/bm25_service.py
-------------------------
Manages the BM25 keyword index for exact-term retrieval.

BM25 (Best Match 25) scores documents by term frequency (TF) and inverse
document frequency (IDF).  It excels at exact keyword matching where vector
search fails — names, codes, dates, section titles like "Section 4.2",
acronyms like "BERT" or "GPT-4".

Design decisions:
  - Lazy build: the index is constructed on the FIRST retrieval call, not at
    startup.  This keeps startup fast and avoids building against an empty DB.
  - Stale flag: after every ingest the caller sets mark_stale().  The NEXT
    retrieval detects the flag, rebuilds the index, then clears the flag.
    Rebuild happens at most once per ingest batch, not once per query.
  - Thread safety: a threading.Lock guards index build so concurrent requests
    can't trigger two simultaneous rebuilds.
  - Fallback: if the ChromaDB collection is empty or the BM25 build fails,
    search() returns an empty list.  The HybridRetrievalService then falls
    back to vector-only results — zero regression.

BM25 scoring:
  rank_bm25 returns raw BM25 scores (higher = more relevant).
  HybridRetrievalService normalises these to [0, 1] before merging.
"""

import threading
from typing import List, Optional, Tuple

from rank_bm25 import BM25Okapi

from utils.logger import get_logger, Timer

logger = get_logger(__name__)


class BM25Document:
    """Lightweight container for a document in the BM25 index."""

    def __init__(
        self,
        chunk_id: str,
        text: str,
        filename: str,
        page_num: int,
        doc_id: str,
        metadata: dict,
    ) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.filename = filename
        self.page_num = page_num
        self.doc_id = doc_id
        self.metadata = metadata

    def excerpt(self, max_chars: int = 200) -> str:
        """Short preview of the chunk text."""
        if len(self.text) <= max_chars:
            return self.text
        return self.text[:max_chars].rstrip() + "..."

    def __repr__(self) -> str:
        return (
            f"BM25Document(file={self.filename}, page={self.page_num}, "
            f"chars={len(self.text)})"
        )


class BM25Service:
    """
    Builds and queries a BM25 keyword index over all ChromaDB chunks.

    Thread safety:
      _lock guards _bm25, _corpus, and _is_stale so that concurrent FastAPI
      requests don't race on index builds.
    """

    def __init__(self) -> None:
        self._bm25: Optional[BM25Okapi] = None
        self._corpus: List[BM25Document] = []       # Parallel to BM25 index rows
        self._is_stale: bool = True                  # True → rebuild on next query
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def mark_stale(self) -> None:
        """
        Signals that the BM25 index is out of date.

        Call this after every successful ingest.  The next search() call will
        rebuild the index before scoring.  This is cheap (just sets a flag).
        """
        with self._lock:
            self._is_stale = True
        logger.info("BM25 index marked stale — will rebuild on next query")

    def search(self, query: str, top_k: int) -> List[Tuple[BM25Document, float]]:
        """
        Scores all indexed documents against the query and returns the top_k.

        Returns:
            List of (BM25Document, raw_bm25_score) tuples, ordered by score
            descending.  Raw scores are NOT normalised here — that's the
            HybridRetrievalService's job.
            Returns [] if the index is empty or the build failed.
        """
        if not query.strip():
            return []

        # Ensure the index is built and current
        self._ensure_index()

        with self._lock:
            if self._bm25 is None or not self._corpus:
                logger.warning("BM25 index is empty — returning no results")
                return []

            tokenized_query = query.lower().split()
            scores = self._bm25.get_scores(tokenized_query)

            # Pair each document with its score and sort
            scored: List[Tuple[BM25Document, float]] = [
                (doc, float(score))
                for doc, score in zip(self._corpus, scores)
            ]
            scored.sort(key=lambda x: x[1], reverse=True)

            top = scored[:top_k]

        logger.info(
            "BM25 search complete",
            extra={
                "query_preview": query[:60],
                "top_k": top_k,
                "results": len(top),
                "top_score": round(top[0][1], 4) if top else None,
            },
        )

        return top

    def index_size(self) -> int:
        """Returns the number of documents currently in the index."""
        with self._lock:
            return len(self._corpus)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure_index(self) -> None:
        """
        Rebuilds the BM25 index if it is stale or has never been built.

        Uses double-checked locking so only one thread rebuilds at a time.
        Other threads that arrive while the rebuild is in progress will wait
        on the lock, then find _is_stale=False and skip their own rebuild.
        """
        if not self._is_stale and self._bm25 is not None:
            return  # Fast path — index is current

        with self._lock:
            # Re-check inside the lock (another thread may have rebuilt while
            # we were waiting to acquire it)
            if not self._is_stale and self._bm25 is not None:
                return

            logger.info("Building BM25 index from ChromaDB")
            self._build_index()

    def _build_index(self) -> None:
        """
        Fetches all documents from ChromaDB and builds the BM25Okapi index.

        MUST be called with self._lock held.

        Tokenisation: simple whitespace split after lowercasing.  This is fast
        and sufficient for document retrieval — we're not doing NLP analysis.

        If ChromaDB is empty or the fetch fails, the index is left as None and
        subsequent search() calls return [] safely.
        """
        try:
            # Import here to avoid circular imports at module load time
            from services.vector_store import get_vector_store_service

            with Timer() as t:
                vector_store = get_vector_store_service()
                raw_docs = vector_store.get_all_documents()

            if not raw_docs:
                logger.warning("BM25 build skipped — ChromaDB returned 0 documents")
                self._bm25 = None
                self._corpus = []
                self._is_stale = False
                return

            # Build parallel lists: corpus (BM25Document) and tokenized texts
            corpus: List[BM25Document] = []
            tokenized_corpus: List[List[str]] = []

            for raw in raw_docs:
                doc = BM25Document(
                    chunk_id=raw["chunk_id"],
                    text=raw["text"],
                    filename=raw["filename"],
                    page_num=raw["page_num"],
                    doc_id=raw["doc_id"],
                    metadata=raw["metadata"],
                )
                corpus.append(doc)
                # Tokenise: lowercase + split on whitespace
                tokenized_corpus.append(doc.text.lower().split())

            self._bm25 = BM25Okapi(tokenized_corpus)
            self._corpus = corpus
            self._is_stale = False

            logger.info(
                "BM25 index built",
                extra={
                    "documents": len(corpus),
                    "elapsed_ms": t.elapsed_ms,
                },
            )

        except Exception as e:
            logger.error(
                "BM25 index build failed — will retry on next query",
                extra={"error": str(e)},
            )
            # Leave _bm25 as None so search() safely returns []
            # Don't clear _is_stale so the next query retries the build
            self._bm25 = None
            self._corpus = []


# ── Singleton ─────────────────────────────────────────────────────────────────
_bm25_service: Optional[BM25Service] = None


def get_bm25_service() -> BM25Service:
    """Returns the shared BM25Service instance."""
    global _bm25_service
    if _bm25_service is None:
        _bm25_service = BM25Service()
    return _bm25_service
