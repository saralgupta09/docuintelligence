"""
graph/nodes/generate.py
------------------------
LangGraph node: generate

Phase 3 changes:
  - Reads 'chat_history' from state and formats it via ConversationManager
    (or directly) before passing to LLMService.generate().
  - LLMService.generate() now accepts an optional chat_history_str parameter.
  - All other behaviour is identical to Phase 2.

Node contract:
  - Input:  GraphState (reads 'question', 'context', 'chat_history', 'error')
  - Output: dict with 'answer' key only (the only field this node changes)

Error propagation:
  If the retrieve node set an error, this node detects it and returns a
  user-friendly message instead of calling the LLM — no wasted API calls.
"""

from typing import Dict, Any

from graph.state import GraphState
from services.llm_service import get_llm_service
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


def generate(state: GraphState) -> Dict[str, Any]:
    """
    LangGraph node: generates an answer using retrieved context and Gemini.

    Args:
        state: Current GraphState.
               Reads 'question', 'context', 'chat_history', 'error'.

    Returns:
        Dict with updated field: 'answer'.
    """
    question = state["question"]
    context = state.get("context", "")
    chat_history: list = state.get("chat_history", [])
    upstream_error = state.get("error")

    # ── Check for upstream retrieval failure ──────────────────────────────────
    if upstream_error:
        logger.warning(
            "Generate node skipping LLM due to upstream error",
            extra={"error": upstream_error},
        )
        return {
            "answer": (
                "I encountered an error while searching your documents. "
                f"Details: {upstream_error}"
            )
        }

    # ── Handle empty context (no documents ingested or no matches) ────────────
    if not context.strip():
        logger.warning(
            "Generate node received empty context",
            extra={"question_preview": question[:60]},
        )
        # Still call the LLM — the prompt instructs it to say "no info found"

    # ── Format chat history for the prompt ───────────────────────────────────
    chat_history_str = _format_history_for_prompt(chat_history)

    logger.info(
        "Generate node started",
        extra={
            "question_preview": question[:80],
            "context_chars": len(context),
            "history_turns": len(chat_history) // 2,
        },
    )

    with Timer() as t:
        try:
            llm_service = get_llm_service()
            answer = llm_service.generate(
                question=question,
                context=context,
                chat_history_str=chat_history_str,
            )
        except RuntimeError as e:
            logger.error("Generate node LLM call failed", extra={"error": str(e)})
            return {"answer": f"Answer generation failed: {str(e)}"}
        except Exception as e:
            logger.error("Generate node unexpected error", extra={"error": str(e)})
            return {"answer": "An unexpected error occurred during answer generation."}

    logger.info(
        "Generate node complete",
        extra={
            "answer_chars": len(answer),
            "elapsed_ms": t.elapsed_ms,
        },
    )

    return {"answer": answer}


def _format_history_for_prompt(chat_history: list) -> str:
    """
    Formats a list of {"role": str, "content": str} dicts into a multi-line
    string for LLM injection.

    Returns "" if history is empty (generate node adds the section only when
    non-empty, handled in LLMService.build_prompt).
    """
    if not chat_history:
        return ""

    lines = []
    for turn in chat_history:
        role_label = "User" if turn.get("role") == "user" else "Assistant"
        lines.append(f"{role_label}: {turn.get('content', '')}")

    return "\n".join(lines)
