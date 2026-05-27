import uuid
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from graph.retrieval_graph import get_retrieval_graph, create_initial_state
from memory.conversation_manager import get_conversation_manager
from services.conversation_store import get_conversation_store
from utils.logger import get_logger, Timer

logger = get_logger(__name__)
router = APIRouter(prefix="/ask", tags=["Question Answering"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    session_id: Optional[str] = None
    doc_id: Optional[str] = None


class SourceReference(BaseModel):
    filename: str
    page: int
    chunk_id: str
    excerpt: str
    score: Optional[float] = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    page_num: int
    filename: str
    score: Optional[float] = None


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: List[SourceReference]
    chunks_retrieved: int
    processing_time_ms: int
    timestamp: str
    rewritten_query: str
    session_id: str
    doc_id_filter: Optional[str] = None
    retrieved_chunks: List[RetrievedChunk] = Field(default_factory=list)


@router.post("/", response_model=AskResponse, summary="Ask a question about ingested documents")
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
            "doc_id_filter": request.doc_id or "all",
        },
    )

    conversation_manager = get_conversation_manager()
    chat_history = conversation_manager.get_history(session_id)

    with Timer() as t:
        try:
            graph = get_retrieval_graph()
            initial_state = create_initial_state(
                question,
                chat_history,
                doc_id=request.doc_id,
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
                        "Add GEMINI_API_KEY to your .env file."
                    ),
                )
            raise HTTPException(status_code=500, detail=error_msg)

        except Exception as e:
            logger.error("Ask pipeline unexpected error", extra={"error": str(e)})
            raise HTTPException(
                status_code=500,
                detail=f"An unexpected error occurred: {str(e)}",
            )

    answer = final_state.get("answer", "")
    raw_sources = final_state.get("sources", [])
    retrieved_docs = final_state.get("retrieved_docs", [])
    pipeline_error = final_state.get("error")
    rewritten_query = final_state.get("retrieval_query", question)

    if pipeline_error:
        logger.warning("Pipeline completed with error in state", extra={"error": pipeline_error})

    try:
        conversation_manager.add_turn(session_id, role="user", content=question)
        conversation_manager.add_turn(session_id, role="assistant", content=answer)
    except Exception as e:
        logger.error(
            "Failed to save turn to ConversationManager",
            extra={"error": str(e), "session_id": session_id[:8] + "..."},
        )

    score_by_chunk_id = {
        doc["chunk_id"]: doc.get("combined_score")
        for doc in retrieved_docs
        if isinstance(doc, dict) and "chunk_id" in doc
    }

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

    response_chunks = [
        RetrievedChunk(
            chunk_id=doc["chunk_id"],
            text=doc["text"],
            page_num=doc["page_num"],
            filename=doc["filename"],
            score=doc.get("combined_score"),
        )
        for doc in retrieved_docs
        if isinstance(doc, dict) and doc.get("text") and doc.get("filename")
    ]

    try:
        store = get_conversation_store()
        store.append_turn(
            session_id,
            user_message={
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": question,
                "timestamp": timestamp,
            },
            assistant_message={
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": answer,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sources": [source.model_dump() for source in response_sources],
                "rewrittenQuery": rewritten_query,
                "processingMs": int(t.elapsed_ms),
                "chunksRetrieved": len(retrieved_docs),
                "docIdFilter": request.doc_id,
                "retrievedChunks": [chunk.model_dump() for chunk in response_chunks],
            },
            retrieved_sources=[source.model_dump() for source in response_sources],
            highlights=[chunk.model_dump() for chunk in response_chunks],
        )
    except Exception as e:
        logger.error(
            "Failed to persist conversation snapshot",
            extra={"error": str(e), "session_id": session_id[:8] + "..."},
        )

    logger.info(
        "Ask request complete",
        extra={
            "question_preview": question[:60],
            "answer_chars": len(answer),
            "sources_count": len(response_sources),
            "chunks_retrieved": len(retrieved_docs),
            "highlight_chunks": len(response_chunks),
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
        doc_id_filter=request.doc_id,
        retrieved_chunks=response_chunks,
    )