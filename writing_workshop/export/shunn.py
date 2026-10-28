# SPDX-License-Identifier: Apache-2.0
"""Shunn manuscript format, for fiction submission.

The conventions are not decoration and a reader notices every deviation:
contact block top-left, word count top-right rounded to the nearest
hundred, the title a third of the way down, a new page per chapter, `#`
alone on a line for a scene break, and `THE END` at the end. Courier or
Times, 12pt, double-spaced, half-inch first-line indents, a running header
of `Surname / Short Title / page`.

Markdown cannot express double-spacing or a running header, so this module
produces both: a `ShunnSpec` carrying the parts a .docx renderer needs, and
markdown for everything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field



@dataclass
class ShunnSpec:
    title: str = ""
    author: str = ""            # the byline
    legal_name: str = ""        # the name on the contract, top-left
    address: list[str] = field(default_factory=list)
    email: str = ""
    phone: str = ""
    word_count: int = 0
    running_header: str = ""
    chapters: list[tuple[str, list[str]]] = field(default_factory=list)
    scene_break: str = "#"
    font: str = "Courier New"
    point_size: int = 12
    line_spacing: float = 2.0
    first_line_indent_inches: float = 0.5

    @property
    def rounded_words(self) -> int:
        """Shunn rounds: 'about 1,500 words', never 1,486.

        FIXED 2026-10-28. This rounded to the nearest THOUSAND from 1,500
        words up, so 1,507 words was "about 2,000" — where Shunn's own page
        rounds its 1,486-word example to 1,500. His rule: the nearest
        hundred, and the nearest 500 "if you're edging into novella
        territory" (taken here as 17,500 words, the SFWA novelette ceiling).
        He gives no novel rule; the nearest thousand from 40,000 is the
        common practice and is labelled as that. Half rounds UP — Python's
        `round` rounds half to even, which made 1,250 "about 1,200". Under
        a hundred words the exact count is given: "about 0 words" is not a
        word count.
        """
        n = int(self.word_count)
        if n < 100:
            return n
        step = 100 if n < 17500 else 500 if n < 40000 else 1000
        return (n + step // 2) // step * step


def _short_title(title: str, limit: int = 3) -> str:
    words = [w for w in title.split() if w.lower() not in
             {"a", "an", "the", "of", "and"}]
    return " ".join(words[:limit]) or title


def _descendants(doc, sec) -> list:
    """Every section under `sec`, in reading order."""
    out, parents = [], {sec.id}
    for other in doc.sections:
        if other.parent_id in parents:
            out.append(other)
            parents.add(other.id)
    return out


def _chapter_level(doc) -> tuple[list, str]:
    """The sections that are the CHAPTERS, and a book title if one heads
    them.

    FIXED 2026-10-28. A novel written as `# The Long Road` with `## Chapter
    One`, `## Chapter Two` beneath it exported as the title, then THE END,
    with no prose at all: the export walked the top-level sections, and a
    section's body stops at the next heading of ANY level, so every
    chapter's prose belonged to a child the export never visited. One top
    heading over several children is a title over chapters; and prose under
    a chapter's own sub-headings is gathered into the chapter.
    """
    tops = doc.chapters()
    if len(tops) == 1:
        children = [s for s in doc.sections if s.parent_id == tops[0].id]
        if len(children) > 1:
            return children, tops[0].title
    return tops, ""


def _paragraphs_of(doc, parts) -> list[str]:
    paragraphs: list[str] = []
    for part_no, part in enumerate(parts):
        if part_no and paragraphs and paragraphs[-1] != "#":
            paragraphs.append("#")
        for scene_no, scene in enumerate(doc.scenes(part)):
            if scene_no and paragraphs and paragraphs[-1] != "#":
                paragraphs.append("#")
            for para in doc.paragraphs(part):
                if not (scene.start <= para.span.start < scene.end):
                    continue
                text = " ".join(para.text.split())
                if text and text != "#":
                    paragraphs.append(text)
    while paragraphs and paragraphs[-1] == "#":
        paragraphs.pop()
    return paragraphs


def shunn_spec(doc, *, title: str = "", author: str = "",
               legal_name: str = "", address: list[str] | None = None,
               email: str = "", phone: str = "") -> ShunnSpec:
    chapters: list[tuple[str, list[str]]] = []
    tops, book_title = _chapter_level(doc)
    if book_title:
        # Prose under the TITLE heading itself — an untitled opening, an
        # epigraph — before the first chapter. Only the children were
        # exported, so it vanished without a word (found by the
        # independent check). It goes first, as a section with no heading.
        head = doc.chapters()[0]
        opening = _paragraphs_of(doc, [head])
        if opening:
            chapters.append(("", opening))
    for sec in tops:
        chapters.append((sec.title,
                         _paragraphs_of(doc, [sec, *_descendants(doc, sec)])))
    words = doc.words
    name = author or legal_name
    surname = name.split()[-1] if name else ""
    spec = ShunnSpec(
        title=title or book_title
        or (doc.chapters()[0].title if doc.chapters() else ""),
        author=author, legal_name=legal_name or author,
        address=list(address or []), email=email, phone=phone,
        word_count=words, chapters=chapters)
    spec.running_header = " / ".join(
        p for p in (surname, _short_title(spec.title)) if p)
    return spec


def shunn_markdown(spec: ShunnSpec) -> str:
    """Shunn as markdown — everything the format expresses in text.

    The typographic half (double spacing, the running header, the indents)
    travels in the spec for a .docx renderer; a markdown reader still gets
    a correctly ORDERED manuscript with proper scene breaks, which is the
    half that matters when the author is proofreading rather than
    submitting.
    """
    lines: list[str] = []
    block = [spec.legal_name, *spec.address, spec.phone, spec.email]
    for entry in block:
        if entry:
            lines.append(entry)
    lines.append("")
    lines.append(f"about {spec.rounded_words:,} words")
    lines.append("")
    lines.append(f"# {spec.title}")
    if spec.author:
        lines.append("")
        lines.append(f"by {spec.author}")
    for title, paragraphs in spec.chapters:
        lines.append("")
        if title:
            lines.append(f"## {title}")
            lines.append("")
        for para in paragraphs:
            lines.append(para)
            lines.append("")
    lines.append("THE END")
    return "\n".join(lines).rstrip() + "\n"
