# SPDX-License-Identifier: Apache-2.0
"""Numbered-section export with a table of contents.

The format a manual actually ships in. Numbering uses the AUTHOR'S own
numbers wherever the headings carry them, and derived ones only where they
do not — renumbering a document on export is how a cross-reference that was
correct on Friday points at the wrong clause on Monday.
"""

from __future__ import annotations


def toc_lines(doc, max_level: int = 3) -> list[str]:
    out = []
    for sec in doc.outline(max_level):
        number = sec.number or sec.derived_number
        indent = "    " * (sec.level - 1)
        out.append(f"{indent}{number} {sec.title}")
    return out


def numbered_markdown(doc, *, title: str = "", subtitle: str = "",
                      max_level: int = 3, include_toc: bool = True) -> str:
    """One markdown document, numbered, with a contents list.

    Deliberately the limited subset ATK's `reports.markdown_to_docx`
    already renders — headings, bullets, bold, italic. Emitting markdown
    the existing converter cannot read would mean writing a second
    converter to ship a feature that is really a re-order of the text.
    """
    lines: list[str] = []
    if title:
        lines += [f"# {title}", ""]
    if subtitle:
        lines += [f"*{subtitle}*", ""]
    if include_toc:
        lines += ["## Contents", ""]
        for entry in toc_lines(doc, max_level):
            lines.append(f"- {entry}")
        lines.append("")
    for sec in doc.sections:
        number = sec.number or sec.derived_number
        hashes = "#" * min(6, sec.level + (1 if title else 0))
        lines.append(f"{hashes} {number} {sec.title}".rstrip())
        lines.append("")
        body = doc.raw(sec).strip()
        if body:
            lines.append(body)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
