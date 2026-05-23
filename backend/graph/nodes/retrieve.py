"""
graph/nodes/retrieve.py
------------------------
LangGraph node: retrieve

Responsibility:
  - Takes the question from state
  - Calls RetrievalService to find the top-k relevant chunks
  - Formats those chunks into a context string for the LLM
  - Builds the sources list for the API response
  - Writes results back to state

Node contract (LangGraph rules):
  - Input:  GraphState (reads 'question')
  - Output: dict with the KEYS it changed ('retrieved_docs', 'context', 'sources', 'error')
  - LangGraph merges this dict into the full state automatically
  - NEVER return the full state — only the fields you modified

Context format sent to the LLM:
  [Source 1: annual_report.pdf, Page 3]
  Revenue grew by 23% in Q3, driven primarily by...

  ---

  [Source 2: annual_report.pdf, Page 7]
  Profit margins were affected by increased supply chain...

  ---

  This format tells the LLM exactly where each piece of information came from,
  which enables it to cite sources in its answer.
"""

from typing import Dict, Any, List

from graph.state import GraphState, RetrievedSource
from services.retrieval_service import get_retrieval_service
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


def retrieve(state: GraphState) -> Dict[str, Any]:
    """
    LangGraph node: embeds the question and retrieves top-k chunks from ChromaDB.

    Args:
        state: Current GraphState. Reads 'question'.

    Returns:
        Dict with updated fields: 'retrieved_docs', 'context', 'sources'.
        On error: returns 'error' field with description.
    """
    question = state["question"]

    logger.info("Retrieve node started", extra={"question_preview": question[:80]})

    with Timer() as t:
        try:
            retrieval_service = get_retrieval_service()
            results = retrieval_service.retrieve(question)
        except Exception as e:
            logger.error("Retrieval node failed", extra={"error": str(e)})
            return {
                "retrieved_docs": [],
                "context": "",
                "sources": [],
                "error": f"Retrieval failed: {str(e)}",
            }

    if not results:
        logger.warning(
            "No chunks retrieved",
            extra={"question_preview": question[:60], "reason": "collection empty or no matches"},
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

    # ── Raw docs (for debugging in later phases) ──────────────────────────────
    raw_docs = [
        {
            "chunk_id": r.chunk_id,
            "text": r.text,
            "filename": r.filename,
            "page_num": r.page_num,
            "distance": r.distance,
        }
        for r in results
    ]

    logger.info(
        "Retrieve node complete",
        extra={
            "chunks_retrieved": len(results),
            "unique_sources": len(sources),
            "context_chars": len(context),
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

    Each chunk is prefixed with its source (filename + page number).
    Sources are separated by "---" for visual clarity in the prompt.

    Example output:
        [Source 1: report.pdf, Page 3]
        Revenue grew 23% in Q3...

        ---

        [Source 2: report.pdf, Page 7]
        Profit margins were impacted by...
    """
    parts = []
    for i, result in enumerate(results, start=1):
        source_header = f"[Source {i}: {result.filename}, Page {result.page_num}]"
        parts.append(f"{source_header}\n{result.text}")

    return "\n\n---\n\n".join(parts)
