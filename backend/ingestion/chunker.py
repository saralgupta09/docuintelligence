"""
ingestion/chunker.py
---------------------
Splits PDF page text into overlapping chunks suitable for embedding and retrieval.

Phase 4 change (minimal):
  build_chunk_metadata() now receives and stores the 'ocr_applied' flag from
  PageContent.ocr_applied so every chunk in ChromaDB records whether its text
  came from direct extraction or OCR.  This enables filtering and debugging.

All other logic is unchanged from Phase 3.
"""

from datetime import datetime, timezone
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import settings
from ingestion.pdf_processor import PDFDocument
from utils.logger import get_logger

logger = get_logger(__name__)


def create_doc_id(filename: str) -> str:
    """
    Creates a stable, filesystem-safe document ID from a filename.
    Unchanged from Phase 1.
    """
    import re
    doc_id = re.sub(r"[^a-z0-9]+", "_", filename.lower()).strip("_")
    return doc_id


def chunk_pdf_document(pdf_doc: PDFDocument, upload_timestamp: str) -> List[Document]:
    """
    Converts a PDFDocument into a flat list of LangChain Document objects,
    each representing one chunk ready for embedding.

    Phase 4: passes page.ocr_applied through to build_chunk_metadata so each
    chunk records whether its text was obtained via OCR.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=[
            "\n\n",   # Paragraph breaks — split here first
            "\n",     # Line breaks
            ". ",     # Sentence ends
            "? ",     # Question ends
            "! ",     # Exclamation ends
            ", ",     # Clause breaks
            " ",      # Word breaks (fallback)
            "",       # Character-level (last resort — rarely reached)
        ],
        length_function=len,
        is_separator_regex=False,
    )

    doc_id = create_doc_id(pdf_doc.filename)
    all_chunks: List[Document] = []
    global_chunk_index = 0  # Increments across ALL pages

    for page in pdf_doc.pages:
        # Skip pages with no usable text
        if page.is_empty:
            logger.debug(
                "Skipping empty page",
                extra={"file": pdf_doc.filename, "page_num": page.page_num},
            )
            continue

        # Split this page's text into chunks
        page_chunks = splitter.split_text(page.text)

        for position_in_page, chunk_text in enumerate(page_chunks):
            if not chunk_text.strip():
                continue

            chunk_id = f"{doc_id}_{global_chunk_index}"

            chunk = Document(
                page_content=chunk_text,
                metadata=build_chunk_metadata(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    filename=pdf_doc.filename,
                    page_num=page.page_num,
                    total_pages=pdf_doc.total_pages,
                    chunk_index=global_chunk_index,
                    position_in_page=position_in_page,
                    upload_timestamp=upload_timestamp,
                    char_count=len(chunk_text),
                    ocr_applied=page.ocr_applied,   # Phase 4: pass through
                ),
            )
            all_chunks.append(chunk)
            global_chunk_index += 1

    logger.info(
        "Chunking complete",
        extra={
            "file": pdf_doc.filename,
            "doc_id": doc_id,
            "total_chunks": len(all_chunks),
            "pages_processed": len(pdf_doc.extractable_pages),
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
        },
    )

    return all_chunks


def build_chunk_metadata(
    chunk_id: str,
    doc_id: str,
    filename: str,
    page_num: int,
    total_pages: int,
    chunk_index: int,
    position_in_page: int,
    upload_timestamp: str,
    char_count: int,
    ocr_applied: bool = False,      # Phase 4: new parameter, default False
) -> dict:
    """
    Builds the metadata dictionary stored alongside each chunk in ChromaDB.

    Phase 4 change: 'has_ocr' is now set from the ocr_applied argument
    instead of being hardcoded False.  'doc_type' is set to 'scanned_pdf'
    when the chunk came from an OCR'd page.
    """
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "filename": filename,
        "page_num": page_num,
        "total_pages": total_pages,
        "chunk_index": chunk_index,
        "position_in_page": position_in_page,
        "upload_timestamp": upload_timestamp,
        "char_count": char_count,
        "doc_type": "scanned_pdf" if ocr_applied else "text_pdf",   # Phase 4
        "has_ocr": ocr_applied,                                       # Phase 4
    }
