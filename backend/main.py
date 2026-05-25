"""
main.py
-------
FastAPI application entry point for DocuIntel backend.
Phase 3: Hybrid retrieval (BM25 + vector), query rewriting, conversation memory.
"""

from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings, ensure_directories
from api.routes import ingest, ask
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once at startup before requests are accepted.
    Initialises all services so the first request isn't slow.
    """
    logger.info(
        "Starting DocuIntel backend",
        extra={
            "version": settings.APP_VERSION,
            "embedding_model": settings.EMBEDDING_MODEL_NAME,
            "llm_model": settings.GEMINI_MODEL,
            "gemini_key_set": bool(settings.GEMINI_API_KEY),
            "query_rewriting": settings.ENABLE_QUERY_REWRITING,
            "max_memory_turns": settings.MAX_MEMORY_TURNS,
            "semantic_weight": settings.SEMANTIC_WEIGHT,
            "bm25_weight": settings.BM25_WEIGHT,
        },
    )

    # Ensure data directories exist before any requests come in
    ensure_directories()
    logger.info("Directories verified")

    # Pre-compile the LangGraph so the first /ask request isn't slow
    from graph.retrieval_graph import get_retrieval_graph
    get_retrieval_graph()
    logger.info("LangGraph retrieval graph compiled and ready")

    # Initialise ConversationManager so it's ready for the first request
    from memory.conversation_manager import get_conversation_manager
    conversation_manager = get_conversation_manager()
    logger.info(
        "ConversationManager ready",
        extra={
            "max_turns": settings.MAX_MEMORY_TURNS,
            "active_sessions": conversation_manager.session_count(),
        },
    )

    logger.info("DocuIntel Phase 3 ready — waiting for requests")

    yield  # Application runs between yield and the code below

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("DocuIntel backend shutting down")


# ── App initialization ─────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Multimodal AI Document Intelligence System\n\n"
        "Phase 3: Hybrid retrieval (BM25 + vector), query rewriting, "
        "multi-turn conversation memory."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── CORS Middleware ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(ingest.router, prefix="/api/v1")
app.include_router(ask.router, prefix="/api/v1")


# ── Health Check ───────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check", tags=["System"], response_model=Dict[str, Any])
def health_check() -> Dict[str, Any]:
    """
    Returns system status, ChromaDB stats, BM25 index size, and memory stats.
    Use this to verify all Phase 3 subsystems are running.
    """
    from services.vector_store import get_vector_store_service
    from services.bm25_service import get_bm25_service
    from memory.conversation_manager import get_conversation_manager

    try:
        vector_store = get_vector_store_service()
        db_stats = vector_store.get_collection_stats()
        db_status = "ok"
    except Exception as e:
        db_stats = {}
        db_status = f"error: {str(e)}"

    try:
        bm25_service = get_bm25_service()
        bm25_index_size = bm25_service.index_size()
    except Exception:
        bm25_index_size = -1

    try:
        conv_manager = get_conversation_manager()
        active_sessions = conv_manager.session_count()
    except Exception:
        active_sessions = -1

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "phase": "3 - Hybrid RAG + Memory",
        "embedding_model": settings.EMBEDDING_MODEL_NAME,
        "llm_model": settings.GEMINI_MODEL,
        "gemini_key_configured": bool(settings.GEMINI_API_KEY),
        "query_rewriting_enabled": settings.ENABLE_QUERY_REWRITING,
        "hybrid_weights": {
            "semantic": settings.SEMANTIC_WEIGHT,
            "bm25": settings.BM25_WEIGHT,
        },
        "vector_db": {"status": db_status, **db_stats},
        "bm25_index": {"documents_indexed": bm25_index_size},
        "memory": {"active_sessions": active_sessions},
    }


@app.get("/", include_in_schema=False)
def root() -> Dict[str, str]:
    """Redirect hint — tells users where to find the docs."""
    return {
        "message": "DocuIntel API is running.",
        "docs": "http://localhost:8000/docs",
        "health": "http://localhost:8000/health",
    }
