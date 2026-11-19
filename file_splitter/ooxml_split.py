"""Split Word (.docx) and PowerPoint (.pptx) files into smaller, valid files.

Both formats are ZIP packages of XML "parts" linked by relationship files.
The approach:

* .docx: the units are the top-level blocks of the document body
  (paragraphs, tables, ...). Each part keeps the same styles, numbering,
  headers/footers and final section settings, with a slice of the body.
* .pptx: the units are slides. Each part keeps the same masters, layouts
  and theme, with a slice of the slide list.

After slicing, relationships from the main part to images, media, charts,
embedded objects, slides etc. that the slice no longer references are
dropped, and every package part no longer reachable from the package root is
deleted, so each output only carries the media it actually uses.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from pathlib import Path
from typing import Iterator

from lxml import etree

from .core import pack

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_MARK = "@@FILE_SPLITTER_UNITS@@"

# Relationship types (last URL segment) that the main part references
# explicitly by r:id, so they can be dropped when the slice no longer uses
# them. Implicit ones (styles, theme, settings, numbering, fonts, ...) are
# always kept.
_PRUNABLE = {
    "image", "oleObject", "package", "video", "audio", "media", "chart",
    "diagramData", "diagramLayout", "diagramQuickStyle", "diagramColors",
    "slide", "header", "footer", "control", "subDocument",
}


def _rels_path(part: str) -> str:
    d, base = posixpath.split(part)
    return posixpath.join(d, "_rels", base + ".rels")


def _resolve(source_part: str, target: str) -> str:
    if target.startswith("/"):
        return target[1:]
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


class _Package:
    def __init__(self, path: Path, main_part: str):
        with zipfile.ZipFile(path) as zf:
            self.infos = zf.infolist()
            self.files = {i.filename: zf.read(i.filename) for i in self.infos}
        if main_part not in self.files:
            raise ValueError(f"{path.name} is missing {main_part}; is it a valid Office file?")
        self.main_part = main_part
        rels = self.files.get(_rels_path(main_part))
        self.main_rels = (etree.fromstring(rels) if rels
                          else etree.Element(f"{{{NS_REL}}}Relationships", nsmap={None: NS_REL}))

    def reachable(self, files: dict[str, bytes]) -> set[str]:
        seen: set[str] = set()
        queue = [""]  # "" = package root, whose rels live at _rels/.rels
        while queue:
            part = queue.pop()
            rels = files.get("_rels/.rels" if part == "" else _rels_path(part))
            if rels is None:
                continue
            for rel in etree.fromstring(rels):
                if rel.get("TargetMode") == "External":
                    continue
                target = _resolve(part, rel.get("Target"))
                if target not in seen and target in files:
                    seen.add(target)
                    queue.append(target)
        return seen

    def render(self, main_xml: bytes) -> bytes:
        files = dict(self.files)
        files[self.main_part] = main_xml

        # Drop explicit relationships the sliced main part no longer uses.
        rels = etree.fromstring(etree.tostring(self.main_rels))
        for rel in list(rels):
            kind = rel.get("Type", "").rsplit("/", 1)[-1]
            if kind in _PRUNABLE and f'"{rel.get("Id")}"'.encode() not in main_xml:
                rels.remove(rel)
        files[_rels_path(self.main_part)] = etree.tostring(
            rels, xml_declaration=True, encoding="UTF-8", standalone=True)

        # Garbage-collect parts nobody points to any more.
        keep = self.reachable(files)
        keep |= {_rels_path(p) for p in keep} | {"_rels/.rels", "[Content_Types].xml"}
        ct = etree.fromstring(files["[Content_Types].xml"])
        for override in list(ct):
            if override.tag == f"{{{NS_CT}}}Override" and override.get("PartName", "/")[1:] not in keep:
                ct.remove(override)
        files["[Content_Types].xml"] = etree.tostring(
            ct, xml_declaration=True, encoding="UTF-8", standalone=True)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as out:
            for info in self.infos:
                name = info.filename
                if name in keep and name in files:
                    out.writestr(info, files[name], compress_type=info.compress_type)
        return buf.getvalue()


def _template(root, container, units) -> tuple[list[bytes], bytes, bytes]:
    """Serialise each unit once, plus the document around them."""
    unit_xml = [etree.tostring(u) for u in units]
    for u in units:
        container.remove(u)
    container.text = _MARK
    whole = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    head, tail = whole.split(_MARK.encode())
    return unit_xml, head, tail


def _split(source: Path, limit: int, warn, main_part: str, find_units, unit_name: str) -> Iterator[bytes]:
    pkg = _Package(source, main_part)
    root = etree.fromstring(pkg.files[main_part])
    container, units, suffix = find_units(root)
    if not units:
        raise ValueError(f"{source.name} has no {unit_name}s to split on")
    unit_xml, head, tail = _template(root, container, units)
    # Elements that must stay at the end of the container (e.g. Word's sectPr).
    tail = suffix + tail

    def build(s: int, e: int) -> bytes:
        return pkg.render(head + b"".join(unit_xml[s:e]) + tail)

    def oversize(i: int) -> None:
        warn(f"{unit_name.capitalize()} {i + 1} alone is larger than the limit (probably a large "
             "image or embedded file); its part is still over the limit.")

    guess = max(1, int(len(units) * limit / source.stat().st_size * 0.8))
    return pack(len(units), build, limit, guess, oversize)


def split_docx(source: Path, limit: int, warn) -> Iterator[bytes]:
    def find_units(root):
        body = root.find(f"{{{NS_W}}}body")
        if body is None:
            raise ValueError("document.xml has no body")
        children = list(body)
        suffix = b""
        if children and children[-1].tag == f"{{{NS_W}}}sectPr":
            sect = children.pop()
            suffix = etree.tostring(sect)
            body.remove(sect)
        return body, children, suffix

    return _split(source, limit, warn, "word/document.xml", find_units, "block")


def split_pptx(source: Path, limit: int, warn) -> Iterator[bytes]:
    def find_units(root):
        lst = root.find(f"{{{NS_P}}}sldIdLst")
        if lst is None:
            raise ValueError("presentation has no slides")
        return lst, list(lst), b""

    return _split(source, limit, warn, "ppt/presentation.xml", find_units, "slide")
