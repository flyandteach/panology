"""OCR-based receipt data extraction using Tesseract.

Handles image files (JPG, PNG) and scanned/image PDFs.
For text-based PDFs, falls back to pypdf text extraction.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional


def _extract_text_from_pdf_bytes(data: bytes) -> str:
    """Try pypdf text extraction first (works for digital PDFs)."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n".join(pages).strip()
    except Exception:
        return ""


def _ocr_pdf(data: bytes) -> str:
    """Convert PDF pages to images and OCR each one."""
    from pdf2image import convert_from_bytes
    import pytesseract
    images = convert_from_bytes(data, dpi=200)
    return "\n".join(pytesseract.image_to_string(img) for img in images)


def _ocr_image(data: bytes) -> str:
    import pytesseract
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img)


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Return raw text from a PDF or image file."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        text = _extract_text_from_pdf_bytes(file_bytes)
        if len(text) > 50:
            return text
        # Fallback: OCR the PDF as images
        return _ocr_pdf(file_bytes)
    else:
        return _ocr_image(file_bytes)


# ---------------------------------------------------------------------------
# Regex parsers
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b",
    r"\b(\d{4}-\d{2}-\d{2})\b",
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
]

_AMOUNT_PATTERNS = [
    r"\bTotal[:\s]+\$?([\d,]+\.\d{2})\b",
    r"\bAmount[:\s]+\$?([\d,]+\.\d{2})\b",
    r"\bCharge[:\s]+\$?([\d,]+\.\d{2})\b",
    r"\bDue[:\s]+\$?([\d,]+\.\d{2})\b",
    r"\$\s*([\d,]+\.\d{2})",
]

_VENDOR_SKIP = re.compile(
    r"^(receipt|invoice|folio|date|time|room|guest|page|thank|www\.|http|"
    r"tel:|phone|fax|tax|subtotal|total|amount|charge|balance|ref|conf|#|\d)",
    re.I,
)


def _find_date(text: str) -> str:
    for pat in _DATE_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            raw = m.group(1)
            # Normalize to YYYY-MM-DD if possible
            from datetime import datetime
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d",
                        "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
                try:
                    return datetime.strptime(raw.replace(",", ""), fmt.replace(",", "")).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return raw
    return ""


def _find_amount(text: str) -> float:
    # Try labeled patterns first (Total, Amount, etc.), then any dollar amount
    for pat in _AMOUNT_PATTERNS:
        matches = re.findall(pat, text, re.I)
        if matches:
            amounts = [float(m.replace(",", "")) for m in matches]
            return max(amounts)  # take the largest (most likely the total)
    return 0.0


def _find_vendor(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 3 or len(line) > 60:
            continue
        if _VENDOR_SKIP.match(line):
            continue
        if re.search(r"[a-zA-Z]{3,}", line):
            return line
    return ""


def parse_receipt(text: str) -> dict:
    """Parse raw OCR/extracted text into a receipt dict."""
    return {
        "vendor":      _find_vendor(text),
        "date":        _find_date(text),
        "amount":      _find_amount(text),
        "raw_text":    text[:500],
    }


def extract_receipt_from_file(file_bytes: bytes, filename: str) -> dict:
    """Full pipeline: extract text then parse into structured receipt data."""
    text = extract_text(file_bytes, filename)
    result = parse_receipt(text)
    return result
