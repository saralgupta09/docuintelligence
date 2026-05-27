from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "DocuIntel"
    APP_VERSION: str = "0.4.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    UPLOAD_DIR: str = "./data/uploads"
    CHROMA_PERSIST_DIR: str = "./data/chroma_db"
    CONVERSATION_STORE_PATH: str = "./data/conversations.json"

    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_BATCH_SIZE: int = 32

    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150

    CHROMA_COLLECTION_NAME: str = "documents"

    RETRIEVAL_TOP_K: int = 5
    VECTOR_TOP_K: int = 10
    BM25_TOP_K: int = 10
    SEMANTIC_WEIGHT: float = 0.6
    BM25_WEIGHT: float = 0.4

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    ENABLE_QUERY_REWRITING: bool = True
    MAX_MEMORY_TURNS: int = 5

    OCR_ENABLED: bool = True
    OCR_LANGUAGE: str = "eng"
    OCR_DPI: int = 300

    RERANK_TOP_N: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def ensure_directories() -> None:
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CONVERSATION_STORE_PATH).parent.mkdir(parents=True, exist_ok=True)    