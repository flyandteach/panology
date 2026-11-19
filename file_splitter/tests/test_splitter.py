"""Tests use small limits (a few hundred KB) so generated fixtures stay small."""

import io
import json
import os
import zipfile

import pytest

from file_splitter.cli import main
from file_splitter.core import parse_size
from file_splitter.splitter import split_file

LIMIT = 300_000


def noise_png(seed: int, px: int = 220) -> io.BytesIO:
    from PIL import Image
    rnd = os.urandom(px * px * 3)  # incompressible, so file sizes are predictable
    buf = io.BytesIO()
    Image.frombytes("RGB", (px, px), rnd).save(buf, "PNG")
    buf.seek(0)
    return buf


def test_parse_size():
    assert parse_size("10MB") == 10_000_000
    assert parse_size("10MiB") == 10 * 1024 * 1024
    assert parse_size("9.5mb") == 9_500_000
    with pytest.raises(ValueError):
        parse_size("ten")


def test_pdf(tmp_path):
    pytest.importorskip("reportlab")
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from pypdf import PdfReader

    src = tmp_path / "big.pdf"
    c = canvas.Canvas(str(src))
    for i in range(30):
        c.drawString(72, 800, f"Page {i + 1}")
        c.drawImage(ImageReader(noise_png(i)), 72, 400, 300, 300)
        c.showPage()
    c.save()
    assert src.stat().st_size > LIMIT * 2

    res = split_file(src, tmp_path / "out", LIMIT)
    assert len(res.parts) >= 3 and not res.oversized
    pages = 0
    for p in res.parts:
        assert p.stat().st_size < LIMIT
        pages += len(PdfReader(str(p)).pages)
    assert pages == 30
    first = PdfReader(str(res.parts[0])).pages[0].extract_text()
    assert "Page 1" in first


def test_docx(tmp_path):
    docx = pytest.importorskip("docx")
    from docx.shared import Inches

    src = tmp_path / "big.docx"
    d = docx.Document()
    for i in range(20):
        d.add_heading(f"Section {i + 1}", level=1)
        d.add_paragraph(f"Body text for section {i + 1}. " * 20)
        d.add_picture(noise_png(i), width=Inches(2))
    d.save(src)
    assert src.stat().st_size > LIMIT * 2

    res = split_file(src, tmp_path / "out", LIMIT)
    assert len(res.parts) >= 3 and not res.oversized
    headings, images = [], 0
    for p in res.parts:
        assert p.stat().st_size < LIMIT
        part = docx.Document(str(p))  # must open cleanly
        headings += [para.text for para in part.paragraphs if para.text.startswith("Section")]
        with zipfile.ZipFile(p) as z:
            images += sum(n.startswith("word/media/") for n in z.namelist())
    assert headings == [f"Section {i + 1}" for i in range(20)]
    assert images == 20  # each image lands in exactly one part


def test_pptx(tmp_path):
    pptx = pytest.importorskip("pptx")
    from pptx.util import Inches

    src = tmp_path / "big.pptx"
    prs = pptx.Presentation()
    for i in range(15):
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = f"Slide {i + 1}"
        s.shapes.add_picture(noise_png(i), Inches(1), Inches(2), Inches(3))
    prs.save(src)

    res = split_file(src, tmp_path / "out", LIMIT)
    assert len(res.parts) >= 2 and not res.oversized
    titles = []
    for p in res.parts:
        assert p.stat().st_size < LIMIT
        titles += [s.shapes.title.text for s in pptx.Presentation(str(p)).slides]
    assert titles == [f"Slide {i + 1}" for i in range(15)]


def test_csv_header_and_quoted_newlines(tmp_path):
    src = tmp_path / "data.csv"
    rows = ['id,note'] + [f'{i},"line one\nline two, ""quoted"" {i}"' for i in range(20000)]
    src.write_text("\n".join(rows) + "\n")
    res = split_file(src, tmp_path / "out", LIMIT)
    assert len(res.parts) >= 2
    import csv
    seen = []
    for p in res.parts:
        assert p.stat().st_size < LIMIT
        with open(p, newline="") as f:
            r = list(csv.reader(f))
        assert r[0] == ["id", "note"]
        seen += [int(row[0]) for row in r[1:]]
    assert seen == list(range(20000))


def test_text_roundtrip(tmp_path):
    src = tmp_path / "log.txt"
    src.write_text("".join(f"log line {i}\n" for i in range(100000)))
    res = split_file(src, tmp_path / "out", LIMIT)
    assert b"".join(p.read_bytes() for p in res.parts) == src.read_bytes()
    assert all(p.stat().st_size < LIMIT for p in res.parts)
    assert all(p.read_bytes().endswith(b"\n") for p in res.parts)


def test_bytes_and_join(tmp_path):
    src = tmp_path / "blob.bin"
    src.write_bytes(os.urandom(LIMIT * 3 + 123))
    out = tmp_path / "out"
    assert main(["split", str(src), "-o", str(out), "-s", str(LIMIT)]) == 0
    parts = sorted(out.glob("blob.bin.part*"))
    assert len(parts) == 4 and all(p.stat().st_size < LIMIT for p in parts)
    joined = tmp_path / "joined.bin"
    assert main(["join", *map(str, parts), "-o", str(joined)]) == 0
    assert joined.read_bytes() == src.read_bytes()
    manifest = json.loads((out / "blob.bin.manifest.json").read_text())
    assert manifest["method"] == "bytes" and len(manifest["parts"]) == 4


def test_watch_once(tmp_path):
    inbox, outbox = tmp_path / "in", tmp_path / "out"
    inbox.mkdir()
    (inbox / "small.txt").write_text("tiny\n")
    (inbox / "large.txt").write_text("x" * 50 + "\n" * 1 + ("row\n" * 200000))
    assert main(["watch", str(inbox), str(outbox), "--once", "-s", str(LIMIT)]) == 0
    assert (outbox / "small" / "small.txt").exists()
    assert len(list((outbox / "large").glob("large_part*.txt"))) >= 2
    assert (inbox / "_processed" / "large.txt").exists()
