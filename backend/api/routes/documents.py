"""
api/routes/documents.py
-----------------------
Feature 2 addition: GET /{doc_id}/file

Serves the original uploaded PDF for a given doc_id.

How it finds the file:
  1. Query ChromaDB for any chunk whose doc_id matches the requested doc_id.
  2. Read the 'filename' from that chunk's metadata.
     This is the timestamped filename saved to disk by ingest.py, e.g.
     "20260526_202541_sample.pdf".
  3. Construct full path: UPLOAD_DIR / filename.
  4. Return a FileResponse (FastAPI streams the file directly — no buffering).

Why this approach:
  - Zero new storage, zero new database.
  - The filename in chunk metadata IS the actual filename on disk.
  - ingest.py saves: f"{timestamp}_{original_name}" → uses that as pdf_doc.filename
    → chunker stores it as metadata["filename"] → ChromaDB persists it.
  - FileResponse sets correct Content-Type and Content-Disposition headers
    so browsers can display the PDF inline.

The existing GET / endpoint is completely unchanged.
"""

from pathlib import Path
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.vector_store import get_vector_store_service
from config import settings

router = APIRouter()


# ── Existing endpoint (unchanged) ─────────────────────────────────────────────

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


# ── Feature 2: serve the original PDF file ────────────────────────────────────

@router.get(
    "/{doc_id}/file",
    summary="Download the original PDF for a document",
    description=(
        "Returns the original uploaded PDF file for the given doc_id. "
        "The file is streamed directly from disk with Content-Type: application/pdf, "
        "suitable for inline display in a browser PDF viewer."
    ),
    response_class=FileResponse,
)
async def get_document_file(doc_id: str):
    """
    GET /api/v1/documents/{doc_id}/file

    Returns the raw PDF file bytes with Content-Type: application/pdf.
    The frontend uses this URL directly as the `file` prop for react-pdf.
    """
    vector_store = get_vector_store_service()

    # ── Step 1: Look up the filename from ChromaDB metadata ───────────────────
    # We only need ONE chunk from this document — all chunks share the same
    # filename.  get_all_documents() returns everything; for efficiency we
    # query ChromaDB directly with a where filter.
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

    # ── Step 2: Resolve the file path ─────────────────────────────────────────
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

    # ── Step 3: Stream the file ───────────────────────────────────────────────
    # media_type="application/pdf" tells the browser to display inline.
    # filename in Content-Disposition uses the original user-facing name
    # (strip the timestamp prefix for a cleaner display name).
    display_name = _strip_timestamp_prefix(filename)

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=display_name,
        headers={
            # Allow cross-origin requests from the Vite dev server
            "Access-Control-Allow-Origin": "*",
            # Tell browser to display inline (not force-download)
            "Content-Disposition": f'inline; filename="{display_name}"',
        },
    )


def _strip_timestamp_prefix(filename: str) -> str:
    """
    Removes the YYYYMMDD_HHMMSS_ prefix added by ingest.py to avoid collisions.

    "20260526_202541_my_report.pdf"  →  "my_report.pdf"
    "my_report.pdf"                  →  "my_report.pdf"  (unchanged if no prefix)
    """
    import re
    match = re.match(r"^\d{8}_\d{6}_(.+)$", filename)
    if match:
        return match.group(1)
    return filename
