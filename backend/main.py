"""
main.py  (MODIFIED for Phase 5 frontend integration)
-------
Changes from original (both are additive / non-breaking):

1. CORSMiddleware now also allows http://localhost:5173 and
   http://127.0.0.1:5173  (Vite dev server default port).
   The original origins (8501) are preserved for backward compat.

2. The new documents router is registered at /api/v1.
   All existing routes and lifespan logic are UNCHANGED.
"""

from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings, ensure_directories
from api.routes import ingest, ask
from api.routes.documents import router as documents_router   # ← NEW
from utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
            # Phase 4
            "ocr_enabled": settings.OCR_ENABLED,
            "ocr_language": settings.OCR_LANGUAGE,
            "ocr_dpi": settings.OCR_DPI,
        },
    )

    ensure_directories()
    logger.info("Directories verified")

    from graph.retrieval_graph import get_retrieval_graph
    get_retrieval_graph()
    logger.info("LangGraph retrieval graph compiled and ready")

    from memory.conversation_manager import get_conversation_manager
    conversation_manager = get_conversation_manager()
    logger.info(
        "ConversationManager ready",
        extra={
            "max_turns": settings.MAX_MEMORY_TURNS,
            "active_sessions": conversation_manager.session_count(),
        },
    )

    # Phase 4: verify tesseract is accessible if OCR is enabled
    if settings.OCR_ENABLED:
        try:
            import pytesseract
            version = pytesseract.get_tesseract_version()
            logger.info(
                "Tesseract OCR ready",
                extra={
                    "tesseract_version": str(version),
                    "language": settings.OCR_LANGUAGE,
                    "dpi": settings.OCR_DPI,
                },
            )
        except Exception as e:
            logger.warning(
                "OCR_ENABLED=true but Tesseract check failed. "
                "OCR will be skipped for scanned pages. "
                "Install tesseract: sudo apt-get install tesseract-ocr",
                extra={"error": str(e)},
            )

    logger.info("DocuIntel Phase 5 ready — waiting for requests")
    yield
    logger.info("DocuIntel backend shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Multimodal AI Document Intelligence System\n\n"
        "Phase 5: React frontend integration."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Phase 5 addition: added Vite dev server origins (5173).
# Original Streamlit origins (8501) are preserved for backward compat.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",     # ← Phase 5: Vite dev server
        "http://127.0.0.1:5173",    # ← Phase 5: Vite dev server (alternate)
        "http://localhost:8501",     # Original: Streamlit
        "http://127.0.0.1:8501",    # Original: Streamlit
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ingest.router, prefix="/api/v1")
app.include_router(ask.router, prefix="/api/v1")
app.include_router(
    documents_router,
    prefix="/api/v1/documents",
    tags=["Documents"]
)


@app.get("/health", summary="Health check", tags=["System"], response_model=Dict[str, Any])
def health_check() -> Dict[str, Any]:
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

    # Phase 4: add OCR status to health response
    ocr_status = "disabled"
    if settings.OCR_ENABLED:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            ocr_status = "ok"
        except Exception as e:
            ocr_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "phase": "5 - React Frontend + OCR + Hybrid RAG + Memory",
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
        # Phase 4
        "ocr": {
            "status": ocr_status,
            "enabled": settings.OCR_ENABLED,
            "language": settings.OCR_LANGUAGE,
            "dpi": settings.OCR_DPI,
        },
    }


@app.get("/", include_in_schema=False)
def root() -> Dict[str, str]:
    return {
        "message": "DocuIntel API is running.",
        "docs": "http://localhost:8000/docs",
        "health": "http://localhost:8000/health",
    }
