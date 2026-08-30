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
        """Shunn rounds: 'about 74,000 words', never 73,842."""
        if self.word_count < 1500:
            return round(self.word_count, -2)
        if self.word_count < 10000:
            return round(self.word_count, -3) or 1000
        return round(self.word_count, -3)


def _short_title(title: str, limit: int = 3) -> str:
    words = [w for w in title.split() if w.lower() not in
             {"a", "an", "the", "of", "and"}]
    return " ".join(words[:limit]) or title


def shunn_spec(doc, *, title: str = "", author: str = "",
               legal_name: str = "", address: list[str] | None = None,
               email: str = "", phone: str = "") -> ShunnSpec:
    chapters: list[tuple[str, list[str]]] = []
    for sec in doc.chapters():
        paragraphs: list[str] = []
        prose = doc.prose_of_file(sec.path)
        for scene_no, scene in enumerate(doc.scenes(sec)):
            if scene_no:
                paragraphs.append("#")
            for para in doc.paragraphs(sec):
                if not (scene.start <= para.span.start < scene.end):
                    continue
                text = " ".join(para.text.split())
                if text and text != "#":
                    paragraphs.append(text)
        chapters.append((sec.title, paragraphs))
        del prose
    words = doc.words
    name = author or legal_name
    surname = name.split()[-1] if name else ""
    spec = ShunnSpec(
        title=title or (doc.chapters()[0].title if doc.chapters() else ""),
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
        lines.append(f"## {title}")
        lines.append("")
        for para in paragraphs:
            lines.append(para)
            lines.append("")
    lines.append("THE END")
    return "\n".join(lines).rstrip() + "\n"
