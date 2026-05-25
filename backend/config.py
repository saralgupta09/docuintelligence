"""
config.py
---------
Central configuration for the DocuIntel backend.
All settings are loaded from environment variables or the .env file.
Pydantic BaseSettings handles validation and type coercion automatically.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "DocuIntel"
    APP_VERSION: str = "0.4.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Paths ────────────────────────────────────────────────────────────────
    # All paths are relative to the project root (one level above backend/)
    UPLOAD_DIR: str = "./data/uploads"
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"

    # ── Embedding model ──────────────────────────────────────────────────────
    # Using bge-small for speed and zero cost (local HuggingFace model)
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DEVICE: str = "cpu"          # Change to "cuda" if GPU available
    EMBEDDING_BATCH_SIZE: int = 32

    # ── Chunking ─────────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    # One collection for the entire app (documents filtered by metadata)
    CHROMA_COLLECTION_NAME: str = "documents"

    # ── Retrieval (Phase 2 — preserved for backward compat) ──────────────────
    RETRIEVAL_TOP_K: int = 5           # Chunks retrieved per question (legacy)

    # ── Retrieval (Phase 3 — hybrid) ─────────────────────────────────────────
    # VECTOR_TOP_K: how many candidates to pull from ChromaDB before merging
    VECTOR_TOP_K: int = 10
    # BM25_TOP_K: how many candidates to score via BM25 before merging
    BM25_TOP_K: int = 10
    # Weights for the hybrid score: SEMANTIC_WEIGHT + BM25_WEIGHT should = 1.0
    # Higher SEMANTIC_WEIGHT → favours conceptual similarity
    # Higher BM25_WEIGHT → favours exact keyword matches
    SEMANTIC_WEIGHT: float = 0.6
    BM25_WEIGHT: float = 0.4

    # ── LLM (Phase 2) ────────────────────────────────────────────────────────
    # Free tier: 1,500 requests/day | Get key: https://aistudio.google.com/app/apikey
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # ── Query rewriting (Phase 3) ─────────────────────────────────────────────
    # When True: a lightweight Gemini call converts vague questions into
    # search-friendly standalone queries before retrieval.
    # When False: retrieval_query = question (pass-through, zero extra API calls).
    # Toggle off to conserve free-tier quota: ENABLE_QUERY_REWRITING=false
    ENABLE_QUERY_REWRITING: bool = True

    # ── Conversation memory (Phase 3) ─────────────────────────────────────────
    # How many prior turns to inject into the generate prompt.
    # Each "turn" = one user question + one assistant answer.
    # Higher values → better continuity, higher token cost.
    MAX_MEMORY_TURNS: int = 5

    # ── OCR (Phase 4) ────────────────────────────────────────────────────────
    # OCR_ENABLED: master switch for the OCR pipeline.
    #   true  — pages with no extractable text are automatically OCR'd
    #            using pytesseract (requires tesseract binary installed).
    #   false — scanned pages are skipped; same behaviour as Phase 3.
    OCR_ENABLED: bool = True

    # OCR_LANGUAGE: Tesseract language code for the OCR engine.
    #   "eng" is always available.  For other languages install the
    #   corresponding data pack:
    #     sudo apt-get install tesseract-ocr-<lang>
    #   Multiple languages: "eng+fra" (English + French)
    OCR_LANGUAGE: str = "eng"

    # OCR_DPI: render resolution used when converting PDF pages to images.
    #   300 is the standard for OCR — good balance of accuracy and speed.
    #   150 is faster but degrades on small fonts.
    #   400+ gives marginal gain with much higher memory use.
    OCR_DPI: int = 300

    # ── Future phases ─────────────────────────────────────────────────────────
    RERANK_TOP_N: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow extra fields so future phases can add keys without errors
        extra = "ignore"


# Single shared instance — import this everywhere
settings = Settings()


def ensure_directories() -> None:
    """Create required directories if they don't exist."""
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
