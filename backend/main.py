"""
main.py
-------
FastAPI application entry point for DocuIntel backend.

Startup sequence:
  1. Load .env config via pydantic BaseSettings
  2. Create required directories (uploads/, chroma_db/)
  3. Register API routers
  4. Expose health check endpoint

Run with:
    cd backend
    uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings, ensure_directories
from api.routes import ingest
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once at startup before requests are accepted.
    Clean place to initialize resources (directories, connections, etc.)
    """
    logger.info(
        "Starting DocuIntel backend",
        extra={
            "version": settings.APP_VERSION,
            "debug": settings.DEBUG,
            "log_level": settings.LOG_LEVEL,
            "upload_dir": settings.UPLOAD_DIR,
            "chroma_dir": settings.CHROMA_PERSIST_DIR,
            "embedding_model": settings.EMBEDDING_MODEL_NAME,
        },
    )

    # Ensure data directories exist before any requests come in
    ensure_directories()
    logger.info("Directories verified")

    logger.info("DocuIntel Phase 1 ready — waiting for requests")

    yield  # Application runs between yield and the code below

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("DocuIntel backend shutting down")


# ── App initialization ─────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Multimodal AI Document Intelligence System\n\n"
        "Phase 1: PDF ingestion → text extraction → chunking → embeddings → ChromaDB"
    ),
    docs_url="/docs",      # Swagger UI at http://localhost:8000/docs
    redoc_url="/redoc",    # ReDoc at http://localhost:8000/redoc
    lifespan=lifespan,
)


# ── CORS Middleware ────────────────────────────────────────────────────────────
# Allows the Streamlit frontend (localhost:8501) to call the backend (localhost:8000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(ingest.router, prefix="/api/v1")

# Future phases will add:
# app.include_router(chat.router, prefix="/api/v1")
# app.include_router(documents.router, prefix="/api/v1")


# ── Health Check ───────────────────────────────────────────────────────────────

@app.get(
    "/health",
    summary="Health check",
    tags=["System"],
    response_model=Dict[str, Any],
)
def health_check() -> Dict[str, Any]:
    """
    Returns system status and ChromaDB stats.
    Use this to verify the server is running before testing ingestion.
    """
    from services.vector_store import get_vector_store_service
    from pathlib import Path

    try:
        vector_store = get_vector_store_service()
        db_stats = vector_store.get_collection_stats()
        db_status = "ok"
    except Exception as e:
        db_stats = {}
        db_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "phase": "1 - Ingestion Core",
        "embedding_model": settings.EMBEDDING_MODEL_NAME,
        "vector_db": {
            "status": db_status,
            **db_stats,
        },
        "directories": {
            "uploads": str(Path(settings.UPLOAD_DIR).resolve()),
            "chroma_db": str(Path(settings.CHROMA_PERSIST_DIR).resolve()),
        },
    }


@app.get("/", include_in_schema=False)
def root() -> Dict[str, str]:
    """Redirect hint — tells users where to find the docs."""
    return {
        "message": "DocuIntel API is running.",
        "docs": "http://localhost:8000/docs",
        "health": "http://localhost:8000/health",
    }
