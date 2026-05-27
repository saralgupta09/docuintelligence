"""
graph/nodes/retrieve.py
------------------------
LangGraph node: retrieve

Feature 1 change: reads the optional 'doc_id' field from state and passes
it to HybridRetrievalService.retrieve(). When doc_id is set, retrieval is
scoped to chunks from that document only. When None, all documents are
searched (existing behaviour, zero regression).

All other logic — query resolution, context formatting, source deduplication,
raw_docs structure — is completely unchanged.
"""

from typing import Dict, Any, List

from graph.state import GraphState, RetrievedSource
from services.hybrid_retrieval_service import get_hybrid_retrieval_service
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


def retrieve(state: GraphState) -> Dict[str, Any]:
    """
    LangGraph node: runs hybrid retrieval using the rewritten query.

    Reads:  'retrieval_query', 'doc_id'
    Writes: 'retrieved_docs', 'context', 'sources', 'error'
    """
    retrieval_query = state.get("retrieval_query") or state["question"]
    doc_id = state.get("doc_id")          # Feature 1: None = all docs

    logger.info(
        "Retrieve node started (hybrid)",
        extra={
            "query_preview": retrieval_query[:80],
            "doc_id_filter": doc_id or "all",
        },
    )

    with Timer() as t:
        try:
            hybrid_service = get_hybrid_retrieval_service()
            results = hybrid_service.retrieve(retrieval_query, doc_id=doc_id)
        except Exception as e:
            logger.error("Hybrid retrieve node failed", extra={"error": str(e)})
            return {
                "retrieved_docs": [],
                "context": "",
                "sources": [],
                "error": f"Retrieval failed: {str(e)}",
            }

    if not results:
        logger.warning(
            "No chunks retrieved",
            extra={
                "query_preview": retrieval_query[:60],
                "doc_id_filter": doc_id or "all",
                "reason": "collection empty or no matches",
            },
        )
        return {
            "retrieved_docs": [],
            "context": "",
            "sources": [],
            "error": None,
        }

    # ── Build context string for the LLM ──────────────────────────────────────
    context = _build_context_string(results)

    # ── Build sources list for the API response ───────────────────────────────
    sources: List[RetrievedSource] = []
    seen_sources = set()

    for result in results:
        source_key = f"{result.filename}:{result.page_num}"
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            sources.append(
                RetrievedSource(
                    filename=result.filename,
                    page=result.page_num,
                    chunk_id=result.chunk_id,
                    excerpt=result.excerpt(max_chars=200),
                )
            )

    # ── Raw docs (for debugging and API response) ─────────────────────────────
    raw_docs = [
        {
            "chunk_id": r.chunk_id,
            "text": r.text,
            "filename": r.filename,
            "page_num": r.page_num,
            "distance": r.distance,
            "combined_score": r.combined_score,
            "vector_score": r.vector_score,
            "bm25_score": r.bm25_score,
        }
        for r in results
    ]

    logger.info(
        "Retrieve node complete",
        extra={
            "chunks_retrieved": len(results),
            "unique_sources": len(sources),
            "context_chars": len(context),
            "top_combined_score": round(results[0].combined_score, 4) if results else None,
            "elapsed_ms": t.elapsed_ms,
        },
    )

    return {
        "retrieved_docs": raw_docs,
        "context": context,
        "sources": sources,
        "error": None,
    }


def _build_context_string(results) -> str:
    parts = []
    for i, result in enumerate(results, start=1):
        source_header = f"[Source {i}: {result.filename}, Page {result.page_num}]"
        parts.append(f"{source_header}\n{result.text}")
    return "\n\n---\n\n".join(parts)
