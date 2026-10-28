# SPDX-License-Identifier: Apache-2.0
"""The manuscript: files on disk, and a structure derived from them.

**THE OUTLINE IS DERIVED, NEVER STORED.** The headings in the files are the
structure. There is nothing to get out of sync, the author can reorganise
in any editor they like and the workshop follows, and — the part that
matters most — the manuscript is never locked inside ATK. A tool that holds
an author's book hostage in a database blob is one they cannot leave, and
one they will not trust with the book.

Two consequences of that, both deliberate:

* **File order is filename order** (natural sort, so `9` precedes `10`).
  An explicit order file would be a second source of truth for the same
  fact, and the first time it disagreed with the folder the author would
  have no way to tell which one the workshop believed. Number the files.
* **Section ids are derived too** — `chapters/03.md#2`. They are stable
  while the heading order is, which is the same guarantee a line number
  gives, and they mean nothing has to be written into the author's files.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path
import re

from . import formats as F
from . import textio as T
from .errors import ProjectError
from .types import Paragraph, Section, Span

#: What counts as manuscript. `.txt` is included because a great many
#: novels are written in one, and refusing to read them would be a purity
#: the author pays for. `.docx` is included because most 200-page manuals
#: are one, they are not going to be converted first, and a workshop that
#: cannot open the document it was designed for is not much of a
#: workshop. A `.docx` is READ-ONLY here and its file is never written —
#: see `writing_workshop.formats` and `SourceFile.derived`.
SUFFIXES = (".md", ".markdown", ".txt", *F.DERIVED_SUFFIXES)

#: Never walked into. `.workshop` is ours; the rest are the folders every
#: project grows and none of them are the book.
SKIP_DIRS = {".workshop", ".git", "__pycache__", "_to_delete", "backups",
             "node_modules", ".venv", "exports", "audio"}

#: Files a HOST writes beside the chapters that are never the book.
#:
#: 2026-10-28: ATK's drafting kept the model's reasoning in
#: `NN-title.thinking.md` beside each chapter, and every one of them was
#: read back in as a chapter — measured, mined for claims, and exported in
#: the Shunn manuscript as "Thinking — Chapter 1". New sidecars live under
#: `.workshop/` now; this keeps the ones already on disk out of the book.
SIDECAR_SUFFIXES = (".thinking.md",)


def is_sidecar(path: str | Path) -> bool:
    name = Path(path).name.lower()
    return any(name.endswith(s) for s in SIDECAR_SUFFIXES)


def decode(raw: bytes) -> tuple[str, str, str]:
    """`(text, encoding, note)` for a manuscript file's bytes.

    Four Windows realities, each of which used to read wrongly AND
    silently (2026-10-28):

    * **UTF-8 with a BOM** (Notepad's default for years, PowerShell 5) —
      the BOM stuck to the first heading, so `# Chapter One` stopped being
      a heading.
    * **UTF-16** (Notepad's "Unicode") — decoded as cp1252 garbage, one
      letter per "word".
    * **One stray Windows byte in a UTF-8 file** — the WHOLE file was
      re-read as cp1252 and every curly quote became mojibake. Now only the
      stray byte is replaced, and the note says so.
    * **A real cp1252 file** — still read, as before, and now named.

    `note` is "" for a clean UTF-8 file and a sentence otherwise, so the
    host can say what was done (rule 4).
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace"), "utf-8-sig", ""
    # The BYTE ORDER is the encoding's name, not "utf-16": writing with
    # plain "utf-16" emits the machine's own order, so a big-endian file
    # came back little-endian on Save.
    if raw.startswith(b"\xff\xfe"):
        return (raw[2:].decode("utf-16-le", errors="replace"), "utf-16-le",
                "read as UTF-16")
    if raw.startswith(b"\xfe\xff"):
        return (raw[2:].decode("utf-16-be", errors="replace"), "utf-16-be",
                "read as UTF-16 (big-endian)")
    try:
        return raw.decode("utf-8"), "utf-8", ""
    except UnicodeDecodeError:
        pass
    as_utf8 = raw.decode("utf-8", errors="replace")
    bad = as_utf8.count("\ufffd")
    good = sum(1 for ch in as_utf8 if ord(ch) > 0x7F and ch != "\ufffd")
    if good > bad:
        return (as_utf8, "utf-8",
                f"{bad} byte(s) were not valid UTF-8 and were replaced")
    return (raw.decode("cp1252", errors="replace"), "cp1252",
            "read as Windows-1252 (cp1252)")


def newline_of(text) -> str:
    """The line ending a file was written with, so a host can write it
    back the same way instead of converting every line on Save.

    Give it the DECODED text. Bytes are accepted and decoded first: in
    UTF-16 a CRLF is `\\r\\x00\\n\\x00`, and counting `b"\\r\\n"` in the raw
    bytes never found one, so every UTF-16 chapter was saved as LF. A file
    of lone `\\r` (classic Mac) is `"\\r"`. Mixed endings get the majority.
    """
    if isinstance(text, (bytes, bytearray)):
        text = decode(bytes(text))[0]
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    if cr > max(lf, crlf):
        return "\r"
    return "\r\n" if crlf and crlf >= lf else "\n"


_NUMBERED = re.compile(r"^\s*((?:\d+|[A-Z])(?:\.\d+)*)[.)]?\s+(.*)$")
_SCENE_BREAK = re.compile(
    r"^\s*(\*\s*\*\s*\*|#\s*#\s*#|---|\* \* \*|#|~~~+)\s*$")


def _natural(name: str) -> tuple:
    return tuple(int(p) if p.isdigit() else p.lower()
                 for p in re.split(r"(\d+)", name))


@dataclass
class SourceFile:
    path: Path
    rel: str
    text: str
    blocks: list[T.Block] = field(default_factory=list)
    prose: str = ""
    #: True when `text` was DERIVED from the file rather than read from
    #: it — a `.docx`, today. It matters to two things and both would be
    #: wrong without it: offsets point into the derived text and not into
    #: anything a host could put a cursor in, and checks whose premise is
    #: "the source is the truth, not the render" are false here, because
    #: for a Word document the render owns the numbering.
    derived: bool = False
    #: How the bytes were read, so the one host widget that writes a file
    #: back (the author's Save) can keep the encoding and line endings it
    #: found. "" for a derived file.
    encoding: str = "utf-8"
    newline: str = "\n"
    #: A sentence when the read was not a clean UTF-8 one; see `decode`.
    note: str = ""

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def clickable(self) -> bool:
        """Can a host jump to an offset in this file? Not for a .docx."""
        return not self.derived


@dataclass
class Manuscript:
    """Every file, every section, in reading order."""

    root: Path
    files: list[SourceFile] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    _by_id: dict[str, Section] = field(default_factory=dict)
    _prose: dict[str, str] = field(default_factory=dict)
    # ---- caches -----------------------------------------------------
    # A Manuscript is IMMUTABLE once loaded. `Project.manuscript()`
    # re-reads from disk on every call precisely so that nothing here has
    # to be invalidated, which is what makes these caches safe by
    # construction rather than by discipline. Before them, `quote()` re-
    # split the whole file into sentences on every call: thirteen quotes
    # cost thirty-nine of the forty seconds one craft check spent.
    _sent: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    _sent_at: dict[str, list[int]] = field(default_factory=dict)
    _paras: dict[str, list[Paragraph]] = field(default_factory=dict)
    _sec_at: dict[str, tuple[list[int], list[Section]]] = field(
        default_factory=dict)
    _found: dict[tuple[str, bool], list[Span]] = field(default_factory=dict)
    _by_rel: dict[str, SourceFile] = field(default_factory=dict)
    _starts: dict[str, list[int]] = field(default_factory=dict)
    #: (path, why) for every file that could not be read. Never raised:
    #: one bad file must not cost the author the other thirty-nine, and
    #: rule 4 says the report has to name what was not done.
    unreadable: list[tuple[str, str]] = field(default_factory=list)
    #: Host sidecars found among the chapters and left out of the book.
    sidecars: list[str] = field(default_factory=list)

    # -- loading ----------------------------------------------------------

    @classmethod
    def load(cls, root: str | Path) -> Manuscript:
        root = Path(root)
        if not root.exists():
            raise ProjectError(
                f"no manuscript at {root} — point the workshop at a folder "
                f"of .md files, or at one file.")
        paths: list[Path]
        if root.is_file():
            paths = [root]
            base = root.parent
        else:
            base = root
            paths = sorted(
                (p for p in root.rglob("*")
                 if p.suffix.lower() in SUFFIXES and p.is_file()
                 and not any(part in SKIP_DIRS or part.startswith(".")
                             for part in p.relative_to(root).parts[:-1])
                 and not p.name.startswith(".")),
                key=lambda p: tuple(_natural(part) for part in
                                    p.relative_to(root).parts))
        doc = cls(root=base)
        for path in paths:
            if is_sidecar(path) and not root.is_file():
                doc.sidecars.append(str(path.relative_to(root))
                                    .replace("\\", "/"))
                continue
            derived = F.is_derived(path)
            encoding, newline, note = "", "\n", ""
            if derived:
                try:
                    text = F.read(path)
                except Exception as exc:               # noqa: BLE001
                    # One unreadable file must not cost the author the
                    # other thirty-nine. It is reported rather than
                    # raised, because a manuscript that will not open at
                    # all is the one failure this loader must not have.
                    doc.unreadable.append((str(path), str(exc)))
                    continue
            else:
                try:
                    raw = path.read_bytes()
                except OSError as exc:
                    doc.unreadable.append((str(path), str(exc)))
                    continue
                # A manuscript written on Windows in a previous decade is
                # read rather than refused; the author cares about the
                # book, not about its encoding — but the note says what
                # was done, because a silent guess is how mojibake gets in.
                text, encoding, note = decode(raw)
                newline = newline_of(text)
                text = text.replace("\r\n", "\n").replace("\r", "\n")
            rel = (path.name if root.is_file()
                   else str(path.relative_to(root)).replace("\\", "/"))
            blocks = T.scan_blocks(text)
            prose = T.prose_of(text)
            if path.suffix.lower() == ".txt":
                blocks = T.plain_headings(text, blocks)
                for block in blocks:
                    if block.kind == T.HEADING and block.marker == "plain":
                        # Masked like any heading: "CHAPTER 7" is not a
                        # sentence of the book.
                        prose = (prose[:block.start]
                                 + " " * (block.end - block.start)
                                 + prose[block.end:])
            src = SourceFile(path=path, rel=rel, text=text,
                             blocks=blocks, derived=derived,
                             encoding=encoding, newline=newline, note=note)
            src.prose = prose
            doc.files.append(src)
            doc._prose[rel] = src.prose
        doc._derive_sections()
        return doc

    # -- structure --------------------------------------------------------

    def _derive_sections(self) -> None:
        self.sections = []
        counters: list[int] = []
        order = 0
        for src in self.files:
            heads = [b for b in src.blocks if b.kind == T.HEADING]
            spans: list[tuple[T.Block | None, int, int]] = []
            first = heads[0].start if heads else len(src.text)
            # Judged on the MASKED prose when there are headings: YAML
            # front matter above the first one made a 0-word phantom
            # chapter per file, named after the file. A file with NO
            # heading is still one section whatever it holds, or a file
            # that is all table could not even be opened from the tree.
            lead = (self._prose.get(src.rel, src.text) if heads
                    else src.text)[:first]
            if lead.strip():
                # Prose before the first heading is a section too. Skipping
                # it is how a whole chapter written without a title becomes
                # invisible to every measurement in the tool.
                spans.append((None, 0, first))
            for i, head in enumerate(heads):
                end = (heads[i + 1].start if i + 1 < len(heads)
                       else len(src.text))
                spans.append((head, head.start, end))

            stack: list[tuple[int, str]] = []
            for head, start, end in spans:
                level = head.level if head else 1
                raw_title = head.text if head else src.stem
                number, title = "", raw_title
                m = _NUMBERED.match(raw_title)
                if m and head is not None:
                    number, title = m.group(1), m.group(2)
                while len(counters) < level:
                    counters.append(0)
                counters = counters[:level]
                counters[level - 1] += 1
                derived = ".".join(str(c) for c in counters)
                while stack and stack[-1][0] >= level:
                    stack.pop()
                parent = stack[-1][1] if stack else ""
                index = sum(1 for s in self.sections if s.path == src.rel)
                sid = f"{src.rel}#{index}"
                body_start = (head.end if head else start)
                span = Span(src.rel, start, end)
                body = Span(src.rel, body_start, end)
                sec = Section(id=sid, title=title.strip(), level=level,
                              span=span, body=body, number=number,
                              derived_number=derived, parent_id=parent,
                              order=order)
                sec.words = len(T.word_list(
                    self._prose[src.rel][body_start:end]))
                self.sections.append(sec)
                stack.append((level, sid))
                order += 1
        self._by_id = {s.id: s for s in self.sections}

    # -- access -----------------------------------------------------------

    def section(self, sid: str) -> Section | None:
        return self._by_id.get(sid)

    def file(self, rel: str) -> SourceFile | None:
        if len(self._by_rel) != len(self.files):
            self._by_rel = {src.rel: src for src in self.files}
        return self._by_rel.get(rel)

    def blocks_in(self, sec: Section) -> list[T.Block]:
        """The blocks that START inside a section's body — a bisect.

        Every per-section loop used to walk every block of the section's
        FILE, which is quadratic in one big file — and a `.docx` is
        always one big file: 3,000 sections took 7.9 s in `paragraphs()`
        and as long again in the definitions check.
        """
        src = self.file(sec.path)
        if src is None:
            return []
        starts = self._starts.get(src.rel)
        if starts is None or len(starts) != len(src.blocks):
            src.blocks.sort(key=lambda b: b.start)
            starts = self._starts[src.rel] = [b.start for b in src.blocks]
        lo = bisect.bisect_left(starts, sec.body.start)
        hi = bisect.bisect_left(starts, sec.body.end, lo)
        return src.blocks[lo:hi]

    def raw(self, sec: Section) -> str:
        src = self.file(sec.path)
        return src.text[sec.body.start:sec.body.end] if src else ""

    def prose(self, sec: Section) -> str:
        """The section's prose, masked — tables and code blanked, offsets
        still true to the file."""
        text = self._prose.get(sec.path, "")
        return text[sec.body.start:sec.body.end]

    def prose_of_file(self, rel: str) -> str:
        return self._prose.get(rel, "")

    def label(self, sec: Section) -> str:
        """What a human calls this section — the author's own number when
        there is one, because a reference the reader cannot see is a
        reference this tool invented."""
        if sec.number:
            return f"§{sec.number} {sec.title}".strip()
        return sec.title or sec.derived_number

    def children(self, sec: Section) -> list[Section]:
        return [s for s in self.sections if s.parent_id == sec.id]

    def chapters(self) -> list[Section]:
        """Top-level sections — chapters in a novel, parts in a manual."""
        tops = [s for s in self.sections if not s.parent_id]
        return tops or self.sections

    def leaves(self) -> list[Section]:
        parents = {s.parent_id for s in self.sections if s.parent_id}
        return [s for s in self.sections if s.id not in parents]

    def sentences_of_file(self, rel: str) -> list[tuple[int, int]]:
        """Sentence spans over one file's prose, computed once.

        Every check that walks sentences and every `quote()` shares this.
        """
        hit = self._sent.get(rel)
        if hit is None:
            hit = T.sentences(self._prose.get(rel, ""))
            self._sent[rel] = hit
            self._sent_at[rel] = [s for s, _e in hit]
        return hit

    def sentence_at(self, span: Span) -> tuple[int, int] | None:
        """The sentence containing a span — a bisect, not a scan."""
        spans = self.sentences_of_file(span.path)
        starts = self._sent_at[span.path]
        i = bisect.bisect_right(starts, span.start) - 1
        if 0 <= i < len(spans) and spans[i][0] <= span.start < spans[i][1]:
            return spans[i]
        return None

    def paragraphs(self, sec: Section | None = None) -> list[Paragraph]:
        key = sec.id if sec is not None else ""
        cached = self._paras.get(key)
        if cached is not None:
            return cached
        out: list[Paragraph] = []
        targets = [sec] if sec else self.sections
        for target in targets:
            if target is None:
                continue
            src = self.file(target.path)
            if not src:
                continue
            idx = 0
            for block in self.blocks_in(target):
                if not block.is_prose:
                    continue
                masked = self._prose[src.rel][block.start:block.end]
                if not masked.strip():
                    continue
                out.append(Paragraph(
                    section_id=target.id, index=idx, text=masked.strip(),
                    span=Span(src.rel, block.start, block.end)))
                idx += 1
        self._paras[key] = out
        return out

    def scenes(self, sec: Section) -> list[Span]:
        """Scene spans inside one chapter, split on the usual break marks.

        A novel with no scene markers gets one scene per chapter, which is
        the correct answer rather than a degraded one: POV drift and pacing
        are then measured at chapter grain and say so.
        """
        src = self.file(sec.path)
        if not src:
            return []
        marks = [b.start for b in self.blocks_in(sec)
                 if b.kind in (T.RULE, T.PARA)
                 and _SCENE_BREAK.match(b.text.strip())]
        edges = [sec.body.start, *marks, sec.body.end]
        spans = []
        for i in range(len(edges) - 1):
            start, end = edges[i], edges[i + 1]
            if self._prose[src.rel][start:end].strip():
                spans.append(Span(src.rel, start, end))
        return spans or [Span(src.rel, sec.body.start, sec.body.end)]

    # -- summaries --------------------------------------------------------

    @property
    def words(self) -> int:
        return sum(len(T.word_list(p)) for p in self._prose.values())

    @property
    def derived_files(self) -> list[SourceFile]:
        """Files whose text this package produced rather than read."""
        return [s for s in self.files if s.derived]

    def notes(self) -> list[str]:
        """What a host should tell the author about this manuscript.

        Rule 4, as a method: a report that measured a Word document has
        to say that its offsets are not positions in the author's file,
        and one that could not read a file has to say which.
        """
        out = []
        derived = self.derived_files
        if derived:
            names = ", ".join(s.rel for s in derived[:4])
            out.append(
                f"{len(derived)} file(s) read as text rather than edited "
                f"in place ({names}"
                + ("…" if len(derived) > 4 else "")
                + "). Findings name the section and quote the sentence; "
                  "they cannot point at a position in a .docx. In a .docx, "
                  + F.NOT_READ + ".")
        for path, why in self.unreadable:
            out.append(f"Could not read {path}: {why}")
        for src in self.files:
            if src.note:
                out.append(f"{src.rel}: {src.note}.")
        if self.sidecars:
            names = ", ".join(self.sidecars[:3])
            out.append(
                f"{len(self.sidecars)} sidecar file(s) left out of the book "
                f"({names}" + ("…" if len(self.sidecars) > 3 else "")
                + "). They hold a model's working notes, not prose.")
        return out

    def outline(self, max_level: int = 6) -> list[Section]:
        return [s for s in self.sections if s.level <= max_level]

    def outline_text(self, max_level: int = 3) -> str:
        """The spine, as it goes into band 3 of the assembler. Absurdly
        cheap and globally useful: it is what stops section 31 restating
        section 7."""
        lines = []
        for sec in self.outline(max_level):
            pad = "  " * (sec.level - 1)
            num = sec.number or sec.derived_number
            lines.append(f"{pad}{num} {sec.title} ({sec.words} words)")
        return "\n".join(lines)

    def passages(self) -> list[tuple[str, str, str, int]]:
        """(text, ref, section_id, order) for whatever indexes the book."""
        out = []
        for para in self.paragraphs():
            sec = self._by_id.get(para.section_id)
            label = self.label(sec) if sec else para.section_id
            out.append((para.text, para.source_ref(label), para.section_id,
                        sec.order if sec else 0))
        return out

    def find(self, needle: str, whole_word: bool = True) -> list[Span]:
        """Every place a term appears, in the prose only.

        Used by the Codex's `reconsider` and by thread tracking. Searching
        the prose mask rather than the raw file is what keeps a term inside
        a code fence out of a continuity finding.
        """
        if not needle.strip():
            return []
        key = (needle.strip(), whole_word)
        cached = self._found.get(key)
        if cached is not None:
            return cached
        pattern = re.escape(needle.strip())
        if whole_word:
            pattern = rf"(?<!\w){pattern}(?!\w)"
        rx = re.compile(pattern, re.I)
        hits = []
        for rel, prose in self._prose.items():
            for m in rx.finditer(prose):
                hits.append(Span(rel, m.start(), m.end()))
        # The Red Thread and name drift ask for the same names one after
        # the other; without this the book is scanned twice for each.
        self._found[key] = hits
        return hits

    def section_at(self, span: Span) -> Section | None:
        """Which section a position is in — a bisect, not a scan.

        `_derive_sections` runs every section from its heading to the
        NEXT heading of any level, so the spans within a file are
        disjoint and contiguous: exactly one can contain a position, and
        the old deepest-level tie-break could never fire. This returns
        the same section and stops being O(sections) per hit — which it
        was, called once per finding, per claim and per mention.
        """
        index = self._sec_at.get(span.path)
        if index is None:
            here = [s for s in self.sections if s.path == span.path]
            here.sort(key=lambda s: s.span.start)
            index = ([s.span.start for s in here], here)
            self._sec_at[span.path] = index
        starts, here = index
        i = bisect.bisect_right(starts, span.start) - 1
        if 0 <= i < len(here) and here[i].span.start <= span.start < \
                here[i].span.end:
            return here[i]
        return None

    def quote(self, span: Span, pad: int = 0) -> str:
        """The sentence a span sits in — evidence, not a character range."""
        prose = self._prose.get(span.path, "")
        found = self.sentence_at(span)
        if found is not None:
            return " ".join(prose[found[0]:found[1]].split())
        lo = max(0, span.start - pad)
        return " ".join(prose[lo:span.end + pad].split())
