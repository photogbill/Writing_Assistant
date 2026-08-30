# SPDX-License-Identifier: Apache-2.0
"""Continuity — the part worth building the rest for.

**The document never has to fit.** Whole-document work here is map-reduce,
not one enormous prompt. The MAP pass — extract claims, measure, summarise
— needs only one section plus the invariant band, so it works at a 10k
context as well as at 75k. The REDUCE pass is an indexed lookup over a
table, not an inference call. A forty-section manual is forty small passes
and a join, which is exactly the shape ATK's `render_queue` already has.

So the context window stops being a ceiling on document size and becomes a
ceiling on how much of ONE PASS is visible at once — a much lower bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..types import DEFECT, WARN, Claim, Conflict, Finding, Thread
from . import chronology, contradictions, namedrift, threads
from .chronology import Moment, timeline
from .namedrift import Variant

__all__ = ["sweep", "Sweep", "map_sections", "contradictions", "threads",
           "chronology", "namedrift", "Moment", "Variant", "timeline"]


@dataclass
class Sweep:
    conflicts: list[Conflict] = field(default_factory=list)
    threads: list[Thread] = field(default_factory=list)
    dropped: list[Thread] = field(default_factory=list)
    variants: list[Variant] = field(default_factory=list)
    moments: list[Moment] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def problems(self) -> list[Finding]:
        return [f for f in self.findings if f.is_problem]


def map_sections(doc, fn: Callable, *, events=None, cancel=None,
                 label: str = "pass") -> list:
    """Run one pass per section and collect the results.

    The MAP half, made explicit because it is the shape every whole-
    document operation in this package takes — and because a forty-section
    sweep that says nothing for two minutes is indistinguishable from a
    hang, which ATK has shipped before.
    """
    out = []
    total = len(doc.sections)
    for i, sec in enumerate(doc.sections, 1):
        if cancel is not None and cancel.is_set():
            break
        if events is not None:
            events.emit("progress", f"{label}: {doc.label(sec)}", i=i,
                        n=total)
        try:
            result = fn(sec)
        except Exception as exc:                      # noqa: BLE001
            if events is not None:
                events.emit("warning", f"{label} failed on "
                            f"{doc.label(sec)}: {exc}")
            continue
        if result:
            out.extend(result if isinstance(result, list) else [result])
    return out


def sweep(doc, claims: list[Claim] | None = None, *,
          cast: list[str] | None = None, terms: list[str] | None = None,
          events=None, cancel=None) -> Sweep:
    """The whole-document continuity pass. No model required.

    Everything here is deterministic or explicitly a candidate. A model
    can be asked afterwards to adjudicate an attribute conflict, and its
    answer arrives as a suggestion beside the two quoted passages — never
    as an edit, and never as a claim promoted without the author.
    """
    result = Sweep()
    if events is not None:
        events.emit("progress", "continuity: comparing claims")
    result.conflicts = contradictions.find(claims or [])
    for conflict in result.conflicts:
        result.findings.append(_conflict_finding(doc, conflict))

    if cancel is not None and cancel.is_set():
        return result

    if events is not None:
        events.emit("progress", "continuity: tracking threads")
    names = threads.candidates(doc, list(cast or []), list(terms or []))
    result.threads = threads.track(doc, names)
    result.dropped = threads.dropped(doc, result.threads)
    total = len(doc.sections) or 1
    for thread in result.dropped:
        last = doc.sections[min(thread.last_order, total - 1)]
        result.findings.append(Finding(
            "dropped_thread", WARN,
            f"“{thread.name}” is introduced, developed, and then dropped",
            f"{thread.count} mentions across {len(thread.sections)} "
            f"sections, the last in {doc.label(last)}, and nothing after "
            f"it. Chekhov's gun, found by arithmetic — the tool has no "
            f"opinion about whether it should fire.",
            section_id=last.id, span=last.body,
            evidence=[doc.quote(span) for _o, span in thread.mentions[:2]],
            data={"name": thread.name, "mentions": thread.count,
                  "emphasis": thread.emphasis,
                  "last_section": doc.label(last)}))

    if events is not None:
        events.emit("progress", "continuity: names and terminology")
    result.variants = namedrift.find(doc, names)
    for variant in result.variants:
        forms = ", ".join(f"“{f}” ×{variant.counts[f]}"
                          for f in variant.forms)
        result.findings.append(Finding(
            "name_drift", WARN,
            f"{len(variant.forms)} names that may be one: {forms}",
            f"Proposed because {variant.reason}. Nothing has been merged — "
            f"the tool does not decide who is who.",
            data={"forms": variant.forms, "counts": variant.counts,
                  "reason": variant.reason}))

    if events is not None:
        events.emit("progress", "continuity: chronology")
    result.moments = chronology.timeline(doc)
    result.metrics = {
        "claims": len(claims or []), "conflicts": len(result.conflicts),
        "deterministic_conflicts": sum(1 for c in result.conflicts
                                       if c.deterministic),
        "threads": len(result.threads), "dropped": len(result.dropped),
        "name_groups": len(result.variants),
        "time_markers": len(result.moments),
        "weekday_runs": len(chronology.weekday_runs(result.moments)),
    }
    return result


def _conflict_finding(doc, conflict: Conflict) -> Finding:
    a, b = conflict.a, conflict.b
    if conflict.deterministic:
        title = (f"{a.subject}: {a.value} in {a.source_ref}, "
                 f"{b.value} in {b.source_ref}")
        severity = DEFECT
    else:
        title = (f"{a.subject} may be described two ways: “{a.value}” and "
                 f"“{b.value}”")
        severity = WARN
    return Finding(
        "contradiction", severity, title, conflict.detail,
        span=a.span, section_id=a.section_id,
        evidence=[q for q in (a.quote, b.quote) if q],
        data={"kind": conflict.kind, "deterministic": conflict.deterministic,
              "a": a.id, "b": b.id})
