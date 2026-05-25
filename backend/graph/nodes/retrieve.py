"""
graph/nodes/retrieve.py
------------------------
LangGraph node: retrieve

Phase 3 changes:
  - Uses HybridRetrievalService (BM25 + vector) instead of RetrievalService.
  - Reads 'retrieval_query' from state (the rewrite node's output) rather than
    'question'.  If rewriting is disabled, retrieval_query == question.
  - Adds 'combined_score' to the raw_docs list for debuggability.
  - All other behaviour is identical to Phase 2.

Node contract (LangGraph rules):
  - Input:  GraphState (reads 'retrieval_query')
  - Output: dict with ONLY the keys changed ('retrieved_docs', 'context',
            'sources', 'error')
  - NEVER return the full state.

Context format sent to the LLM:
  [Source 1: annual_report.pdf, Page 3]
  Revenue grew by 23% in Q3, driven primarily by...

  ---

  [Source 2: annual_report.pdf, Page 7]
  Profit margins were affected by increased supply chain...
"""

from typing import Dict, Any, List

from graph.state import GraphState, RetrievedSource
from services.hybrid_retrieval_service import get_hybrid_retrieval_service
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


def retrieve(state: GraphState) -> Dict[str, Any]:
    """
    LangGraph node: runs hybrid retrieval using the rewritten query.

    Args:
        state: Current GraphState.  Reads 'retrieval_query'.

    Returns:
        Dict with updated fields: 'retrieved_docs', 'context', 'sources'.
        On error: returns 'error' field with description.
    """
    # Use retrieval_query (rewrite node output).  Falls back to question if
    # retrieval_query was never set (should not happen with Phase 3 graph, but
    # defensive programming keeps unit tests safe).
    retrieval_query = state.get("retrieval_query") or state["question"]

    logger.info(
        "Retrieve node started (hybrid)",
        extra={"query_preview": retrieval_query[:80]},
    )

    with Timer() as t:
        try:
            hybrid_service = get_hybrid_retrieval_service()
            results = hybrid_service.retrieve(retrieval_query)
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
    seen_sources = set()  # Deduplicate: same file+page shouldn't appear twice

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
            # HybridRetrievalResult has .distance derived from vector_score
            "distance": r.distance,
            # Phase 3 extra fields
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
    """
    Formats retrieved chunks into a numbered context string for the LLM.

    Works with both HybridRetrievalResult and RetrievalResult objects
    (both have .filename, .page_num, .text attributes).
    """
    parts = []
    for i, result in enumerate(results, start=1):
        source_header = f"[Source {i}: {result.filename}, Page {result.page_num}]"
        parts.append(f"{source_header}\n{result.text}")

    return "\n\n---\n\n".join(parts)
