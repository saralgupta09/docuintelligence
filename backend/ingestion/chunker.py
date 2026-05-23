"""
ingestion/chunker.py
---------------------
Splits PDF page text into overlapping chunks suitable for embedding and retrieval.

Why RecursiveCharacterTextSplitter?
  - Tries to split on paragraph breaks first (\n\n), then sentence ends (. ),
    then words — so chunks break at natural boundaries, not mid-sentence.
  - chunk_overlap ensures sentences that straddle a boundary appear in both
    adjacent chunks, preventing "lost" context at chunk edges.
  - Simple, battle-tested, no external dependencies beyond LangChain.

Chunk ID format:
  {doc_id}_{chunk_index}
  Example: "report_pdf_0", "report_pdf_1", ...

  This makes chunks traceable back to their source document and position.
"""

import hashlib
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

    "My Report (Final) v2.pdf" → "my_report_final_v2_pdf"

    A short MD5 suffix is appended if two filenames would produce the same ID.
    For Phase 1 we keep it simple — just sanitize the filename.
    """
    import re
    # Lowercase, replace non-alphanumeric with underscores, collapse extras
    doc_id = re.sub(r"[^a-z0-9]+", "_", filename.lower()).strip("_")
    return doc_id


def chunk_pdf_document(pdf_doc: PDFDocument, upload_timestamp: str) -> List[Document]:
    """
    Converts a PDFDocument into a flat list of LangChain Document objects,
    each representing one chunk ready for embedding.

    Strategy:
    1. Process each page individually (preserves page_num per chunk)
    2. Run RecursiveCharacterTextSplitter on each page's text
    3. Attach rich metadata to every chunk

    Args:
        pdf_doc:          Output from pdf_processor.extract_text_from_pdf()
        upload_timestamp: ISO 8601 timestamp string (set once at upload time)

    Returns:
        List of Document objects. Each has .page_content (the text)
        and .metadata (filename, page_num, chunk_id, etc.)
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
        # Skip pages with no usable text (scanned pages handled in Phase 3)
        if page.is_empty:
            logger.debug(
                "Skipping empty page",
                extra={"file": pdf_doc.filename, "page_num": page.page_num},
            )
            continue

        # Split this page's text into chunks
        page_chunks = splitter.split_text(page.text)

        for position_in_page, chunk_text in enumerate(page_chunks):
            # Skip chunks that are just whitespace after splitting
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
) -> dict:
    """
    Builds the metadata dictionary stored alongside each chunk in ChromaDB.

    These fields power:
    - Citation display: filename + page_num
    - Deduplication: chunk_id
    - Filtering: doc_id (retrieve only from a specific document)
    - Debugging: chunk_index, char_count
    - Audit: upload_timestamp
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
        "doc_type": "text_pdf",  # Phase 3 will set "scanned_pdf", "image", etc.
        "has_ocr": False,         # Phase 3 will set True for OCR'd content
    }
