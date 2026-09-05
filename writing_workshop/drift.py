# SPDX-License-Identifier: Apache-2.0
"""Has this book drifted from the voice it started in?

The fingerprint was built to answer one question — *use an AI writing
tool long enough and the prose converges on the model's voice* — and it
could only ever ask it one sentence at a time, which is precisely the
level at which the drift is invisible. `Room.attach_drift` scores a
suggestion BEFORE it is offered. Nothing scored the manuscript against
its own past, so the cumulative effect the module's own docstring
describes ("not through any single bad suggestion — each one looks like an
improvement") had no measurement anywhere.

It needs nothing new. Named versions are already on disk, the fingerprint
already fits per window, and chapters already exist. Fit the baseline on a
version the author names — *"the draft before I started using The Room"* —
and score the current manuscript against it, chapter by chapter.

**What the answer is worth, and what it is not.** A chapter scoring 1.8
against a baseline of the author's own earlier work is a FACT about the
book; it is not a verdict about whether the book got worse. An author who
deliberately tightened their prose over eight months will light this up,
and should. What the tool contributes is that the change is now visible
and located, rather than being something they suspect at three in the
morning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import statistics as stats

from . import fingerprint as FP
from .document import Manuscript
from .types import Drift, Fingerprint


@dataclass
class SectionDrift:
    """One chapter, against the baseline."""

    section_id: str
    label: str
    words: int
    score: float
    drifts: list[Drift] = field(default_factory=list)

    @property
    def notable(self) -> list[Drift]:
        return [d for d in self.drifts if d.notable]

    def line(self) -> str:
        top = ", ".join(f"{d.direction} on {d.label}"
                        for d in self.notable[:2])
        return f"{self.label}: {self.score:.2f}" + (f" — {top}" if top
                                                    else "")


@dataclass
class DriftReport:
    """The book against its own past, and an honest account of the fit."""

    baseline: Fingerprint = field(default_factory=Fingerprint)
    baseline_name: str = ""
    sections: list[SectionDrift] = field(default_factory=list)
    words: int = 0

    @property
    def trustworthy(self) -> bool:
        return self.baseline.trustworthy

    @property
    def overall(self) -> float:
        scores = [s.score for s in self.sections if s.words]
        return round(stats.fmean(scores), 2) if scores else 0.0

    @property
    def worst(self) -> list[SectionDrift]:
        return sorted(self.sections, key=lambda s: -s.score)[:5]

    def halves(self) -> tuple[float, float]:
        """Mean drift over the first half of the book, then the second.

        The shape of a convergence is a rising line, so this is the one
        number that distinguishes "this author changed" from "this
        manuscript has been edited by a model since chapter nine".
        """
        rows = [s for s in self.sections if s.words]
        if len(rows) < 4:
            return (0.0, 0.0)
        mid = len(rows) // 2
        return (round(stats.fmean([s.score for s in rows[:mid]]), 2),
                round(stats.fmean([s.score for s in rows[mid:]]), 2))

    def summary(self) -> list[str]:
        """What the page says. Includes what it does NOT know."""
        if not self.baseline.metrics:
            return ["No baseline — name a version to measure against."]
        head = (f"Measured against “{self.baseline_name}” "
                f"({self.baseline.n_words:,} words)")
        lines = [head + f" · overall drift {self.overall:.2f}."]
        if not self.trustworthy:
            lines.append(
                f"The baseline is thin ({self.baseline.n_words:,} words, "
                f"{self.baseline.n_sentences} sentences), so treat every "
                f"number here as indicative.")
        early, late = self.halves()
        if early or late:
            lines.append(
                f"First half {early:.2f}, second half {late:.2f}"
                + (" — the later chapters sit further from the baseline, "
                   "which is the shape a convergence has."
                   if late - early >= 0.4 else
                   " — no rising trend across the book."))
        lines.append("Drift is distance from your own earlier writing. It "
                     "is not a quality score, and a deliberate change of "
                     "style will register exactly like an accidental one.")
        return lines


def baseline_from_version(versions, version_id: str,
                          *, exclude=None) -> tuple[Fingerprint, str]:
    """Fit the fingerprint on a named draft, as it was saved.

    Versions are folders of plain files, so this is the same measurement
    run over an older copy of the book — no special storage, nothing
    retained at save time, and it works on every version the author has
    ever named including ones saved before this feature existed.
    """
    info = versions.get(version_id)
    root = versions.root / version_id
    if info is None or not root.exists():
        return Fingerprint(), ""
    doc = Manuscript.load(root)
    fp = FP.from_manuscript(doc, fitted_on=f"version “{info.name}”",
                            exclude=exclude)
    return fp, info.name


def against(doc, baseline: Fingerprint, *, baseline_name: str = "",
            sections=None) -> DriftReport:
    """Score every chapter of the current manuscript against a baseline."""
    report = DriftReport(baseline=baseline, baseline_name=baseline_name)
    if not baseline.metrics:
        return report
    targets = sections if sections is not None else doc.chapters()
    for sec in targets:
        body = doc.prose(sec).strip()
        words = len(body.split())
        if words < 120:
            continue
        drifts = FP.score(baseline, body)
        report.sections.append(SectionDrift(
            section_id=sec.id, label=doc.label(sec), words=words,
            score=FP.drift_score(drifts), drifts=drifts))
        report.words += words
    return report


def since_version(doc, versions, version_id: str, *,
                  exclude=None) -> DriftReport:
    """The whole answer in one call: fit on a draft, score the book."""
    baseline, name = baseline_from_version(versions, version_id,
                                           exclude=exclude)
    return against(doc, baseline, baseline_name=name or version_id)
