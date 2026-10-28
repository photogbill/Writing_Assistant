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
    old_gaps = _gaps(old, old_spans)
    new_gaps = _gaps(new, new_spans)
    old_lead = old[:old_spans[0][0]] if old_spans else old
    new_lead = new[:new_spans[0][0]] if new_spans else new
    old_tail = old[old_spans[-1][1]:] if old_spans else ""
    new_tail = new[new_spans[-1][1]:] if new_spans else ""
    matcher = difflib.SequenceMatcher(
        None, [_norm(s) for s in old_sents], [_norm(s) for s in new_sents],
        autojunk=False)
    hunks: list[Hunk] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        hunks.append(Hunk(
            op=op, old=old_sents[i1:i2], new=new_sents[j1:j2],
            old_span=_bounds(old_spans, i1, i2, len(old)),
            new_span=_bounds(new_spans, j1, j2, len(new)),
            id=len(hunks), old_gaps=old_gaps[i1:i2],
            new_gaps=new_gaps[j1:j2], old_lead=old_lead, new_lead=new_lead,
            old_tail=old_tail, new_tail=new_tail))
    return hunks


def _gaps(text: str, spans: list[tuple[int, int]]) -> list[str]:
    """The whitespace after each sentence, up to the next one (or the end
    of the text, for the last)."""
    out = []
    for k, (_s, e) in enumerate(spans):
        nxt = spans[k + 1][0] if k + 1 < len(spans) else len(text)
        out.append(text[e:nxt])
    return out


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

    THE WHITESPACE IS THE WHOLE DIFFICULTY, and the first two versions of
    this got it wrong. Sentence spans exclude the space BETWEEN sentences,
    and the old rebuild invented one — a single space — wherever a taken
    hunk met the text around it. Measured 2026-10-28, five of six ordinary
    edits came back corrupted: `One. Two.Three.`, `One.Two. Three.`, a
    deleted paragraph leaving four newlines, an inserted paragraph glued on
    as `B two.C three.`, a deleted last sentence leaving a trailing space.
    Silent corruption by the one feature whose promise is that it does not
    corrupt the author's text.

    Now every sentence carries the whitespace that FOLLOWED it in its own
    text, and the rebuild never invents a separator:

    * between two sentences that were neighbours in the same text, the
      separator they had;
    * where the rebuild jumps (a deletion, or old text meeting new), the
      separator after the first — unless that was its text's ending, in
      which case the separator before the second;
    * the lead and the tail come from whichever text the first and last
      hunks were taken from.

    `apply(old, diff(old, new)) == new` is a property test now, over
    random paragraph, heading and blank-line edits.
    """
    if not hunks:
        return old

    def taken(hunk: Hunk) -> bool:
        return hunk.op != EQUAL and (accepted is None or hunk.id in accepted)

    # The hunk holding each text's LAST sentence: its trailing gap is that
    # text's ending, not a separator owed to anything.
    last_old = max((i for i, h in enumerate(hunks) if h.old), default=-1)
    last_new = max((i for i, h in enumerate(hunks) if h.new), default=-1)

    pieces: list[tuple[str, str | None]] = []    # sentence, separator owed
    for index, hunk in enumerate(hunks):
        use_new = taken(hunk)
        sents = hunk.new if use_new else hunk.old
        gaps = hunk.new_gaps if use_new else hunk.old_gaps
        if len(gaps) != len(sents):              # a Hunk built elsewhere
            gaps = [" "] * len(sents)
        nxt = hunks[index + 1] if index + 1 < len(hunks) else None
        for k, sentence in enumerate(sents):
            if k + 1 < len(sents):
                pieces.append((sentence, gaps[k]))
                continue
            # The separator after this hunk's last sentence. An unchanged
            # stretch followed by a TAKEN change is crossing into the new
            # text, so it owes the NEW text's separator — which is what
            # keeps the paragraph break when the last sentence of a
            # paragraph is deleted.
            if (hunk.op == EQUAL and nxt is not None and taken(nxt)
                    and len(hunk.new_gaps) == len(hunk.new)):
                gap, ends = hunk.new_gaps[-1], index == last_new
            else:
                gap = gaps[-1]
                ends = index == (last_new if use_new else last_old)
            pieces.append((sentence, None if ends else gap))

    out = [hunks[0].new_lead if taken(hunks[0]) else hunks[0].old_lead]
    for k, (sentence, _owed) in enumerate(pieces):
        if k:
            out.append(pieces[k - 1][1] or " ")
        out.append(sentence)
    if pieces:
        out.append(hunks[-1].new_tail if taken(hunks[-1])
                   else hunks[-1].old_tail)
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
