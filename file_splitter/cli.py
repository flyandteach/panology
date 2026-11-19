"""Command line: split files, rejoin byte-split parts, or watch a folder."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from .core import DEFAULT_LIMIT, human, parse_size
from .splitter import MODES, join_parts, split_file


def _expand(paths: list[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            it = p.rglob("*") if recursive else p.iterdir()
            files += sorted(f for f in it if f.is_file() and not f.name.startswith("."))
        elif p.is_file():
            files.append(p)
        else:
            print(f"! Not found: {p}", file=sys.stderr)
    return files


def _process(src: Path, out_dir: Path, args, copy_small: bool) -> bool:
    """Split one file. Returns True if every resulting file is under the limit."""
    size = src.stat().st_size
    if size < args.limit and not args.force:
        if copy_small:
            shutil.copy2(src, out_dir / src.name)
            print(f"= {src.name} ({human(size)}) already under the limit; copied unchanged")
        else:
            print(f"= {src.name} ({human(size)}) already under the limit; skipped")
        return True
    print(f"> {src.name} ({human(size)})", flush=True)
    result = split_file(src, out_dir, args.limit, mode=args.mode,
                        header_lines=args.header_lines, manifest=not args.no_manifest)
    for part in result.parts:
        flag = "  OVER LIMIT" if part in result.oversized else ""
        print(f"    {part.name}  {human(part.stat().st_size)}{flag}")
    for w in result.warnings:
        print(f"    ! {w}")
    print(f"  {len(result.parts)} parts via {result.method} -> {out_dir}")
    return not result.oversized


def cmd_split(args) -> int:
    files = _expand(args.inputs, args.recursive)
    if not files:
        print("No input files.", file=sys.stderr)
        return 2
    ok = True
    for src in files:
        out_dir = Path(args.output) if args.output else src.parent / f"{src.stem}_split"
        try:
            ok &= _process(src, out_dir, args, copy_small=False)
        except Exception as exc:  # noqa: BLE001 - report and keep going with other files
            ok = False
            print(f"  ERROR {src.name}: {exc}", file=sys.stderr)
    return 0 if ok else 1


def cmd_join(args) -> int:
    parts = [Path(p) for p in args.parts]
    out = join_parts(parts, Path(args.output))
    print(f"Joined {len(parts)} parts -> {out} ({human(out.stat().st_size)})")
    return 0


def cmd_watch(args) -> int:
    inbox, outbox = Path(args.inbox), Path(args.outbox)
    done, failed = inbox / "_processed", inbox / "_failed"
    for d in (inbox, outbox, done, failed):
        d.mkdir(parents=True, exist_ok=True)
    print(f"Watching {inbox} every {args.interval}s; parts go to {outbox} "
          f"(limit {human(args.limit)}). Ctrl+C to stop.")
    last_seen: dict[Path, tuple[int, float]] = {}
    try:
        while True:
            for src in sorted(inbox.iterdir()):
                if not src.is_file() or src.name.startswith((".", "~$")):
                    continue
                st = src.stat()
                sig = (st.st_size, st.st_mtime)
                # Only touch a file once it has stopped changing (copy finished).
                if last_seen.get(src) != sig:
                    last_seen[src] = sig
                    continue
                last_seen.pop(src, None)
                target = outbox / src.stem if not args.flat else outbox
                target.mkdir(parents=True, exist_ok=True)
                try:
                    ok = _process(src, target, args, copy_small=True)
                    shutil.move(str(src), done / src.name)
                    if not ok:
                        print(f"  ! Some parts of {src.name} are still over the limit")
                except Exception as exc:  # noqa: BLE001
                    print(f"  ERROR {src.name}: {exc}", file=sys.stderr)
                    shutil.move(str(src), failed / src.name)
            if args.once:
                # In one-shot mode, don't wait a second pass for stability.
                if not any(p.is_file() and not p.name.startswith((".", "~$"))
                           for p in inbox.iterdir()):
                    return 0
                time.sleep(1)
                continue
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("-s", "--max-size", dest="limit", type=parse_size, default=DEFAULT_LIMIT,
                   help="Every part is kept strictly below this size. Default 10MB "
                        "(10,000,000 bytes). Accepts KB/MB/GB or KiB/MiB/GiB.")
    p.add_argument("-m", "--mode", choices=MODES, default="auto",
                   help="How to split. 'auto' picks from the file extension.")
    p.add_argument("--header-lines", type=int, default=None,
                   help="Lines repeated at the top of every part (CSV/TSV default 1, text 0).")
    p.add_argument("--force", action="store_true",
                   help="Process files even if they are already under the limit.")
    p.add_argument("--no-manifest", action="store_true",
                   help="Don't write the <file>.manifest.json listing parts and checksums.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m file_splitter",
        description="Split large documents into multiple files under a size limit (default <10MB).")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("split", help="Split one or more files (or every file in a folder).")
    s.add_argument("inputs", nargs="+", help="Files or folders.")
    s.add_argument("-o", "--output", help="Output folder (default: <name>_split next to each file).")
    s.add_argument("-r", "--recursive", action="store_true", help="Recurse into folders.")
    _common(s)
    s.set_defaults(func=cmd_split)

    w = sub.add_parser("watch", help="Watch a folder and automatically split files dropped into it.")
    w.add_argument("inbox", help="Folder to watch.")
    w.add_argument("outbox", help="Folder that receives the parts.")
    w.add_argument("-i", "--interval", type=float, default=5.0, help="Seconds between scans.")
    w.add_argument("--flat", action="store_true",
                   help="Put all parts directly in the outbox instead of one subfolder per file.")
    w.add_argument("--once", action="store_true",
                   help="Process what is in the inbox now, then exit (for cron/scheduled jobs).")
    _common(w)
    w.set_defaults(func=cmd_watch)

    j = sub.add_parser("join", help="Rejoin parts produced by --mode bytes.")
    j.add_argument("parts", nargs="+", help="Part files (sorted by name before joining).")
    j.add_argument("-o", "--output", required=True, help="File to write.")
    j.set_defaults(func=cmd_join)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
