"""
api/routes/ask.py
------------------
Handles question-answering via POST /api/v1/ask.

Flow:
  1. Receive the user's question (JSON body)
  2. Validate input
  3. Initialize GraphState with the question
  4. Invoke the LangGraph retrieval pipeline
  5. Return the answer + sources in a clean response

Error scenarios handled:
  - Empty question → 400 Bad Request
  - No documents in ChromaDB → 200 with guidance message
  - LLM API key missing → 503 Service Unavailable
  - Any unexpected error → 500 Internal Server Error

Design note:
  The route is deliberately thin — it only handles HTTP concerns
  (request parsing, response formatting, HTTP error codes).
  All business logic lives in the graph nodes and services.
"""

from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from graph.retrieval_graph import get_retrieval_graph, create_initial_state
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


class SourceReference(BaseModel):
    """One source document referenced in the answer."""
    filename: str = Field(description="Name of the source PDF file")
    page: int = Field(description="Page number within the document")
    chunk_id: str = Field(description="Internal chunk identifier")
    excerpt: str = Field(description="Short excerpt from the retrieved chunk")


class AskResponse(BaseModel):
    """Output schema for POST /ask."""
    question: str
    answer: str
    sources: List[SourceReference]
    chunks_retrieved: int = Field(description="Number of chunks retrieved from ChromaDB")
    processing_time_ms: int = Field(description="Total end-to-end latency in milliseconds")
    timestamp: str = Field(description="ISO 8601 timestamp of the response")


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=AskResponse,
    summary="Ask a question about ingested documents",
    description=(
        "Retrieves relevant chunks from ChromaDB using semantic similarity, "
        "then generates a grounded answer via Gemini 2.5 Flash. "
        "Returns the answer and the source chunks used."
    ),
)
def ask(request: AskRequest) -> AskResponse:
    """
    POST /api/v1/ask

    Accepts JSON: {"question": "your question here"}
    Returns: answer + list of source documents
    """
    question = request.question.strip()
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Ask request received",
        extra={"question_preview": question[:80]},
    )

    # ── Run the LangGraph pipeline ────────────────────────────────────────────
    with Timer() as t:
        try:
            graph = get_retrieval_graph()
            initial_state = create_initial_state(question)
            final_state = graph.invoke(initial_state)

        except RuntimeError as e:
            # Catches: GEMINI_API_KEY missing, API call failed
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

    # Log if the pipeline encountered any errors (non-fatal — answer still returned)
    if pipeline_error:
        logger.warning(
            "Pipeline completed with error in state",
            extra={"error": pipeline_error},
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
            "answer_chars": len(answer),
            "sources_count": len(response_sources),
            "chunks_retrieved": len(retrieved_docs),
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
    )
