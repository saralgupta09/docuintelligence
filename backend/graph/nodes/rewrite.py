"""
graph/nodes/rewrite.py
-----------------------
LangGraph node: rewrite

Responsibility:
  - Reads 'question' and 'chat_history' from state.
  - Calls LLMService.rewrite_query() to produce a search-optimised standalone
    query.  This is a lightweight Gemini call (~20 output tokens).
  - Writes the result to state['retrieval_query'].
  - If rewriting is disabled (ENABLE_QUERY_REWRITING=False) or the Gemini call
    fails, falls back to retrieval_query = question.  The pipeline is never
    blocked by a rewrite failure.

Why this node exists:
  Multi-turn questions are often anaphoric ("what about the second one?",
  "and for the next year?").  Without rewriting, the retriever gets a vague
  fragment and returns irrelevant chunks.  This node resolves references
  using conversation history before retrieval.

Node contract (LangGraph rules):
  - Input:  GraphState (reads 'question', 'chat_history')
  - Output: dict with ONLY the keys changed ('retrieval_query')
  - Never return the full state — only fields this node modifies.

Fallback chain:
  1. ENABLE_QUERY_REWRITING is False → use question verbatim
  2. GEMINI_API_KEY missing           → use question verbatim, log warning
  3. Gemini call raises exception     → use question verbatim, log error
  4. Gemini returns empty string      → use question verbatim, log warning
  Any of the above: pipeline continues normally, no error is set in state.
"""

from typing import Dict, Any

from config import settings
from graph.state import GraphState
from services.llm_service import get_llm_service
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


def rewrite(state: GraphState) -> Dict[str, Any]:
    """
    LangGraph node: rewrites the user's question into a search-optimised query.

    Args:
        state: Current GraphState.  Reads 'question' and 'chat_history'.

    Returns:
        Dict with updated field: 'retrieval_query'.
        Always returns something — never raises; never sets 'error'.
    """
    question = state["question"]
    chat_history: list = state.get("chat_history", [])

    # ── Fast path: rewriting disabled ─────────────────────────────────────────
    if not settings.ENABLE_QUERY_REWRITING:
        logger.info(
            "Query rewriting disabled — using original question",
            extra={"question_preview": question[:80]},
        )
        return {"retrieval_query": question}

    logger.info(
        "Rewrite node started",
        extra={
            "question_preview": question[:80],
            "history_turns": len(chat_history) // 2,
        },
    )

    with Timer() as t:
        rewritten = _attempt_rewrite(question, chat_history)

    logger.info(
        "Rewrite node complete",
        extra={
            "original": question[:80],
            "rewritten": rewritten[:80],
            "changed": rewritten != question,
            "elapsed_ms": t.elapsed_ms,
        },
    )

    return {"retrieval_query": rewritten}


# ── Private helpers ───────────────────────────────────────────────────────────

def _attempt_rewrite(question: str, chat_history: list) -> str:
    """
    Tries to call LLMService.rewrite_query().  Returns the original question
    on any failure so the pipeline is never blocked.
    """
    try:
        llm_service = get_llm_service()
        rewritten = llm_service.rewrite_query(
            question=question,
            chat_history=chat_history,
        )
        if not rewritten or not rewritten.strip():
            logger.warning("Gemini returned empty rewrite — using original question")
            return question
        return rewritten.strip()

    except RuntimeError as e:
        # Missing API key or API call failed
        logger.warning(
            "Rewrite failed (RuntimeError) — using original question",
            extra={"error": str(e)},
        )
        return question

    except Exception as e:
        logger.error(
            "Rewrite failed (unexpected error) — using original question",
            extra={"error": str(e)},
        )
        return question
