# SPDX-License-Identifier: Apache-2.0
"""Sentence-level diff, because a line diff of prose is useless.

A paragraph is one line. Change one word and a line differ renders the
whole paragraph as deleted and re-added — which destroys the only thing a
version feature exists to provide. So: split to sentences, diff those,
rejoin, and offer a word-level view inside any sentence that changed.

Nothing in this module writes to disk. `apply()` returns text; whether that
text becomes the manuscript is the author's decision and the author's
keystroke.
"""

from __future__ import annotations

import difflib
import re

from . import textio as T
from .types import Hunk

EQUAL, INSERT, DELETE, REPLACE = "equal", "insert", "delete", "replace"


def split(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    """Sentences and their spans, over the RAW text.

    Raw, not masked: this feeds an editor, so the offsets have to land on
    the characters the author sees, markdown markup included.
    """
    spans = T.sentences(text)
    return [text[s:e] for s, e in spans], spans


def _norm(sentence: str) -> str:
    """What counts as "the same sentence" for matching purposes.

    Whitespace and a re-wrapped paragraph must not read as a change, or
    every reflow in an editor becomes a hundred hunks and the diff is
    noise again — the same failure as the line diff, one level down.
    """
    return " ".join(sentence.split())


def diff(old: str, new: str) -> list[Hunk]:
    """Hunks from `old` to `new`, with char spans into both."""
    old_sents, old_spans = split(old)
    new_sents, new_spans = split(new)
    matcher = difflib.SequenceMatcher(
        None, [_norm(s) for s in old_sents], [_norm(s) for s in new_sents],
        autojunk=False)
    hunks: list[Hunk] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        hunks.append(Hunk(
            op=op, old=old_sents[i1:i2], new=new_sents[j1:j2],
            old_span=_bounds(old_spans, i1, i2, len(old)),
            new_span=_bounds(new_spans, j1, j2, len(new)),
            id=len(hunks)))
    return hunks


def _bounds(spans: list[tuple[int, int]], a: int, b: int,
            fallback: int) -> tuple[int, int]:
    if a >= b:
        pos = spans[a][0] if a < len(spans) else fallback
        return (pos, pos)
    return (spans[a][0], spans[b - 1][1])


def changed(hunks: list[Hunk]) -> list[Hunk]:
    return [h for h in hunks if h.changed]


def summary(hunks: list[Hunk]) -> dict:
    counts = {EQUAL: 0, INSERT: 0, DELETE: 0, REPLACE: 0}
    for hunk in hunks:
        counts[hunk.op] = counts.get(hunk.op, 0) + max(
            len(hunk.old), len(hunk.new))
    counts["hunks"] = len(changed(hunks))
    return counts


def apply(old: str, hunks: list[Hunk], accepted: set[int] | None = None
          ) -> str:
    """Rebuild the text with the accepted hunks taken and the rest left.

    `accepted` is a set of hunk ids. None means "take everything", which
    is only ever used by a test — in the workshop the set comes from the
    author clicking, one hunk at a time.

    THE WHITESPACE IS THE WHOLE DIFFICULTY. Sentence spans exclude the
    space BETWEEN sentences, so a naive rebuild produced `Four.Five.` for
    an accepted insertion at the end and a double space for an accepted
    deletion in the middle. Both are silent corruption of the author's
    text by a feature whose entire promise is that it does not corrupt the
    author's text, so the separators are handled explicitly here rather
    than left to the spans.
    """
    out: list[str] = []
    cursor = 0
    for hunk in hunks:
        start, end = hunk.old_span
        if start > cursor:
            out.append(old[cursor:start])
        cursor = max(cursor, end)
        take = accepted is None or hunk.id in accepted
        if hunk.op == EQUAL or not take:
            out.append(old[start:end])
            continue
        replacement = " ".join(s.strip() for s in hunk.new if s.strip())
        if not replacement:
            # A deletion: drop the sentence AND the separator that
            # followed it, or the text keeps a widow space.
            while cursor < len(old) and old[cursor] in " \t":
                cursor += 1
            continue
        joined = "".join(out)
        if joined and not joined[-1].isspace() and not replacement[0].isspace():
            out.append(" ")
        out.append(replacement)
    out.append(old[cursor:])
    return "".join(out)


_TOKEN = re.compile(r"\w+|\s+|[^\w\s]")


def inline(old_sentence: str, new_sentence: str) -> list[tuple[str, str]]:
    """Word-level ops inside one replaced sentence, for display.

    The second half of making a prose diff readable: knowing WHICH
    sentence changed is not enough when the change is one word in forty.
    """
    a = _TOKEN.findall(old_sentence)
    b = _TOKEN.findall(new_sentence)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out: list[tuple[str, str]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == EQUAL:
            out.append((EQUAL, "".join(a[i1:i2])))
        elif op == DELETE:
            out.append((DELETE, "".join(a[i1:i2])))
        elif op == INSERT:
            out.append((INSERT, "".join(b[j1:j2])))
        else:
            out.append((DELETE, "".join(a[i1:i2])))
            out.append((INSERT, "".join(b[j1:j2])))
    return [(op, text) for op, text in out if text]


def render(hunks: list[Hunk], context: int = 0) -> str:
    """A plain-text rendering, for a CLI or a log."""
    lines: list[str] = []
    for hunk in hunks:
        if not hunk.changed:
            if context:
                for sentence in hunk.old[-context:]:
                    lines.append(f"  {_norm(sentence)}")
            continue
        for sentence in hunk.old:
            lines.append(f"- {_norm(sentence)}")
        for sentence in hunk.new:
            lines.append(f"+ {_norm(sentence)}")
    return "\n".join(lines)
