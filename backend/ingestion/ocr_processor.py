"""
ingestion/ocr_processor.py
---------------------------
OCR pipeline for pages that contain no extractable text layer.

Fits cleanly into the existing pipeline without touching any other file's
logic.  The caller (pdf_processor.py) passes in a PageContent whose
.text is empty, and this module returns the OCR-extracted text for that page.

Approach: PyMuPDF render → PIL Image → pytesseract
  PyMuPDF already owns the open fitz.Document, so we render each page
  to a high-resolution pixmap and pass that directly to pytesseract.
  This avoids the pdf2image / poppler dependency and keeps the stack lean.
  pdf2image is still listed in requirements.txt as a fallback / alternative,
  but is not used in the primary path.

DPI choice:
  300 DPI is the industry standard for OCR.  Lower DPI (150, 200) is faster
  but degrades character recognition on small fonts.  Higher (400+) gives
  marginal gains and much larger memory allocations.  300 DPI is the default.

Thread safety:
  pytesseract spawns a subprocess for each call, so concurrent requests are
  safe.  There is no shared state in this module.
"""

import io
from typing import Optional

import fitz          # PyMuPDF — already a Phase 1 dependency
from PIL import Image
import pytesseract

from utils.logger import get_logger, Timer

logger = get_logger(__name__)


def ocr_page(
    fitz_doc: fitz.Document,
    page_index: int,           # 0-based index into fitz_doc
    page_num: int,             # 1-based page number (for logging / metadata)
    dpi: int = 300,
    language: str = "eng",
) -> str:
    """
    Renders one PDF page to an image and extracts text via pytesseract.

    Args:
        fitz_doc:   An already-open fitz.Document object.
        page_index: 0-based page index within fitz_doc.
        page_num:   1-based page number used only for log messages.
        dpi:        Render resolution.  300 is standard for OCR.
        language:   Tesseract language code.  Must match an installed data pack.
                    Run `tesseract --list-langs` to see what's available.
                    Default "eng" is always present.

    Returns:
        The extracted text string, normalised (trailing whitespace stripped,
        excess blank lines collapsed).  Returns "" on any error so the page
        is treated as empty rather than crashing the whole ingest.
    """
    try:
        page = fitz_doc[page_index]

        with Timer() as t:
            # Scale factor: default PDF unit is 72 DPI.
            # To render at target DPI:  scale = target_dpi / 72
            scale = dpi / 72.0
            mat = fitz.Matrix(scale, scale)

            # get_pixmap renders the page as a raster image.
            # colorspace=fitz.csRGB gives a 3-channel colour image.
            # alpha=False drops the transparency channel (not needed for OCR).
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)

            # Convert PyMuPDF Pixmap → PNG bytes → PIL Image
            # (PIL is what pytesseract accepts)
            img_bytes = pix.tobytes("png")
            pil_image = Image.open(io.BytesIO(img_bytes))

        logger.debug(
            "Page rendered for OCR",
            extra={
                "page_num": page_num,
                "dpi": dpi,
                "image_size": f"{pil_image.width}x{pil_image.height}",
                "render_ms": t.elapsed_ms,
            },
        )

        with Timer() as ocr_t:
            # image_to_string runs tesseract and returns the text as a Python str.
            # config="" uses tesseract defaults (PSM 3: fully automatic page segmentation).
            # For single-column documents, PSM 6 can be more reliable:
            #   config="--psm 6"
            raw_text = pytesseract.image_to_string(pil_image, lang=language)

        normalized = _normalize_ocr_output(raw_text)

        logger.info(
            "OCR complete for page",
            extra={
                "page_num": page_num,
                "chars_extracted": len(normalized),
                "ocr_ms": ocr_t.elapsed_ms,
            },
        )

        return normalized

    except pytesseract.TesseractNotFoundError:
        logger.error(
            "Tesseract binary not found. "
            "Install it: sudo apt-get install tesseract-ocr  "
            "or brew install tesseract",
            extra={"page_num": page_num},
        )
        return ""

    except Exception as e:
        logger.error(
            "OCR failed for page",
            extra={"page_num": page_num, "error": str(e)},
        )
        return ""


def _normalize_ocr_output(text: str) -> str:
    """
    Cleans up typical OCR noise before the text enters the chunking pipeline.

    OCR artifacts this handles:
      - Trailing/leading whitespace on lines (common in Tesseract output)
      - More than two consecutive blank lines (paragraph breaks are kept as \\n\\n)
      - Form-feed characters \\x0c that Tesseract appends at end of page
    """
    import re

    # Tesseract appends \x0c (form feed) at the end of every page — strip it
    text = text.replace("\x0c", "")

    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in text.splitlines()]
    text = "\n".join(lines)

    # Collapse 3+ consecutive blank lines to 2 (preserve paragraph structure)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
