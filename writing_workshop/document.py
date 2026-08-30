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

from dataclasses import dataclass, field
from pathlib import Path
import re

from . import textio as T
from .errors import ProjectError
from .types import Paragraph, Section, Span

#: What counts as manuscript. `.txt` is included because a great many
#: novels are written in one, and refusing to read them would be a purity
#: the author pays for.
SUFFIXES = (".md", ".markdown", ".txt")

#: Never walked into. `.workshop` is ours; the rest are the folders every
#: project grows and none of them are the book.
SKIP_DIRS = {".workshop", ".git", "__pycache__", "_to_delete", "backups",
             "node_modules", ".venv", "exports", "audio"}

_NUMBERED = re.compile(r"^\s*((?:\d+|[A-Z])(?:\.\d+)*)[.)]?\s+(.*)$")
_SCENE_BREAK = re.compile(r"^\s*(\*\s*\*\s*\*|#\s*#\s*#|---|\* \* \*|#)\s*$")


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

    @property
    def stem(self) -> str:
        return self.path.stem


@dataclass
class Manuscript:
    """Every file, every section, in reading order."""

    root: Path
    files: list[SourceFile] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    _by_id: dict[str, Section] = field(default_factory=dict)
    _prose: dict[str, str] = field(default_factory=dict)

    # -- loading ----------------------------------------------------------

    @classmethod
    def load(cls, root: str | Path) -> "Manuscript":
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
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # A manuscript written on Windows in a previous decade. Read
                # it rather than refusing it; the author cares about the
                # book, not about its encoding.
                text = path.read_text(encoding="cp1252", errors="replace")
            rel = (path.name if root.is_file()
                   else str(path.relative_to(root)).replace("\\", "/"))
            src = SourceFile(path=path, rel=rel, text=text,
                             blocks=T.scan_blocks(text))
            src.prose = T.prose_of(text)
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
            lead = src.text[:first]
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
        for src in self.files:
            if src.rel == rel:
                return src
        return None

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

    def paragraphs(self, sec: Section | None = None) -> list[Paragraph]:
        out: list[Paragraph] = []
        targets = [sec] if sec else self.sections
        for target in targets:
            if target is None:
                continue
            src = self.file(target.path)
            if not src:
                continue
            idx = 0
            for block in src.blocks:
                if not block.is_prose:
                    continue
                if not (target.body.start <= block.start < target.body.end):
                    continue
                masked = self._prose[src.rel][block.start:block.end]
                if not masked.strip():
                    continue
                out.append(Paragraph(
                    section_id=target.id, index=idx, text=masked.strip(),
                    span=Span(src.rel, block.start, block.end)))
                idx += 1
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
        marks = [b.start for b in src.blocks
                 if b.kind in (T.RULE, T.PARA)
                 and sec.body.start <= b.start < sec.body.end
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
        pattern = re.escape(needle.strip())
        if whole_word:
            pattern = rf"(?<!\w){pattern}(?!\w)"
        rx = re.compile(pattern, re.I)
        hits = []
        for rel, prose in self._prose.items():
            for m in rx.finditer(prose):
                hits.append(Span(rel, m.start(), m.end()))
        return hits

    def section_at(self, span: Span) -> Section | None:
        best = None
        for sec in self.sections:
            if sec.path == span.path and sec.span.start <= span.start < sec.span.end:
                if best is None or sec.level >= best.level:
                    best = sec
        return best

    def quote(self, span: Span, pad: int = 0) -> str:
        """The sentence a span sits in — evidence, not a character range."""
        prose = self._prose.get(span.path, "")
        for start, end in T.sentences(prose):
            if start <= span.start < end:
                return " ".join(prose[start:end].split())
        lo = max(0, span.start - pad)
        return " ".join(prose[lo:span.end + pad].split())
