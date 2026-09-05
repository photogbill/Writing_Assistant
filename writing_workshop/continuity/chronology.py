# SPDX-License-Identifier: Apache-2.0
"""Time: when things happen, and where the document disagrees with itself.

ATK already builds temporal edges with a date and a time on them
(`atk/core/comms.py`). A narrative chronology is the same shape — events
with times and participants — which is why this module is small: it reads
times out of prose and hands them to the same comparison the numeric check
uses.

It answers "chapter 12 happens on Tuesday but chapter 9 put the wedding on
Wednesday", and in a manual, "step 7 says wait 20 minutes; the summary says
15."
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .. import textio as T
from ..types import Span

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday")
MONTHS = ("january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december")

_MARKERS = (
    (re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b", re.I), "weekday"),
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), "date"),
    (re.compile(r"\b(\d{1,2}\s+(?:" + "|".join(MONTHS) + r")\b[^.,;]{0,8})",
                re.I), "date"),
    (re.compile(r"\b(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\b", re.I), "clock"),
    (re.compile(r"\b((?:the\s+)?(?:next|following|previous|last)\s+"
                r"(?:morning|evening|night|day|week|month|year))\b", re.I),
     "relative"),
    (re.compile(r"\b((?:a|one|two|three|four|five|six|seven|eight|nine|ten|"
                r"eleven|twelve|\d+)\s+(?:minutes?|hours?|days?|weeks?|"
                r"months?|years?)\s+(?:later|earlier|before|after|ago))\b",
                re.I), "relative"),
    (re.compile(r"\b(\d+\s*(?:minutes?|hours?|seconds?|days?))\b", re.I),
     "duration"),
)


@dataclass
class Moment:
    kind: str
    text: str
    span: Span
    section_id: str
    section_label: str
    order: int
    quote: str = ""


def timeline(doc) -> list[Moment]:
    """Every time-marker in the document, in reading order.

    A timeline, not an interpretation. The workshop shows it and lets the
    author read it — which is the honest thing to do with a signal this
    noisy, and is also the one view that makes a chronology error obvious
    to a human in about four seconds.
    """
    out: list[Moment] = []
    seen: set[tuple[str, int]] = set()
    for sec in doc.sections:
        prose = doc.prose_of_file(sec.path)
        body = prose[sec.body.start:sec.body.end]
        for rx, kind in _MARKERS:
            for m in rx.finditer(body):
                start = sec.body.start + m.start(1)
                key = (sec.path, start)
                if key in seen:
                    continue
                seen.add(key)
                span = Span(sec.path, start, sec.body.start + m.end(1))
                out.append(Moment(kind, m.group(1).strip(), span, sec.id,
                                  doc.label(sec), sec.order,
                                  doc.quote(span)))
    out.sort(key=lambda mo: (mo.order, mo.span.start))
    return out


def weekday_runs(moments: list[Moment]) -> list[tuple[str, list[Moment]]]:
    """Weekday mentions grouped in reading order — the view that makes
    "Tuesday, then Wednesday, then Monday" visible without asserting that
    it is wrong. Flashbacks exist."""
    runs: list[tuple[str, list[Moment]]] = []
    for moment in moments:
        if moment.kind != "weekday":
            continue
        day = T.normalise(moment.text)
        if runs and runs[-1][0] == day:
            runs[-1][1].append(moment)
        else:
            runs.append((day, [moment]))
    return runs


def transitions(moments: list[Moment], kind: str = "weekday"
                ) -> list[tuple[str, list[Moment]]]:
    """Runs of one kind of marker, collapsed — the readable view.

    `timeline()` returns EVERY marker, which on a 155,000-word manuscript
    is 3,922 of them: a list nobody reads is a search result wearing a
    timeline's clothes. What a chronology error looks like is a
    TRANSITION — Tuesday, then Wednesday, then Monday — so the runs are
    what the author is shown and the full list is what they can open.
    """
    runs: list[tuple[str, list[Moment]]] = []
    for moment in moments:
        if moment.kind != kind:
            continue
        value = T.normalise(moment.text)
        if runs and runs[-1][0] == value:
            runs[-1][1].append(moment)
        else:
            runs.append((value, [moment]))
    return runs


def summarise(moments: list[Moment]) -> dict:
    """What the Continuity page shows instead of four thousand rows.

    Counts by kind, the weekday and date sequences as runs, and the
    sections carrying the most markers — which is where a reader would
    look for the error anyway.
    """
    by_kind: dict[str, int] = {}
    by_section: dict[str, int] = {}
    for moment in moments:
        by_kind[moment.kind] = by_kind.get(moment.kind, 0) + 1
        by_section[moment.section_label] = by_section.get(
            moment.section_label, 0) + 1
    busiest = sorted(by_section.items(), key=lambda kv: -kv[1])[:8]
    return {
        "total": len(moments),
        "by_kind": by_kind,
        "weekday_sequence": [day for day, _ms in transitions(moments)],
        "date_sequence": [value for value, _ms
                          in transitions(moments, "date")][:40],
        "busiest_sections": busiest,
    }


def out_of_order(moments: list[Moment]) -> list[tuple[Moment, Moment]]:
    """Consecutive DATES that go backwards, in reading order.

    Offered as a view and never as a defect: flashbacks exist, and a tool
    that called one an error would be wrong in the most annoying possible
    way. Only ISO dates are compared, because those are the only markers
    here that carry an unambiguous order.
    """
    dated = [m for m in moments
             if m.kind == "date" and re.fullmatch(r"\d{4}-\d{2}-\d{2}",
                                                  m.text.strip())]
    out = []
    for a, b in zip(dated, dated[1:], strict=False):
        if b.text.strip() < a.text.strip():
            out.append((a, b))
    return out


def durations(doc) -> dict[str, list[Moment]]:
    """Durations keyed by the step or procedure they belong to.

    The manual half of chronology: "step 7 says wait 20 minutes; the
    summary says 15" is the same defect as a wedding on two days, found
    the same way.
    """
    out: dict[str, list[Moment]] = {}
    for moment in timeline(doc):
        if moment.kind != "duration":
            continue
        out.setdefault(moment.section_id, []).append(moment)
    return out
