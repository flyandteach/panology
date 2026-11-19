"""Split text-like files on line (or CSV record) boundaries, and anything else by bytes."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

CHUNK_READ = 1 << 20


def _records(path: Path, csv_mode: bool) -> Iterator[bytes]:
    """Yield lines; in CSV mode, yield whole records so quoted newlines stay intact.

    RFC 4180 escapes a quote by doubling it, so a record ends at a newline
    only when the number of '"' characters seen so far in it is even.
    """
    with open(path, "rb") as f:
        if not csv_mode:
            yield from f
            return
        pending: list[bytes] = []
        quotes = 0
        for line in f:
            pending.append(line)
            quotes += line.count(b'"')
            if quotes % 2 == 0:
                yield b"".join(pending)
                pending, quotes = [], 0
        if pending:
            yield b"".join(pending)


def split_text(source: Path, limit: int, warn, header_lines: int = 0,
               csv_mode: bool = False) -> Iterator[bytes]:
    records = _records(source, csv_mode)
    header = b""
    for _ in range(header_lines):
        header += next(records, b"")
    if len(header) >= limit // 2:
        raise ValueError("Header is too large to repeat in every part")

    buf = bytearray(header)
    has_body = False
    warned = False
    for rec in records:
        if len(buf) + len(rec) >= limit and has_body:
            yield bytes(buf)
            buf, has_body = bytearray(header), False
        if len(header) + len(rec) >= limit:
            # A single line bigger than a whole part: cut it on raw bytes.
            if not warned:
                warn("A single line/record is larger than the limit; it was cut mid-line.")
                warned = True
            room = limit - 1 - len(buf)
            while rec:
                buf += rec[:room]
                rec = rec[room:]
                if rec:
                    yield bytes(buf)
                    buf = bytearray(header)
                    room = limit - 1 - len(buf)
            has_body = True
            continue
        buf += rec
        has_body = True
    if has_body or not buf:
        yield bytes(buf)


def split_bytes(source: Path, limit: int, warn) -> Iterator[bytes]:
    size = limit - 1
    with open(source, "rb") as f:
        while True:
            chunk = f.read(size)
            if not chunk:
                break
            yield chunk
