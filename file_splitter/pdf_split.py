"""Split a PDF into page ranges, each a standalone PDF under the size limit."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterator

from pypdf import PdfReader, PdfWriter

from .core import pack


def _render(reader: PdfReader, start: int, end: int) -> bytes:
    writer = PdfWriter()
    for i in range(start, end):
        writer.add_page(reader.pages[i])
    if reader.metadata:
        writer.add_metadata({k: v for k, v in reader.metadata.items() if isinstance(v, str)})
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def split_pdf(source: Path, limit: int, warn) -> Iterator[bytes]:
    reader = PdfReader(str(source))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{source.name} is password-protected; decrypt it first") from exc
    n = len(reader.pages)
    if n == 0:
        raise ValueError(f"{source.name} has no pages")
    size = source.stat().st_size
    guess = max(1, int(n * limit / size * 0.8))

    def oversize(i: int) -> None:
        warn(f"Page {i + 1} alone is larger than the limit; it was written to its own part "
             "and that part is still over the limit (compress its images to fix).")

    return pack(n, lambda s, e: _render(reader, s, e), limit, guess, oversize)
