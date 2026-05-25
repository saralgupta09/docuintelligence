"""
ingestion/pdf_processor.py
---------------------------
Extracts text from PDF files page-by-page using PyMuPDF (fitz).

Phase 4 addition:
  When OCR_ENABLED=true, pages that have no extractable text layer (scanned
  PDFs, image-based pages) are automatically routed through pytesseract OCR.
  The rest of the pipeline (chunker, embeddings, ChromaDB) is unchanged —
  every page ends up with a .text string regardless of how it was obtained.

All existing Phase 1/2/3 behaviour is preserved:
  - PageContent dataclass: unchanged
  - PDFDocument dataclass: unchanged
  - extract_text_from_pdf() signature: unchanged
  - _normalize_whitespace(): unchanged
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
        ocr_applied: True if this page's text came from OCR rather than direct
                     text extraction.  Stored in chunk metadata as 'has_ocr'.
    """
    page_num: int
    text: str
    ocr_applied: bool = False          # Phase 4: flag set when OCR was used
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
        After Phase 4 processing this will be False for successfully OCR'd docs.
        """
        if not self.pages:
            return False
        empty_ratio = sum(1 for p in self.pages if p.is_empty) / len(self.pages)
        return empty_ratio > 0.5  # More than half of pages are image-only

    @property
    def ocr_page_count(self) -> int:
        """Number of pages whose text was obtained via OCR (Phase 4)."""
        return sum(1 for p in self.pages if p.ocr_applied)


def extract_text_from_pdf(file_path: str) -> PDFDocument:
    """
    Opens a PDF and extracts text from every page.

    Phase 4 behaviour:
      If OCR_ENABLED=true in config (default: true), pages with fewer than
      50 characters of direct text are automatically run through pytesseract.
      The fitz.Document is kept open while OCR runs so we don't re-open the
      file for each page, then closed once all pages are processed.

    Args:
        file_path: Absolute or relative path to the PDF file.

    Returns:
        PDFDocument with per-page content and metadata.
        Pages processed via OCR have .ocr_applied = True.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file is not a valid PDF.
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

    # ── Phase 4: import config and OCR module ─────────────────────────────────
    # Imported here (not at module top) to keep Phase 1 behaviour if OCR
    # config keys are absent — pydantic will use defaults gracefully.
    from config import settings
    ocr_enabled = getattr(settings, "OCR_ENABLED", True)
    ocr_language = getattr(settings, "OCR_LANGUAGE", "eng")
    ocr_dpi = getattr(settings, "OCR_DPI", 300)

    if ocr_enabled:
        from ingestion.ocr_processor import ocr_page

    pages: List[PageContent] = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_num = page_index + 1       # 1-based

        # ── Direct text extraction (always attempted first) ───────────────────
        raw_text = page.get_text("text")
        normalized_text = _normalize_whitespace(raw_text)

        ocr_applied = False

        # ── Phase 4: OCR fallback for empty pages ─────────────────────────────
        # A page is considered empty if it has fewer than 50 chars after
        # normalisation.  This threshold matches PageContent.is_empty so that
        # a page which fails direct extraction is OCR'd before is_empty is
        # evaluated, not after.
        if ocr_enabled and len(normalized_text.strip()) < 50:
            logger.info(
                "Page has no extractable text — attempting OCR",
                extra={
                    "file": path.name,
                    "page_num": page_num,
                    "direct_chars": len(normalized_text.strip()),
                },
            )
            ocr_text = ocr_page(
                fitz_doc=doc,
                page_index=page_index,
                page_num=page_num,
                dpi=ocr_dpi,
                language=ocr_language,
            )
            if ocr_text.strip():
                normalized_text = ocr_text
                ocr_applied = True
                logger.info(
                    "OCR succeeded",
                    extra={
                        "file": path.name,
                        "page_num": page_num,
                        "ocr_chars": len(normalized_text),
                    },
                )
            else:
                logger.warning(
                    "OCR returned no text for page",
                    extra={"file": path.name, "page_num": page_num},
                )

        page_content = PageContent(
            page_num=page_num,
            text=normalized_text,
            ocr_applied=ocr_applied,
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
            "ocr_pages": pdf_doc.ocr_page_count,
            "needs_ocr": pdf_doc.needs_ocr,
            "total_chars": sum(p.char_count for p in pages),
        },
    )

    return pdf_doc


def _normalize_whitespace(text: str) -> str:
    """
    Cleans up common PDF text extraction artifacts.
    Unchanged from Phase 1.
    """
    import re

    # Replace non-breaking spaces (common in PDFs)
    text = text.replace("\u00a0", " ")

    # Collapse 3+ newlines to 2 (preserve paragraph structure)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse multiple spaces on same line (but NOT across newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()
