# SPDX-License-Identifier: Apache-2.0
"""Reading a `.docx` — measurement only, and never a write.

Most 200-page manuals are not markdown. They are Word documents, they are
not going to be converted first, and a workshop that cannot open one is a
workshop that does not get used on the documents it was designed for.

**Read-only, structurally.** This module returns TEXT. There is no writer
here and there is not going to be one: the promise that the manuscript is
never locked inside the tool is kept by the tool never touching the file,
and a `.docx` is exactly the format where a well-meaning round-trip
destroys tracked changes, comments, styles and a template somebody's
employer owns. Everything the workshop produces for a `.docx` project is a
finding, a measurement or an export — never an edit in place.

**Offsets are into the derived text.** For a markdown project, a span is a
character range in the file the author is editing, and clicking a finding
lands on it. For a `.docx` there is no such thing: the file is a zip of
XML. `SourceFile.derived` says so, and a host must show the section and
the quoted sentence rather than pretending it can put a cursor somewhere.
Saying that out loud is the whole reason this module is small.

Standard library only — `zipfile` and `xml.etree` — because the zero-
dependency rule is what lets the workshop run on a laptop with the GPU
cold, and it is not worth spending on a reader.
"""

from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: Extensions this module can turn into text.
DERIVED_SUFFIXES = (".docx",)

_HEADING = re.compile(r"^heading\s*([1-9])$", re.I)


def is_derived(path: str | Path) -> bool:
    return Path(path).suffix.lower() in DERIVED_SUFFIXES


def read(path: str | Path) -> str:
    """Any supported non-text manuscript file, as markdown."""
    path = Path(path)
    if path.suffix.lower() == ".docx":
        return read_docx(path)
    kind = path.suffix or "a file with no extension"
    raise ValueError(f"no reader for {kind}")


# ---------------------------------------------------------------------------
# .docx
# ---------------------------------------------------------------------------


def _numbering(zf: zipfile.ZipFile) -> dict[str, str]:
    """numId -> "bullet" or "ordered", from `word/numbering.xml`.

    Best effort by design. A document with no numbering part, or one
    whose numbering is defined somewhere this does not look, gets
    "bullet" — which produces a list item that is still prose and still
    measured, rather than an exception.
    """
    try:
        raw = zf.read("word/numbering.xml")
    except KeyError:
        return {}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return {}
    abstract: dict[str, str] = {}
    for node in root.iter(f"{W}abstractNum"):
        aid = node.get(f"{W}abstractNumId") or ""
        fmt = ""
        for lvl in node.iter(f"{W}lvl"):
            if (lvl.get(f"{W}ilvl") or "0") != "0":
                continue
            found = lvl.find(f"{W}numFmt")
            if found is not None:
                fmt = found.get(f"{W}val") or ""
            break
        abstract[aid] = "bullet" if fmt == "bullet" else "ordered"
    out: dict[str, str] = {}
    for node in root.iter(f"{W}num"):
        nid = node.get(f"{W}numId") or ""
        ref = node.find(f"{W}abstractNumId")
        aid = ref.get(f"{W}val") if ref is not None else ""
        out[nid] = abstract.get(aid or "", "ordered")
    return out


def _style_numbering(zf: zipfile.ZipFile) -> tuple[dict[str, str],
                                                   dict[str, str]]:
    """styleId -> numId, and styleId -> style NAME, from `word/styles.xml`.

    Needed because a list paragraph does not have to carry its own
    `numPr`: Word is perfectly happy for the numbering to live on the
    STYLE, and several generators do exactly that. Reading only the
    paragraph missed every list in such a document and silently reported
    the items as ordinary prose — which is worse than failing, because
    the step checks then have nothing to find and say so confidently.
    """
    try:
        root = ET.fromstring(zf.read("word/styles.xml"))
    except (KeyError, ET.ParseError):
        return {}, {}
    num: dict[str, str] = {}
    names: dict[str, str] = {}
    for node in root.iter(f"{W}style"):
        sid = node.get(f"{W}styleId") or ""
        if not sid:
            continue
        name = node.find(f"{W}name")
        if name is not None:
            names[sid] = name.get(f"{W}val") or ""
        props = node.find(f"{W}pPr")
        if props is None:
            continue
        num_pr = props.find(f"{W}numPr")
        if num_pr is None:
            continue
        ref = num_pr.find(f"{W}numId")
        if ref is not None and ref.get(f"{W}val"):
            num[sid] = ref.get(f"{W}val")
    return num, names


#: Style names that mean "list item" even with no numbering attached.
#: The last resort, and it is a real case: a document whose numbering
#: part was dropped in a round-trip still LOOKS like a numbered procedure
#: to the reader, and the author would like it measured as one.
_LIST_STYLE = re.compile(r"^list(paragraph|number|bullet|continue)", re.I)
_ORDERED_STYLE = re.compile(r"^list(number|paragraph)", re.I)


def _text_of(node) -> str:
    """One paragraph's visible text, tabs and breaks included."""
    parts: list[str] = []
    for child in node.iter():
        tag = child.tag
        if tag == f"{W}t":
            parts.append(child.text or "")
        elif tag == f"{W}tab":
            parts.append("\t")
        elif tag in (f"{W}br", f"{W}cr"):
            parts.append(" ")
    return "".join(parts).strip()


def _style(node) -> tuple[str, str, int]:
    """(style id, numbering id, indent level) for one paragraph."""
    props = node.find(f"{W}pPr")
    if props is None:
        return "", "", 0
    style = ""
    found = props.find(f"{W}pStyle")
    if found is not None:
        style = found.get(f"{W}val") or ""
    num_id, level = "", 0
    num = props.find(f"{W}numPr")
    if num is not None:
        ref = num.find(f"{W}numId")
        if ref is not None:
            num_id = ref.get(f"{W}val") or ""
        ilvl = num.find(f"{W}ilvl")
        if ilvl is not None:
            try:
                level = int(ilvl.get(f"{W}val") or 0)
            except ValueError:
                level = 0
    return style, num_id, level


def _heading_level(style: str) -> int:
    if not style:
        return 0
    plain = style.replace("-", " ").replace("_", " ").strip()
    m = _HEADING.match(plain)
    if m:
        return int(m.group(1))
    if plain.lower() in ("title", "doctitle"):
        return 1
    if plain.lower() in ("subtitle",):
        return 2
    return 0


def _row_text(row) -> list[str]:
    return [" ".join(_text_of(cell).split())
            for cell in row.findall(f"{W}tc")]


def read_docx(path: str | Path) -> str:
    """A Word document as markdown: headings, lists, tables, paragraphs.

    **Ordered lists are renumbered from 1.** Word stores no numbers — the
    renderer supplies them — so there is nothing in the file for the
    step-numbering check to find a gap in. Emitting a clean run is the
    honest representation of "this document's numbering is not the
    author's to get wrong"; inventing gaps would manufacture defects.
    `craft.technical.steps` skips derived files for the same reason.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        numbering = _numbering(zf)
        style_num, style_names = _style_numbering(zf)
        try:
            raw = zf.read("word/document.xml")
        except KeyError as exc:
            raise ValueError(f"{path.name} has no word/document.xml — "
                             f"is it really a .docx?") from exc
    root = ET.fromstring(raw)
    body = root.find(f"{W}body")
    if body is None:
        return ""

    lines: list[str] = []
    counters: dict[str, int] = {}
    for node in body:
        if node.tag == f"{W}tbl":
            counters.clear()
            rows = [_row_text(r) for r in node.findall(f"{W}tr")]
            rows = [r for r in rows if any(c for c in r)]
            if not rows:
                continue
            width = max(len(r) for r in rows)
            lines.append("")
            for i, row in enumerate(rows):
                cells = [*row, *([""] * (width - len(row)))]
                lines.append("| " + " | ".join(cells) + " |")
                if i == 0:
                    lines.append("|" + "---|" * width)
            lines.append("")
            continue
        if node.tag != f"{W}p":
            continue
        text = _text_of(node)
        style, num_id, level = _style(node)
        listed = ""
        if num_id:
            listed = numbering.get(num_id, "ordered")
        elif style and style in style_num:
            num_id = style_num[style]
            listed = numbering.get(num_id, "ordered")
        elif style:
            plain = (style_names.get(style, style) or "").replace(" ", "")
            if _LIST_STYLE.match(plain):
                num_id = f"style:{style}"
                listed = ("ordered" if _ORDERED_STYLE.match(plain)
                          and "bullet" not in plain.lower() else "bullet")
        if not text:
            counters.clear()
            lines.append("")
            continue
        heading = _heading_level(style)
        if heading:
            counters.clear()
            lines.append("")
            lines.append("#" * min(6, heading) + " " + text)
            lines.append("")
            continue
        if listed:
            indent = "    " * min(3, level)
            if listed == "bullet":
                lines.append(f"{indent}- {text}")
            else:
                counters[num_id] = counters.get(num_id, 0) + 1
                lines.append(f"{indent}{counters[num_id]}. {text}")
            continue
        counters.clear()
        lines.append("")
        lines.append(text)
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"
