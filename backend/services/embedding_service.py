"""
services/embedding_service.py
------------------------------
Wraps BAAI/bge-small-en-v1.5 for generating text embeddings locally.

Why BGE-small?
  - Completely free (HuggingFace, runs locally, no API calls)
  - Small model (~130MB) — fast on CPU, no GPU required
  - Good quality for retrieval tasks (outperforms OpenAI ada-002 on BEIR)
  - Normalization gives proper cosine similarity scores

IMPORTANT BGE quirk:
  BGE models use DIFFERENT prefixes for queries vs documents:
  - Queries:    "Represent this sentence for searching relevant passages: <query>"
  - Documents:  NO prefix needed (embed raw text)

  If you forget the query prefix, retrieval quality drops noticeably.
  This service handles the prefix automatically.

First run:
  The model (~130MB) is downloaded from HuggingFace on first use.
  Subsequent runs use the local cache (~/.cache/huggingface/).
"""

from typing import List
from functools import lru_cache

from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_core.documents import Document

from config import settings
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


class EmbeddingService:
    """
    Manages BGE-small embeddings for document chunks and search queries.

    Usage:
        service = EmbeddingService()
        doc_vectors = service.embed_documents(["text 1", "text 2"])
        query_vector = service.embed_query("what is the revenue?")
    """

    def __init__(self) -> None:
        self._model: HuggingFaceBgeEmbeddings | None = None

    def _get_model(self) -> HuggingFaceBgeEmbeddings:
        """
        Lazy initialization — loads the model on first use.
        This avoids a 5-10 second delay at startup.
        """
        if self._model is None:
            logger.info(
                "Loading BGE embedding model (first use — may take ~30s to download)",
                extra={"model": settings.EMBEDDING_MODEL_NAME, "device": settings.EMBEDDING_DEVICE},
            )
            with Timer() as t:
                self._model = HuggingFaceBgeEmbeddings(
                    model_name=settings.EMBEDDING_MODEL_NAME,
                    model_kwargs={"device": settings.EMBEDDING_DEVICE},
                    encode_kwargs={
                        "normalize_embeddings": True,  # Required for cosine similarity
                        "batch_size": settings.EMBEDDING_BATCH_SIZE,
                    },
                    # This prefix is automatically prepended to QUERY strings
                    # (not documents). BGE requires it for accurate retrieval.
                    query_instruction="Represent this sentence for searching relevant passages: ",
                )
            logger.info(
                "BGE model loaded",
                extra={"model": settings.EMBEDDING_MODEL_NAME, "load_time_ms": t.elapsed_ms},
            )
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a list of document texts.
        Used at ingestion time when storing chunks in ChromaDB.

        Args:
            texts: List of raw text strings (chunk content)

        Returns:
            List of embedding vectors (list of floats, length 384 for bge-small)
        """
        if not texts:
            return []

        logger.info(
            "Generating document embeddings",
            extra={"count": len(texts), "model": settings.EMBEDDING_MODEL_NAME},
        )

        with Timer() as t:
            model = self._get_model()
            embeddings = model.embed_documents(texts)

        logger.info(
            "Document embeddings complete",
            extra={
                "count": len(embeddings),
                "vector_dim": len(embeddings[0]) if embeddings else 0,
                "elapsed_ms": t.elapsed_ms,
            },
        )
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        """
        Generates an embedding for a search query.
        Automatically prepends the BGE query instruction prefix.
        Used at retrieval time when searching ChromaDB.

        Args:
            query: The user's question or search string

        Returns:
            Single embedding vector (list of floats)
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")

        with Timer() as t:
            model = self._get_model()
            embedding = model.embed_query(query)

        logger.debug(
            "Query embedding generated",
            extra={"query_preview": query[:60], "elapsed_ms": t.elapsed_ms},
        )
        return embedding

    def get_embedding_dimension(self) -> int:
        """
        Returns the vector dimension of this model.
        bge-small: 384 dimensions
        bge-large: 1024 dimensions
        """
        test_embedding = self.embed_query("dimension check")
        return len(test_embedding)


# Module-level singleton — shared across all requests
# This avoids reloading the model on every API call
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """
    Returns the shared EmbeddingService instance.
    Call this function everywhere instead of creating new instances.
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
