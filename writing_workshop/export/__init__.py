# SPDX-License-Identifier: Apache-2.0
"""Export that respects the destination.

Two destinations, and they want opposite things. A novel goes out in
**Shunn manuscript format** — double-spaced Courier, a title page with a
word count rounded to the nearest hundred, `#` for a scene break — because
that is what a submission reader expects and deviating from it is the first
thing they notice. A manual goes out as a **numbered .docx with a table of
contents**, because that is the shape a specification ships in.

The core builds the STRUCTURE and never touches python-docx: everything
here returns markdown or a spec object, and the host renders it. That is
what keeps this package's runtime dependency list empty, and it is why
ATK's existing `reports.markdown_to_docx` can do the technical half with no
new code at all.
"""

from __future__ import annotations

from .shunn import ShunnSpec, shunn_markdown, shunn_spec
from .technical import numbered_markdown, toc_lines

__all__ = ["ShunnSpec", "shunn_spec", "shunn_markdown", "numbered_markdown",
           "toc_lines", "plain_markdown"]


def plain_markdown(doc) -> str:
    """The manuscript as one file, in reading order. The fallback that
    always works and never loses a word."""
    parts = []
    for src in doc.files:
        parts.append(src.text.rstrip())
    return "\n\n".join(parts) + "\n"
