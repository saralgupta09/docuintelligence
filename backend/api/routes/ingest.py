"""
api/routes/ingest.py
---------------------
Handles PDF upload and ingestion via POST /ingest.

Phase 4 change:
  The early-return warning block "no text — OCR coming in Phase 3" has been
  replaced with proper behaviour: because pdf_processor.py now applies OCR
  automatically to empty pages, 'chunks' will only be empty if OCR is
  disabled AND the PDF has no text layer, OR if OCR itself found nothing.
  In that case a clear warning is returned, identical in shape to before.

  Two new response fields are added:
    ocr_pages_count  — number of pages whose text came from OCR
    ocr_applied      — True if any page used OCR

  The /ingest endpoint URL, method, request shape, and all existing response
  fields are unchanged.  /api/v1/ask is not touched.
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
    ocr_applied: bool = False       # Phase 4: was OCR used for this page?


class IngestResponse(BaseModel):
    """
    Response returned after successful ingestion.
    All Phase 3 fields are preserved.  Two new Phase 4 fields are added.
    """
    status: str
    message: str
    filename: str
    doc_id: str
    total_pages: int
    extractable_pages: int
    total_chunks: int
    chunks_stored: int
    needs_ocr: bool
    upload_timestamp: str
    processing_time_ms: float
    vector_store_total: int
    page_stats: List[PageStats]
    # ── Phase 4 additions ─────────────────────────────────────────────────────
    ocr_pages_count: int = 0        # Number of pages that went through OCR
    ocr_applied: bool = False       # True if any page used OCR


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=IngestResponse,
    summary="Upload and ingest a PDF",
    description=(
        "Accepts a PDF file, extracts text (with automatic OCR for scanned pages), "
        "chunks it, generates embeddings, and stores everything in ChromaDB."
    ),
)
def ingest_pdf(file: UploadFile = File(..., description="PDF file to ingest")) -> IngestResponse:
    """
    POST /ingest

    Accepts multipart/form-data with a 'file' field containing a PDF.
    Scanned/image-based PDFs are handled automatically via pytesseract OCR
    when OCR_ENABLED=true (default).
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
            "ocr_pages": pdf_doc.ocr_page_count,
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
        # Reaches here only when:
        #   (a) OCR_ENABLED=false  AND  the PDF has no text layer, OR
        #   (b) OCR ran but extracted nothing (very poor scan quality)
        ocr_note = (
            "OCR was attempted but found no text. "
            "The scan quality may be too poor, or OCR_ENABLED=false."
            if getattr(settings, "OCR_ENABLED", True)
            else "OCR is disabled (OCR_ENABLED=false). "
                 "Enable it to process scanned PDFs."
        )
        return IngestResponse(
            status="warning",
            message=f"No text could be extracted from '{file.filename}'. {ocr_note}",
            filename=file.filename,
            doc_id="unknown",
            total_pages=pdf_doc.total_pages,
            extractable_pages=0,
            total_chunks=0,
            chunks_stored=0,
            needs_ocr=pdf_doc.needs_ocr,
            upload_timestamp=upload_timestamp,
            processing_time_ms=0.0,
            vector_store_total=0,
            page_stats=_build_page_stats(pdf_doc),
            ocr_pages_count=pdf_doc.ocr_page_count,
            ocr_applied=pdf_doc.ocr_page_count > 0,
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
    ocr_pages = pdf_doc.ocr_page_count

    logger.info(
        "Ingestion complete ✓",
        extra={
            "file": file.filename,
            "doc_id": doc_id,
            "chunks": stored_count,
            "ocr_pages": ocr_pages,
            "total_ms": overall_timer.elapsed_ms,
        },
    )

    return IngestResponse(
        status="success",
        message=f"Successfully ingested '{file.filename}' — {stored_count} chunks stored."
                + (f" ({ocr_pages} page(s) processed via OCR)" if ocr_pages else ""),
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
        ocr_pages_count=ocr_pages,
        ocr_applied=ocr_pages > 0,
    )


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_page_stats(pdf_doc: PDFDocument) -> List[PageStats]:
    """Builds per-page stats for the response. Phase 4: adds ocr_applied."""
    return [
        PageStats(
            page_num=page.page_num,
            char_count=page.char_count,
            is_empty=page.is_empty,
            ocr_applied=page.ocr_applied,       # Phase 4
        )
        for page in pdf_doc.pages
    ]
