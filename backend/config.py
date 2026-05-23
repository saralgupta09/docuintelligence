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
    APP_VERSION: str = "0.1.0"
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

    # ── Retrieval (used in later phases, defined here for completeness) ───────
    RETRIEVAL_TOP_K: int = 20
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
