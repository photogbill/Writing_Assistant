# SPDX-License-Identifier: Apache-2.0
"""The Red Thread — and the check that falls out of doing it properly.

The original plan described semantic search with a timeline view, which is
a search box. The useful version tracks a thread's STATE: where it is
introduced, where it is developed, where it is resolved, and where it goes
quiet. Out of that falls the check nobody offers:

    **Dropped-thread detection.** An entity introduced with emphasis,
    mentioned in three chapters, then absent for the remaining twelve with
    no resolution. Chekhov's gun, found by arithmetic.

In a manual the same measurement finds the section that references a
subsystem the document never explains again — the reader is left holding
it.
"""

from __future__ import annotations

from collections import defaultdict
import re

from .. import textio as T
from ..types import Thread

#: A thread is "carried to the end" if it reaches the last slice of the
#: document. Deliberately generous: the tool is looking for things that
#: VANISH, and a mention in the final fifth is not a vanishing.
TAIL_SHARE = 0.18


def track(doc, names: list[str]) -> list[Thread]:
    """Where each named thing appears, and how loudly it arrived."""
    threads: list[Thread] = []
    sections = doc.sections
    total = len(sections) or 1
    for name in names:
        hits = doc.find(name)
        if not hits:
            continue
        thread = Thread(name=name)
        for span in hits:
            sec = doc.section_at(span)
            order = sec.order if sec else 0
            thread.mentions.append((order, span))
            if sec:
                thread.sections.add(sec.id)
        thread.mentions.sort(key=lambda pair: pair[0])
        thread.first_order = thread.mentions[0][0]
        thread.last_order = thread.mentions[-1][0]
        thread.emphasis = _emphasis(doc, name, thread)
        if thread.last_order >= total * (1 - TAIL_SHARE):
            thread.resolved_at = thread.last_order
        threads.append(thread)
    threads.sort(key=lambda t: -t.count)
    return threads


def _emphasis(doc, name: str, thread: Thread) -> float:
    """How loudly a thread was introduced.

    Three cheap signals, and they are the ones that survive contact with
    real manuscripts: it is in a heading; it appears more than once in the
    paragraph that introduces it; that paragraph is near the top of its
    section. A thing introduced quietly and dropped is usually fine. A
    thing introduced with a fanfare and dropped is the finding.
    """
    score = 0.0
    first_order, first_span = thread.mentions[0]
    sec = doc.section_at(first_span)
    if sec and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", sec.title,
                         re.I):
        score += 2.0
    if sec:
        offset = first_span.start - sec.body.start
        if offset < 400:
            score += 1.0
    for para in doc.paragraphs(sec):
        if para.span.start <= first_span.start < para.span.end:
            count = len(re.findall(rf"(?<!\w){re.escape(name)}(?!\w)",
                                   para.text, re.I))
            score += min(2.0, count - 1)
            break
    return score


def dropped(doc, threads: list[Thread], *, min_sections: int = 2,
            min_gap: int | None = None, min_emphasis: float = 1.0
            ) -> list[Thread]:
    """Threads introduced with emphasis, developed, and then abandoned."""
    total = len(doc.sections) or 1
    gap = min_gap if min_gap is not None else max(3, total // 4)
    out = []
    for thread in threads:
        if thread.resolved_at is not None:
            continue
        if len(thread.sections) < min_sections:
            continue
        if thread.emphasis < min_emphasis:
            continue
        if total - 1 - thread.last_order < gap:
            continue
        out.append(thread)
    return sorted(out, key=lambda t: (-t.emphasis, -t.count))


def gaps(doc, thread: Thread) -> list[tuple[int, int]]:
    """The stretches of the document where a live thread goes quiet."""
    orders = sorted({order for order, _s in thread.mentions})
    out = []
    for a, b in zip(orders, orders[1:]):
        if b - a > 1:
            out.append((a, b))
    return out


def candidates(doc, cast: list[str], terms: list[str],
               minimum: int = 3) -> list[str]:
    """What to track, when the project has not said.

    Proper nouns and hyphenated terms that appear at least a few times.
    Deliberately not every capitalised word: a thread list nobody reads is
    a thread list that hides the one dropped thread that mattered.
    """
    named = list(dict.fromkeys([*cast, *terms]))
    if named:
        return named
    counts: defaultdict[str, int] = defaultdict(int)
    surface: dict[str, str] = {}
    for src in doc.files:
        prose = doc.prose_of_file(src.rel)
        for m in re.finditer(r"\b[A-Z][a-z]{3,}(?:[- ][A-Z][a-z]{2,})?\b",
                             prose):
            word = m.group(0)
            if T.is_common(word):
                continue
            key = T.term_key(word)
            counts[key] += 1
            surface.setdefault(key, word)
    return [surface[k] for k, n in
            sorted(counts.items(), key=lambda kv: -kv[1]) if n >= minimum][:60]
