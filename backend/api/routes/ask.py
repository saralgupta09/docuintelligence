"""
api/routes/ask.py
------------------
Feature 1 change: AskRequest gains an optional 'doc_id' field.
When provided, it is passed to create_initial_state() so the retrieve
node scopes its ChromaDB and BM25 searches to that document only.
When absent (None), all documents are searched — existing behaviour unchanged.

All other logic, field names, and response shape are preserved exactly.
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
            "Session identifier for multi-turn conversations. "
            "If not provided, a new session is created and returned."
        ),
    )
    # ── Feature 1 addition ────────────────────────────────────────────────────
    doc_id: Optional[str] = Field(
        default=None,
        description=(
            "When provided, retrieval is scoped to chunks from this document only. "
            "Use the doc_id value returned by POST /ingest or GET /documents. "
            "Omit (or pass null) to search across all documents."
        ),
        examples=["research_pdf", None],
    )


class SourceReference(BaseModel):
    filename: str = Field(description="Name of the source PDF file")
    page: int = Field(description="Page number within the document")
    chunk_id: str = Field(description="Internal chunk identifier")
    excerpt: str = Field(description="Short excerpt from the retrieved chunk")
    score: Optional[float] = Field(
        default=None,
        description="Hybrid retrieval confidence score (0–1).",
    )


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: List[SourceReference]
    chunks_retrieved: int = Field(description="Number of chunks retrieved from ChromaDB")
    processing_time_ms: int = Field(description="Total end-to-end latency in milliseconds")
    timestamp: str = Field(description="ISO 8601 timestamp of the response")
    rewritten_query: str = Field(
        description="The search-optimised query used for retrieval."
    )
    session_id: str = Field(
        description="Session identifier. Send back on subsequent requests."
    )
    # ── Feature 1: echo back which doc was filtered ───────────────────────────
    doc_id_filter: Optional[str] = Field(
        default=None,
        description="The doc_id filter applied to this request, if any.",
    )


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=AskResponse,
    summary="Ask a question about ingested documents",
)
def ask(request: AskRequest) -> AskResponse:
    question = request.question.strip()
    timestamp = datetime.now(timezone.utc).isoformat()

    session_id = request.session_id or str(uuid.uuid4())
    is_new_session = request.session_id is None

    logger.info(
        "Ask request received",
        extra={
            "question_preview": question[:80],
            "session_id": session_id[:8] + "...",
            "new_session": is_new_session,
            "doc_id_filter": request.doc_id or "all",     # Feature 1
        },
    )

    # ── Load conversation history ─────────────────────────────────────────────
    conversation_manager = get_conversation_manager()
    chat_history = conversation_manager.get_history(session_id)

    # ── Run the LangGraph pipeline ────────────────────────────────────────────
    with Timer() as t:
        try:
            graph = get_retrieval_graph()
            initial_state = create_initial_state(
                question,
                chat_history,
                doc_id=request.doc_id,          # Feature 1: pass filter
            )
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
        logger.warning("Pipeline completed with error in state", extra={"error": pipeline_error})

    # ── Save Q&A to conversation memory ───────────────────────────────────────
    try:
        conversation_manager.add_turn(session_id, role="user", content=question)
        conversation_manager.add_turn(session_id, role="assistant", content=answer)
    except Exception as e:
        logger.error(
            "Failed to save turn to ConversationManager",
            extra={"error": str(e), "session_id": session_id[:8] + "..."},
        )

    # ── Build chunk_id → combined_score lookup ────────────────────────────────
    score_by_chunk_id = {
        doc["chunk_id"]: doc.get("combined_score")
        for doc in retrieved_docs
        if isinstance(doc, dict) and "chunk_id" in doc
    }

    # ── Build response sources ────────────────────────────────────────────────
    response_sources = [
        SourceReference(
            filename=source["filename"],
            page=source["page"],
            chunk_id=source["chunk_id"],
            excerpt=source["excerpt"],
            score=score_by_chunk_id.get(source["chunk_id"]),
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
            "doc_id_filter": request.doc_id or "all",
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
        doc_id_filter=request.doc_id,           # Feature 1: echo back
    )
