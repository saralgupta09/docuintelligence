"""
api/routes/documents.py
-----------------------
Deletion feature addition: DELETE /{doc_id}

Removes a document completely:
  1. Looks up the timestamped filename from ChromaDB metadata
     (same lookup used by GET /{doc_id}/file — reuses the same pattern).
  2. Deletes the PDF file from disk.
  3. Deletes all ChromaDB chunks for this doc_id via vector_store.delete_document().
  4. Marks the BM25 index stale so the next /ask rebuilds it.

All existing endpoints (GET / and GET /{doc_id}/file) are completely unchanged.
"""

import re
from pathlib import Path
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.vector_store import get_vector_store_service
from services.bm25_service import get_bm25_service
from config import settings

router = APIRouter()


# ── GET / — list all documents ────────────────────────────────────────────────

@router.get("/")
async def get_documents():
    try:
        vector_store = get_vector_store_service()
        chunks = vector_store.get_all_documents()

        docs_map = defaultdict(
            lambda: {
                "doc_id": "",
                "filename": "",
                "total_pages": 0,
                "chunk_count": 0,
                "ocr_applied": False,
                "upload_timestamp": "",
            }
        )

        for chunk in chunks:
            doc_id = chunk.get("doc_id")
            metadata = chunk.get("metadata", {})

            docs_map[doc_id]["doc_id"] = doc_id
            docs_map[doc_id]["filename"] = chunk.get("filename", "unknown")
            docs_map[doc_id]["chunk_count"] += 1

            page = chunk.get("page_num", 0)
            docs_map[doc_id]["total_pages"] = max(
                docs_map[doc_id]["total_pages"], page
            )

            docs_map[doc_id]["ocr_applied"] = metadata.get("ocr_applied", False)
            docs_map[doc_id]["upload_timestamp"] = metadata.get("upload_timestamp", "")

        documents = list(docs_map.values())
        return {"documents": documents, "total": len(documents)}

    except Exception as e:
        return {"documents": [], "total": 0, "error": str(e)}


# ── GET /{doc_id}/file — stream the original PDF ─────────────────────────────

@router.get(
    "/{doc_id}/file",
    summary="Download the original PDF for a document",
    response_class=FileResponse,
)
async def get_document_file(doc_id: str):
    """
    GET /api/v1/documents/{doc_id}/file
    Returns the raw PDF file bytes with Content-Type: application/pdf.
    """
    vector_store = get_vector_store_service()

    try:
        collection = vector_store._get_collection()
        results = collection.get(
            where={"doc_id": {"$eq": doc_id}},
            limit=1,
            include=["metadatas"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query ChromaDB: {str(e)}",
        )

    if not results["ids"]:
        raise HTTPException(
            status_code=404,
            detail=f"No document found with doc_id '{doc_id}'.",
        )

    metadata = results["metadatas"][0]
    filename = metadata.get("filename")

    if not filename:
        raise HTTPException(
            status_code=500,
            detail=f"Document '{doc_id}' has no filename in metadata.",
        )

    upload_dir = Path(settings.UPLOAD_DIR)
    file_path = upload_dir / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"PDF file '{filename}' not found on disk. "
                "It may have been manually deleted from the uploads directory."
            ),
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"'{filename}' exists but is not a regular file.",
        )

    display_name = _strip_timestamp_prefix(filename)

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=display_name,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Content-Disposition": f'inline; filename="{display_name}"',
        },
    )


# ── DELETE /{doc_id} — remove document completely ────────────────────────────

@router.delete(
    "/{doc_id}",
    summary="Delete a document and all associated data",
    description=(
        "Removes all ChromaDB chunks for the document, deletes the uploaded PDF "
        "file from disk, and marks the BM25 index stale. "
        "Returns 404 if the doc_id is not found in ChromaDB."
    ),
)
async def delete_document(doc_id: str):
    """
    DELETE /api/v1/documents/{doc_id}

    Steps:
      1. Look up the stored filename from ChromaDB (one chunk, metadatas only).
      2. Delete all ChromaDB chunks for this doc_id.
      3. Delete the PDF file from disk (gracefully skips if already missing).
      4. Mark BM25 index stale so the next /ask call rebuilds it.
    """
    vector_store = get_vector_store_service()

    # ── Step 1: Resolve filename before deleting anything ─────────────────────
    # We need the filename BEFORE we delete the chunks, because after deletion
    # the metadata is gone and we can no longer find which file to remove.
    try:
        collection = vector_store._get_collection()
        results = collection.get(
            where={"doc_id": {"$eq": doc_id}},
            limit=1,
            include=["metadatas"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query ChromaDB: {str(e)}",
        )

    if not results["ids"]:
        raise HTTPException(
            status_code=404,
            detail=f"No document found with doc_id '{doc_id}'.",
        )

    filename = results["metadatas"][0].get("filename")

    # ── Step 2: Delete all ChromaDB chunks ────────────────────────────────────
    try:
        chunks_deleted = vector_store.delete_document(doc_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete chunks from ChromaDB: {str(e)}",
        )

    # ── Step 3: Delete the PDF file from disk ─────────────────────────────────
    file_deleted = False
    file_warning = None

    if filename:
        file_path = Path(settings.UPLOAD_DIR) / filename
        try:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                file_deleted = True
            else:
                # Not an error — the file may have been manually removed already.
                file_warning = (
                    f"PDF '{filename}' was not found on disk; "
                    "it may have been manually deleted."
                )
        except Exception as e:
            # Log but do not roll back — chunks are already gone.
            file_warning = f"Chunks deleted but could not remove file '{filename}': {str(e)}"
    else:
        file_warning = "No filename stored in metadata; file on disk was not removed."

    # ── Step 4: Mark BM25 index stale ────────────────────────────────────────
    try:
        get_bm25_service().mark_stale()
    except Exception:
        # Never let BM25 housekeeping break a successful deletion.
        pass

    return {
        "status": "deleted",
        "doc_id": doc_id,
        "chunks_deleted": chunks_deleted,
        "file_deleted": file_deleted,
        "file_warning": file_warning,
    }


# ── Helper ────────────────────────────────────────────────────────────────────

def _strip_timestamp_prefix(filename: str) -> str:
    """
    Removes the YYYYMMDD_HHMMSS_ prefix added by ingest.py.
    "20260526_202541_my_report.pdf"  →  "my_report.pdf"
    """
    match = re.match(r"^\d{8}_\d{6}_(.+)$", filename)
    if match:
        return match.group(1)
    return filename