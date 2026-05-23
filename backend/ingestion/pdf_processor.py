"""
ingestion/pdf_processor.py
---------------------------
Extracts text from PDF files page-by-page using PyMuPDF (fitz).

Why PyMuPDF?
  - Fastest Python PDF library (C-based)
  - Preserves page numbers accurately
  - Handles text, embedded fonts, and most PDF variants
  - Returns page-level text (essential for citation tracking)

Phase 3 note:
  If a PDF has zero extractable text (scanned/image PDF), this module
  returns empty strings per page. Phase 3 will detect this and route
  those pages through the OCR pipeline instead.
"""

import fitz  # PyMuPDF — imported as "fitz" (historical name)
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PageContent:
    """
    Represents the extracted content of a single PDF page.

    Attributes:
        page_num:   1-based page number (so citations say "page 3" not "page 2")
        text:       Raw extracted text from the page
        char_count: Number of characters (used to detect scanned pages)
    """
    page_num: int
    text: str
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.char_count = len(self.text.strip())

    @property
    def is_empty(self) -> bool:
        """True if the page has no usable text (likely scanned/image)."""
        return self.char_count < 50  # Fewer than 50 chars is essentially empty


@dataclass
class PDFDocument:
    """
    Represents a fully extracted PDF document.

    Attributes:
        filename:    Original filename (e.g., "report.pdf")
        total_pages: Total page count
        pages:       List of PageContent objects, one per page
    """
    filename: str
    total_pages: int
    pages: List[PageContent]

    @property
    def full_text(self) -> str:
        """All page texts joined (useful for debugging)."""
        return "\n\n".join(p.text for p in self.pages if not p.is_empty)

    @property
    def extractable_pages(self) -> List[PageContent]:
        """Pages with actual text content."""
        return [p for p in self.pages if not p.is_empty]

    @property
    def needs_ocr(self) -> bool:
        """
        True if the majority of pages are empty — indicates a scanned PDF.
        Phase 3 will use this flag to route through the OCR pipeline.
        """
        if not self.pages:
            return False
        empty_ratio = sum(1 for p in self.pages if p.is_empty) / len(self.pages)
        return empty_ratio > 0.5  # More than half of pages are image-only


def extract_text_from_pdf(file_path: str) -> PDFDocument:
    """
    Opens a PDF and extracts text from every page.

    Args:
        file_path: Absolute or relative path to the PDF file.

    Returns:
        PDFDocument with per-page content and metadata.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file is not a valid PDF.
        RuntimeError: If PyMuPDF encounters an unrecoverable error.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

    logger.info("Opening PDF", extra={"file": path.name, "path": str(path)})

    try:
        doc = fitz.open(str(path))
    except fitz.FileDataError as e:
        raise ValueError(f"Invalid or corrupted PDF: {file_path}") from e

    pages: List[PageContent] = []

    for page_index in range(len(doc)):
        page = doc[page_index]

        # extract_text() returns the raw text on the page.
        # "text" mode is the simplest; "blocks" mode (used in Phase 3+)
        # preserves layout but is more complex.
        raw_text = page.get_text("text")

        # Normalize whitespace: collapse 3+ newlines → 2, strip leading/trailing
        normalized_text = _normalize_whitespace(raw_text)

        page_content = PageContent(
            page_num=page_index + 1,  # Convert 0-based index to 1-based page number
            text=normalized_text,
        )
        pages.append(page_content)

    doc.close()

    pdf_doc = PDFDocument(
        filename=path.name,
        total_pages=len(pages),
        pages=pages,
    )

    logger.info(
        "PDF extraction complete",
        extra={
            "file": path.name,
            "total_pages": pdf_doc.total_pages,
            "extractable_pages": len(pdf_doc.extractable_pages),
            "needs_ocr": pdf_doc.needs_ocr,
            "total_chars": sum(p.char_count for p in pages),
        },
    )

    return pdf_doc


def _normalize_whitespace(text: str) -> str:
    """
    Cleans up common PDF text extraction artifacts:
    - Collapses 3+ consecutive newlines into 2 (preserves paragraph breaks)
    - Strips leading/trailing whitespace
    - Replaces non-breaking spaces with regular spaces
    """
    import re

    # Replace non-breaking spaces (common in PDFs)
    text = text.replace("\u00a0", " ")

    # Collapse 3+ newlines to 2 (preserve paragraph structure)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse multiple spaces on same line (but NOT across newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()
