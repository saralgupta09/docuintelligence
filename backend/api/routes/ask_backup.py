"""
api/routes/ask.py
------------------
Handles question-answering via POST /api/v1/ask.

Phase 3 changes:
  - Accepts optional 'session_id' in the request body.
  - Generates a UUID session_id if the client doesn't provide one.
  - Loads conversation history from ConversationManager before graph.invoke().
  - Saves the Q&A turn to ConversationManager after graph.invoke().
  - Returns 'rewritten_query' and 'session_id' in the response (new fields).
  - All Phase 2 response fields are preserved — additive, not breaking.

Backward compatibility:
  Clients sending {"question": "..."} (no session_id) continue to work.
  They get a new session_id in the response they can use for follow-ups.

Flow:
  1. Receive question + optional session_id
  2. Generate session_id if absent
  3. Load chat_history from ConversationManager
  4. create_initial_state(question, chat_history)
  5. graph.invoke() → rewrite → retrieve → generate
  6. Save Q&A to ConversationManager
  7. Return answer + sources + rewritten_query + session_id
"""

import uuid
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from graph.retrieval_graph import get_retrieval_graph, create_initial_state
from memory.conversation_manager import get_conversation_manager
from utils.logger import get_logger, Timer

logger = get_logger(__name__)
router = APIRouter(prefix="/ask", tags=["Question Answering"])


# ── Request / Response Models ─────────────────────────────────────────────────

class AskRequest(BaseModel):
    """Input schema for POST /ask."""
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The question to ask about your documents.",
        examples=["What are the main findings of this report?"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Session identifier for multi-turn conversations.  "
            "If not provided, a new session is created and returned in the response.  "
            "Send this back on subsequent requests to maintain conversation history."
        ),
    )


class SourceReference(BaseModel):
    """One source document referenced in the answer."""
    filename: str = Field(description="Name of the source PDF file")
    page: int = Field(description="Page number within the document")
    chunk_id: str = Field(description="Internal chunk identifier")
    excerpt: str = Field(description="Short excerpt from the retrieved chunk")


class AskResponse(BaseModel):
    """Output schema for POST /ask."""
    # ── Phase 2 fields (preserved unchanged) ──────────────────────────────────
    question: str
    answer: str
    sources: List[SourceReference]
    chunks_retrieved: int = Field(description="Number of chunks retrieved from ChromaDB")
    processing_time_ms: int = Field(description="Total end-to-end latency in milliseconds")
    timestamp: str = Field(description="ISO 8601 timestamp of the response")
    # ── Phase 3 additions (additive — clients can ignore them) ────────────────
    rewritten_query: str = Field(
        description=(
            "The search-optimised query used for retrieval.  "
            "Equals 'question' when rewriting is disabled or the original "
            "question was already a clear standalone query."
        )
    )
    session_id: str = Field(
        description=(
            "Session identifier.  Store this and send it back in subsequent "
            "requests to maintain multi-turn conversation history."
        )
    )


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=AskResponse,
    summary="Ask a question about ingested documents",
    description=(
        "Retrieves relevant chunks from ChromaDB using hybrid BM25 + vector search, "
        "then generates a grounded answer via Gemini 2.5 Flash. "
        "Supports multi-turn conversations via optional session_id. "
        "Returns the answer, source chunks, rewritten query, and session_id."
    ),
)
def ask(request: AskRequest) -> AskResponse:
    """
    POST /api/v1/ask

    Accepts JSON:
      {"question": "your question here"}
      {"question": "follow-up", "session_id": "uuid-from-previous-response"}

    Returns: answer + sources + rewritten_query + session_id
    """
    question = request.question.strip()
    timestamp = datetime.now(timezone.utc).isoformat()

    # ── Session management ────────────────────────────────────────────────────
    session_id = request.session_id or str(uuid.uuid4())
    is_new_session = request.session_id is None

    logger.info(
        "Ask request received",
        extra={
            "question_preview": question[:80],
            "session_id": session_id[:8] + "...",
            "new_session": is_new_session,
        },
    )

    # ── Load conversation history ─────────────────────────────────────────────
    conversation_manager = get_conversation_manager()
    chat_history = conversation_manager.get_history(session_id)

    logger.info(
        "Chat history loaded",
        extra={
            "session_id": session_id[:8] + "...",
            "history_messages": len(chat_history),
        },
    )

    # ── Run the LangGraph pipeline ────────────────────────────────────────────
    with Timer() as t:
        try:
            graph = get_retrieval_graph()
            initial_state = create_initial_state(question, chat_history)
            final_state = graph.invoke(initial_state)

        except RuntimeError as e:
            error_msg = str(e)
            logger.error("Ask pipeline RuntimeError", extra={"error": error_msg})

            if "GEMINI_API_KEY" in error_msg:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Gemini API key is not configured. "
                        "Add GEMINI_API_KEY to your .env file. "
                        "Get a free key at https://aistudio.google.com/app/apikey"
                    ),
                )
            raise HTTPException(status_code=500, detail=error_msg)

        except Exception as e:
            logger.error("Ask pipeline unexpected error", extra={"error": str(e)})
            raise HTTPException(
                status_code=500,
                detail=f"An unexpected error occurred: {str(e)}",
            )

    # ── Extract results from final state ──────────────────────────────────────
    answer = final_state.get("answer", "")
    raw_sources = final_state.get("sources", [])
    retrieved_docs = final_state.get("retrieved_docs", [])
    pipeline_error = final_state.get("error")
    rewritten_query = final_state.get("retrieval_query", question)

    if pipeline_error:
        logger.warning(
            "Pipeline completed with error in state",
            extra={"error": pipeline_error},
        )

    # ── Save Q&A to conversation memory ───────────────────────────────────────
    # Always save both turns together — if either fails, don't save partial history
    try:
        conversation_manager.add_turn(session_id, role="user", content=question)
        conversation_manager.add_turn(session_id, role="assistant", content=answer)
    except Exception as e:
        # Memory save failure must not break the response
        logger.error(
            "Failed to save turn to ConversationManager — response unaffected",
            extra={"error": str(e), "session_id": session_id[:8] + "..."},
        )

    # ── Build response sources ────────────────────────────────────────────────
    response_sources = [
        SourceReference(
            filename=source["filename"],
            page=source["page"],
            chunk_id=source["chunk_id"],
            excerpt=source["excerpt"],
        )
        for source in raw_sources
    ]

    logger.info(
        "Ask request complete",
        extra={
            "question_preview": question[:60],
            "rewritten_preview": rewritten_query[:60],
            "answer_chars": len(answer),
            "sources_count": len(response_sources),
            "chunks_retrieved": len(retrieved_docs),
            "session_id": session_id[:8] + "...",
            "total_ms": t.elapsed_ms,
        },
    )

    return AskResponse(
        question=question,
        answer=answer,
        sources=response_sources,
        chunks_retrieved=len(retrieved_docs),
        processing_time_ms=int(t.elapsed_ms),
        timestamp=timestamp,
        rewritten_query=rewritten_query,
        session_id=session_id,
    )
