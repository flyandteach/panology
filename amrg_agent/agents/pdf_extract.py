"""
Downloads a publicly-available full-text PDF and extracts its text and
embedded figures/images for use in the AMRG summary.
"""

import os
import re
import uuid

import requests

import config


class DownloadError(Exception):
    pass


def download_pdf(eprint_url: str, dest_dir: str = None) -> str:
    """Download a PDF from a Scholar eprint_url. Returns the local file path.

    Not every eprint_url points straight at a PDF -- some point at an HTML
    landing page that itself links to a PDF. This handles the common case
    (direct PDF) and raises DownloadError otherwise, so the caller can skip
    the article rather than store garbage.
    """
    dest_dir = dest_dir or config.DOWNLOADS_DIR
    os.makedirs(dest_dir, exist_ok=True)

    headers = {"User-Agent": config.USER_AGENT}
    try:
        resp = requests.get(
            eprint_url, headers=headers, timeout=config.REQUEST_TIMEOUT, stream=True
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise DownloadError(f"Failed to fetch {eprint_url}: {e}") from e

    content_type = resp.headers.get("Content-Type", "")
    looks_like_pdf = "pdf" in content_type.lower() or eprint_url.lower().endswith(".pdf")
    if not looks_like_pdf:
        raise DownloadError(
            f"{eprint_url} did not return a PDF (Content-Type: {content_type!r}); "
            "likely an HTML landing page, skipping."
        )

    filename = f"{uuid.uuid4().hex}.pdf"
    path = os.path.join(dest_dir, filename)
    with open(path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            fh.write(chunk)

    if os.path.getsize(path) < 2048:
        os.remove(path)
        raise DownloadError(f"{eprint_url} returned a suspiciously small file; skipping.")

    return path


def extract_text_and_figures(pdf_path: str, figures_dir: str = None) -> dict:
    """Extract full text (page-joined) and embedded images from a PDF.

    Returns:
        {
          "text": str,
          "page_count": int,
          "figures": [{"path": str, "page": int, "caption": str|None}],
        }
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError(
            "PyMuPDF is required for PDF extraction. Install it with `pip install pymupdf`."
        ) from e

    figures_dir = figures_dir or os.path.join(config.OUTPUT_DIR, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    doc_id = uuid.uuid4().hex[:8]
    full_text_parts = []
    figures = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_text = page.get_text("text")
        full_text_parts.append(page_text)

        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue
            image_bytes = base_image.get("image")
            ext = base_image.get("ext", "png")
            if not image_bytes:
                continue
            # Skip tiny images (icons, logos, decorative rules) -- keep this
            # generous since figures can legitimately be small line charts.
            if base_image.get("width", 0) < 100 or base_image.get("height", 0) < 100:
                continue

            fname = f"{doc_id}_p{page_index + 1}_{img_index}.{ext}"
            fpath = os.path.join(figures_dir, fname)
            with open(fpath, "wb") as fh:
                fh.write(image_bytes)

            figures.append({
                "path": fpath,
                "page": page_index + 1,
                "caption": _nearby_caption(page_text),
            })

    doc.close()

    return {
        "text": "\n".join(full_text_parts),
        "page_count": len(full_text_parts),
        "figures": figures,
    }


def _nearby_caption(page_text: str) -> str:
    """Best-effort: grab the first 'Figure N...' line on the same page."""
    match = re.search(r"(Figure\s+\d+[.:][^\n]{0,200})", page_text, re.IGNORECASE)
    return match.group(1).strip() if match else None
