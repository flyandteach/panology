"""Choose a split strategy for a file and write its parts to disk."""

from __future__ import annotations

import shutil
from pathlib import Path

from .core import SplitResult, part_names, write_manifest
from .ooxml_split import split_docx, split_pptx
from .pdf_split import split_pdf
from .text_split import split_bytes, split_text

TEXT_EXT = {".txt", ".text", ".md", ".markdown", ".log", ".jsonl", ".ndjson", ".sql",
            ".srt", ".vtt", ".ini", ".yaml", ".yml"}
CSV_EXT = {".csv", ".tsv"}

MODES = ("auto", "pdf", "docx", "pptx", "text", "csv", "bytes")


def detect_mode(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".docx", ".docm"):
        return "docx"
    if ext in (".pptx", ".pptm"):
        return "pptx"
    if ext in CSV_EXT:
        return "csv"
    if ext in TEXT_EXT:
        return "text"
    return "bytes"


def split_file(source: Path, out_dir: Path, limit: int, mode: str = "auto",
               header_lines: int | None = None, manifest: bool = True) -> SplitResult:
    source = Path(source)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = detect_mode(source) if mode == "auto" else mode
    result = SplitResult(source=source, method=mode)
    warn = result.warnings.append

    if mode == "pdf":
        chunks = split_pdf(source, limit, warn)
    elif mode == "docx":
        chunks = split_docx(source, limit, warn)
    elif mode == "pptx":
        chunks = split_pptx(source, limit, warn)
    elif mode == "csv":
        hl = 1 if header_lines is None else header_lines
        chunks = split_text(source, limit, warn, header_lines=hl, csv_mode=True)
    elif mode == "text":
        chunks = split_text(source, limit, warn, header_lines=header_lines or 0)
    elif mode == "bytes":
        chunks = split_bytes(source, limit, warn)
    else:
        raise ValueError(f"Unknown mode {mode!r}; choose from {', '.join(MODES)}")

    # Write to temporary names first: the total count isn't known until the end.
    temps: list[Path] = []
    try:
        for i, data in enumerate(chunks):
            tmp = out_dir / f".{source.name}.splitting.{i:05d}"
            tmp.write_bytes(data)
            temps.append(tmp)
    except BaseException:
        for t in temps:
            t.unlink(missing_ok=True)
        raise

    if mode == "bytes":
        width = max(3, len(str(len(temps))))
        finals = [out_dir / f"{source.name}.part{i:0{width}d}" for i in range(1, len(temps) + 1)]
        warn("Split as raw bytes: the parts are not individually openable. Rejoin them with "
             "`python -m file_splitter join` (or `cat` / `copy /b`).")
    else:
        finals = part_names(source, out_dir, len(temps))
    for tmp, final in zip(temps, finals):
        tmp.replace(final)
        if final.stat().st_size >= limit:
            result.oversized.append(final)
    result.parts = finals
    if manifest:
        write_manifest(result, out_dir, limit)
    return result


def join_parts(parts: list[Path], output: Path) -> Path:
    """Concatenate byte-split parts back into the original file."""
    parts = sorted(parts, key=lambda p: p.name)
    with open(output, "wb") as out:
        for p in parts:
            with open(p, "rb") as f:
                shutil.copyfileobj(f, out)
    return output


__all__ = ["split_file", "join_parts", "detect_mode", "MODES"]
