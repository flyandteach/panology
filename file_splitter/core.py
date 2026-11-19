"""Shared helpers: size parsing, chunk packing, naming, and the manifest."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

# Default limit is 10 MB in decimal units (10,000,000 bytes). That is smaller
# than 10 MiB (10,485,760 bytes), so parts satisfy "<10MB" under either
# definition. Every part is kept strictly *below* the limit.
DEFAULT_LIMIT = 10_000_000

_UNITS = {
    "": 1, "B": 1,
    "KB": 1000, "MB": 1000**2, "GB": 1000**3,
    "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3,
}


def parse_size(text: str) -> int:
    """Parse '10MB', '9.5MiB', '500KB' or a bare byte count into bytes."""
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([A-Za-z]*)\s*", text)
    if not m or m.group(2).upper() not in _UNITS:
        raise ValueError(f"Unrecognised size: {text!r} (try 10MB, 9.5MiB, 500KB)")
    value = int(float(m.group(1)) * _UNITS[m.group(2).upper()])
    if value < 1024:
        raise ValueError("Size limit must be at least 1KiB")
    return value


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1000
    return str(n)


class SplitWarning(UserWarning):
    pass


@dataclass
class SplitResult:
    source: Path
    method: str
    parts: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    oversized: list[Path] = field(default_factory=list)


def pack(n_units: int, build: Callable[[int, int], bytes], limit: int,
         first_guess: int, on_oversize: Callable[[int], None]) -> Iterator[bytes]:
    """Group units [0, n_units) into consecutive chunks each < limit bytes.

    ``build(start, end)`` renders units[start:end] into a complete file and
    returns its bytes. Rendering is the only reliable way to know a chunk's
    size (PDF fonts and DOCX styles are shared overhead), so this gallops up
    from a guess and then binary-searches for the largest chunk that fits.
    A single unit that alone exceeds the limit is emitted on its own and
    reported through ``on_oversize``.
    """
    start = 0
    guess = max(1, first_guess)
    while start < n_units:
        remaining = n_units - start
        good_k, good_data = 0, b""   # largest count known to fit
        bad_k = None                  # smallest count known not to fit
        k = min(guess, remaining)
        while True:
            data = build(start, start + k)
            if len(data) < limit:
                good_k, good_data = k, data
            else:
                bad_k = k
            if good_k == remaining:
                break
            if bad_k is None:
                k = min(good_k * 2, remaining)
            elif bad_k - good_k <= 1:
                break
            else:
                k = (good_k + bad_k) // 2
        if good_k == 0:
            on_oversize(start)
            good_k, good_data = 1, build(start, start + 1)
        yield good_data
        start += good_k
        guess = good_k


def part_names(source: Path, out_dir: Path, count: int) -> list[Path]:
    width = max(2, len(str(count)))
    return [out_dir / f"{source.stem}_part{i:0{width}d}of{count:0{width}d}{source.suffix}"
            for i in range(1, count + 1)]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_manifest(result: SplitResult, out_dir: Path, limit: int) -> Path:
    manifest = {
        "source": result.source.name,
        "source_bytes": result.source.stat().st_size,
        "source_sha256": sha256_file(result.source),
        "method": result.method,
        "limit_bytes": limit,
        "parts": [{"file": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
                  for p in result.parts],
        "warnings": result.warnings,
    }
    path = out_dir / f"{result.source.name}.manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path
