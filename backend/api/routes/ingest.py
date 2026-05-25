"""
api/routes/ingest.py
---------------------
Handles PDF upload and ingestion via POST /ingest.

Flow:
  1. Receive uploaded PDF file
  2. Save to disk (temp storage)
  3. Extract text per page (PyMuPDF)
  4. Split into overlapping chunks (RecursiveCharacterTextSplitter)
  5. Generate BGE embeddings for each chunk
  6. Store chunks + embeddings in ChromaDB
  7. Return ingestion summary

Error handling:
  - Non-PDF files → 400 Bad Request
  - Corrupted PDFs → 422 Unprocessable Entity
  - PDFs with no text → 200 with warning (Phase 3 will handle OCR)
  - Storage errors → 500 Internal Server Error
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, File, UploadFile, HTTPException
from pydantic import BaseModel

from config import settings
from ingestion.pdf_processor import extract_text_from_pdf, PDFDocument
from ingestion.chunker import chunk_pdf_document
from services.embedding_service import get_embedding_service
from services.vector_store import get_vector_store_service
from services.bm25_service import get_bm25_service   # Phase 3: mark stale after ingest
from utils.logger import get_logger, Timer

logger = get_logger(__name__)
router = APIRouter(prefix="/ingest", tags=["Ingestion"])


# ── Response Models ───────────────────────────────────────────────────────────

class PageStats(BaseModel):
    """Per-page extraction statistics included in the response."""
    page_num: int
    char_count: int
    is_empty: bool


class IngestResponse(BaseModel):
    """
    Response returned after successful ingestion.
    Designed to be informative — tells you exactly what happened.
    """
    status: str                       # "success" or "warning"
    message: str                      # Human-readable summary
    filename: str
    doc_id: str
    total_pages: int
    extractable_pages: int
    total_chunks: int
    chunks_stored: int
    needs_ocr: bool                   # True if majority of pages were empty
    upload_timestamp: str
    processing_time_ms: float
    vector_store_total: int           # Total chunks in ChromaDB after ingestion
    page_stats: List[PageStats]       # Per-page breakdown


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=IngestResponse,
    summary="Upload and ingest a PDF",
    description=(
        "Accepts a PDF file, extracts text, chunks it, generates embeddings, "
        "and stores everything in ChromaDB. Returns a detailed ingestion summary."
    ),
)
def ingest_pdf(file: UploadFile = File(..., description="PDF file to ingest")) -> IngestResponse:
    """
    POST /ingest

    Accepts multipart/form-data with a 'file' field containing a PDF.
    Returns ingestion summary on success.
    """
    overall_timer = Timer().__enter__()
    upload_timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Ingestion request received",
        extra={"file": file.filename, "content_type": file.content_type},
    )

    # ── Step 1: Validate file type ────────────────────────────────────────────
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF files are accepted. Got: {file.filename}",
        )

    # ── Step 2: Save uploaded file to disk ────────────────────────────────────
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Use timestamp prefix to avoid collisions with same-named files
    safe_filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    save_path = upload_dir / safe_filename

    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error("Failed to save uploaded file", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    finally:
        file.file.close()

    logger.info("File saved", extra={"path": str(save_path)})

    # ── Step 3: Extract text from PDF ─────────────────────────────────────────
    try:
        with Timer() as extract_timer:
            pdf_doc = extract_text_from_pdf(str(save_path))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("PDF extraction failed", extra={"error": str(e), "file": file.filename})
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {str(e)}")

    logger.info(
        "Text extraction complete",
        extra={
            "file": file.filename,
            "pages": pdf_doc.total_pages,
            "extractable": len(pdf_doc.extractable_pages),
            "elapsed_ms": extract_timer.elapsed_ms,
        },
    )

    # ── Step 4: Chunk the extracted text ──────────────────────────────────────
    try:
        with Timer() as chunk_timer:
            chunks = chunk_pdf_document(pdf_doc, upload_timestamp)
    except Exception as e:
        logger.error("Chunking failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Chunking failed: {str(e)}")

    if not chunks:
        # This happens with fully scanned PDFs — no text extracted
        # Return a warning (Phase 3 will handle OCR for these cases)
        return IngestResponse(
            status="warning",
            message=(
                "No text could be extracted from this PDF. "
                "It may be a scanned document. OCR support coming in Phase 3."
            ),
            filename=file.filename,
            doc_id=chunks[0].metadata["doc_id"] if chunks else "unknown",
            total_pages=pdf_doc.total_pages,
            extractable_pages=0,
            total_chunks=0,
            chunks_stored=0,
            needs_ocr=True,
            upload_timestamp=upload_timestamp,
            processing_time_ms=0,
            vector_store_total=0,
            page_stats=_build_page_stats(pdf_doc),
        )

    logger.info(
        "Chunking complete",
        extra={
            "file": file.filename,
            "chunks": len(chunks),
            "elapsed_ms": chunk_timer.elapsed_ms,
        },
    )

    # ── Step 5: Generate embeddings ───────────────────────────────────────────
    try:
        with Timer() as embed_timer:
            embedding_service = get_embedding_service()
            chunk_texts = [chunk.page_content for chunk in chunks]
            embeddings = embedding_service.embed_documents(chunk_texts)
    except Exception as e:
        logger.error("Embedding generation failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Embedding failed: {str(e)}")

    logger.info(
        "Embeddings generated",
        extra={
            "count": len(embeddings),
            "dim": len(embeddings[0]) if embeddings else 0,
            "elapsed_ms": embed_timer.elapsed_ms,
        },
    )

    # ── Step 6: Store in ChromaDB ─────────────────────────────────────────────
    try:
        with Timer() as store_timer:
            vector_store = get_vector_store_service()
            stored_count = vector_store.add_documents(chunks, embeddings)
            stats = vector_store.get_collection_stats()
    except Exception as e:
        logger.error("ChromaDB storage failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Storage failed: {str(e)}")

    logger.info(
        "Storage complete",
        extra={
            "stored": stored_count,
            "collection_total": stats["total_chunks"],
            "elapsed_ms": store_timer.elapsed_ms,
        },
    )

    # ── Step 7: Mark BM25 index stale ────────────────────────────────────────
    # The BM25 index must be rebuilt to include the new chunks.
    # mark_stale() is cheap (just sets a flag).  The actual rebuild happens
    # lazily on the next /ask call that triggers a retrieval.
    try:
        get_bm25_service().mark_stale()
    except Exception as e:
        # Never let BM25 housekeeping break a successful ingest
        logger.warning(
            "BM25 mark_stale failed — index may be stale until next restart",
            extra={"error": str(e)},
        )

    # ── Step 8: Build response ────────────────────────────────────────────────
    overall_timer.__exit__(None, None, None)

    doc_id = chunks[0].metadata["doc_id"]

    logger.info(
        "Ingestion complete ✓",
        extra={
            "file": file.filename,
            "doc_id": doc_id,
            "chunks": stored_count,
            "total_ms": overall_timer.elapsed_ms,
        },
    )

    return IngestResponse(
        status="success",
        message=f"Successfully ingested '{file.filename}' — {stored_count} chunks stored.",
        filename=file.filename,
        doc_id=doc_id,
        total_pages=pdf_doc.total_pages,
        extractable_pages=len(pdf_doc.extractable_pages),
        total_chunks=len(chunks),
        chunks_stored=stored_count,
        needs_ocr=pdf_doc.needs_ocr,
        upload_timestamp=upload_timestamp,
        processing_time_ms=overall_timer.elapsed_ms,
        vector_store_total=stats["total_chunks"],
        page_stats=_build_page_stats(pdf_doc),
    )


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_page_stats(pdf_doc: PDFDocument) -> List[PageStats]:
    """Builds a list of per-page stats for the response."""
    return [
        PageStats(
            page_num=page.page_num,
            char_count=page.char_count,
            is_empty=page.is_empty,
        )
        for page in pdf_doc.pages
    ]
