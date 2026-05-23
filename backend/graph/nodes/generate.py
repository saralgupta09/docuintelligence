"""
graph/nodes/generate.py
------------------------
LangGraph node: generate

Responsibility:
  - Reads the question and formatted context from state
  - Calls LLMService to generate an answer via Gemini 2.5 Flash
  - Writes the answer back to state

Node contract:
  - Input:  GraphState (reads 'question', 'context', 'error')
  - Output: dict with 'answer' key only (the only field this node changes)

Error propagation:
  If the retrieve node set an error, this node detects it and returns a
  user-friendly message instead of calling the LLM — no wasted API calls.

  If retrieval returned no chunks (context is empty), the LLM is still called
  but the prompt instructs it to say "I don't have enough information..."
  This is better than returning a raw "no results" error to the user.
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
        state: Current GraphState. Reads 'question', 'context', 'error'.

    Returns:
        Dict with updated field: 'answer'.
    """
    question = state["question"]
    context = state.get("context", "")
    upstream_error = state.get("error")

    # ── Check for upstream retrieval failure ──────────────────────────────────
    # If retrieve node set an error flag, skip the LLM and return a clear message.
    # This avoids calling the Gemini API when we already know retrieval failed.
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
        # Still call the LLM — the prompt handles empty context gracefully
        # by instructing it to say "no information found"

    logger.info(
        "Generate node started",
        extra={
            "question_preview": question[:80],
            "context_chars": len(context),
        },
    )

    with Timer() as t:
        try:
            llm_service = get_llm_service()
            answer = llm_service.generate(question=question, context=context)
        except RuntimeError as e:
            # API key missing or API call failed
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
