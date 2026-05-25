"""
services/vector_store.py
-------------------------
Wraps ChromaDB for persistent local vector storage.

Architecture decisions:
  - Single collection for all documents (filtered by metadata at retrieval time)
  - Persistent storage to disk (survives server restarts)
  - Cosine similarity space (matches normalized BGE embeddings)
  - IDs are the chunk_id from metadata (enables upsert / deduplication)

ChromaDB storage location:
  Configured via CHROMA_PERSIST_DIR in .env (default: ./data/chroma_db)
  ChromaDB creates this directory and manages its own SQLite file inside.

Phase 1 implements: add_documents, get_collection_stats
Phase 2 adds:       similarity_search, delete_document
Phase 4 adds:       metadata filtering for hybrid retrieval
"""

from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_core.documents import Document

from config import settings
from utils.logger import get_logger, Timer

logger = get_logger(__name__)


class VectorStoreService:
    """
    Manages document storage and retrieval in ChromaDB.

    ChromaDB stores:
    - The text content of each chunk
    - The embedding vector for each chunk
    - Metadata (filename, page_num, chunk_id, etc.)

    All three are stored together and can be retrieved together.
    """

    def __init__(self) -> None:
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    def _get_client(self) -> chromadb.ClientAPI:
        """
        Lazy-initializes the ChromaDB persistent client.
        PersistentClient saves data to disk between server restarts.
        """
        if self._client is None:
            logger.info(
                "Initializing ChromaDB client",
                extra={"persist_dir": settings.CHROMA_PERSIST_DIR},
            )
            self._client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(
                    anonymized_telemetry=False,  # Disable telemetry
                    allow_reset=True,            # Allow collection reset (useful for debugging)
                ),
            )
        return self._client

    def _get_collection(self) -> chromadb.Collection:
        """
        Gets or creates the main document collection.
        Uses cosine distance (appropriate for normalized BGE embeddings).
        """
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                metadata={
                    "hnsw:space": "cosine",           # Cosine similarity
                    "hnsw:construction_ef": 100,      # Index build quality
                    "hnsw:search_ef": 100,             # Query search quality
                    "description": "DocuIntel document chunks",
                },
            )
            logger.info(
                "ChromaDB collection ready",
                extra={
                    "collection": settings.CHROMA_COLLECTION_NAME,
                    "count": self._collection.count(),
                },
            )
        return self._collection

    def add_documents(
        self,
        documents: List[Document],
        embeddings: List[List[float]],
    ) -> int:
        """
        Stores chunks and their pre-computed embeddings in ChromaDB.

        We pass embeddings explicitly (instead of letting ChromaDB embed them)
        because we use a custom BGE model that ChromaDB doesn't know about.

        Args:
            documents:  List of Document objects (page_content + metadata)
            embeddings: Pre-computed embedding vectors (same length as documents)

        Returns:
            Number of chunks successfully stored.

        Raises:
            ValueError: If documents and embeddings lists have different lengths.
        """
        if not documents:
            logger.warning("add_documents called with empty list")
            return 0

        if len(documents) != len(embeddings):
            raise ValueError(
                f"Mismatch: {len(documents)} documents but {len(embeddings)} embeddings"
            )

        collection = self._get_collection()

        # ChromaDB requires parallel lists: ids, embeddings, documents, metadatas
        ids: List[str] = []
        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for doc in documents:
            chunk_id = doc.metadata.get("chunk_id")
            if not chunk_id:
                raise ValueError(f"Document missing 'chunk_id' in metadata: {doc.metadata}")

            ids.append(chunk_id)
            texts.append(doc.page_content)

            # ChromaDB metadata values must be str, int, float, or bool
            # Filter out any None values (ChromaDB rejects them)
            clean_metadata = {
                k: v for k, v in doc.metadata.items()
                if isinstance(v, (str, int, float, bool))
            }
            metadatas.append(clean_metadata)

        logger.info(
            "Storing chunks in ChromaDB",
            extra={"count": len(ids), "collection": settings.CHROMA_COLLECTION_NAME},
        )

        with Timer() as t:
            # upsert = insert OR update if chunk_id already exists
            # This prevents duplicates if the same PDF is uploaded twice
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )

        final_count = collection.count()
        logger.info(
            "Chunks stored successfully",
            extra={
                "stored": len(ids),
                "collection_total": final_count,
                "elapsed_ms": t.elapsed_ms,
            },
        )

        return len(ids)

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Returns summary statistics about the vector store.
        Used by the health endpoint and the ingest response.
        """
        collection = self._get_collection()
        count = collection.count()

        stats: Dict[str, Any] = {
            "collection_name": settings.CHROMA_COLLECTION_NAME,
            "total_chunks": count,
            "persist_dir": settings.CHROMA_PERSIST_DIR,
        }

        # If there are documents, sample the most recent ones
        if count > 0:
            # Peek at up to 5 documents to show what's stored
            sample = collection.peek(limit=5)
            unique_files = list(set(
                m.get("filename", "unknown")
                for m in (sample.get("metadatas") or [])
            ))
            stats["sample_documents"] = unique_files

        return stats

    def document_exists(self, doc_id: str) -> bool:
        """
        Returns True if any chunk with this doc_id exists in ChromaDB.
        Useful for checking if a document has already been ingested.
        """
        collection = self._get_collection()
        # ChromaDB where filter: match any chunk with this doc_id
        results = collection.get(where={"doc_id": {"$eq": doc_id}})
        return len(results["ids"]) > 0

    def get_all_documents(self) -> list:
        """
        Returns ALL stored chunks as a list of dicts.

        Used by the /api/v1/documents/ endpoint to build the document list,
        and by BM25Service to build its keyword index.
        Each dict has the shape:
          {
            "chunk_id": str,
            "text":     str,
            "filename": str,
            "page_num": int,
            "doc_id":   str,
            "metadata": dict,
          }

        ChromaDB's .get() without a 'where' filter returns every document in
        the collection.  We pass include=["documents", "metadatas"] to avoid
        loading embeddings (we don't need them here).

        Returns [] if the collection is empty or on any error.
        """
        try:
            collection = self._get_collection()
            count = collection.count()

            if count == 0:
                return []

            # Fetch all documents — no filter, no embeddings
            raw = collection.get(include=["documents", "metadatas"])

            ids = raw.get("ids", [])
            texts = raw.get("documents", []) or []
            metadatas = raw.get("metadatas", []) or []

            docs = []
            for chunk_id, text, metadata in zip(ids, texts, metadatas):
                docs.append(
                    {
                        "chunk_id": chunk_id,
                        "text": text or "",
                        "filename": metadata.get("filename", "unknown"),
                        "page_num": int(metadata.get("page_num", 0)),
                        "doc_id": metadata.get("doc_id", "unknown"),
                        "metadata": metadata,
                    }
                )

            logger.info(
                "get_all_documents complete",
                extra={"total": len(docs)},
            )

            return docs

        except Exception as e:
            logger.error(
                "get_all_documents failed",
                extra={"error": str(e)},
            )
            return []

    def delete_document(self, doc_id: str) -> int:
        """
        Deletes all chunks for a given doc_id.
        Returns the number of chunks deleted.
        """
        collection = self._get_collection()
        before = collection.count()
        collection.delete(where={"doc_id": {"$eq": doc_id}})
        after = collection.count()
        deleted = before - after
        logger.info(
            "Document deleted from ChromaDB",
            extra={"doc_id": doc_id, "chunks_deleted": deleted},
        )
        return deleted


# Module-level singleton — shared across all requests
_vector_store_service: VectorStoreService | None = None


def get_vector_store_service() -> VectorStoreService:
    """
    Returns the shared VectorStoreService instance.
    Call this function everywhere instead of creating new instances.
    """
    global _vector_store_service
    if _vector_store_service is None:
        _vector_store_service = VectorStoreService()
    return _vector_store_service