# SPDX-License-Identifier: Apache-2.0
"""Building a request out of a manuscript, a budget and a question.

`build()` is what a panel calls. Everything it assembles is priced,
ordered and accounted for, and the account is shown to the author — an
invisible policy is one they can neither trust nor steer.
"""

from __future__ import annotations

from .. import textio as T
from ..document import Manuscript
from ..types import Budget, Candidate, Claim, Section
from .assembler import (BAND_CLAIMS, BAND_IMMEDIATE, BAND_INVARIANT,
                        BAND_PRIOR, BAND_SPINE, BAND_SUMMARY, assemble)
from .budget import DEFAULT_RESERVE, from_model, offline
from .tokens import TokenCounter, estimate

__all__ = ["assemble", "build", "summarise", "from_model", "offline",
           "TokenCounter", "estimate", "meter", "DEFAULT_RESERVE",
           "BAND_INVARIANT", "BAND_IMMEDIATE", "BAND_CLAIMS", "BAND_SPINE",
           "BAND_PRIOR", "BAND_SUMMARY"]


def summarise(doc: Manuscript, sec: Section, sentences: int = 2) -> str:
    """An extractive summary — no model, and that is the point.

    Band 5 is the compression fallback for prior text, so it has to exist
    before any inference does; a summary band that needs a model to fill
    would make the whole assembler depend on the thing it is budgeting
    for. First and last sentence plus the size, which for a section of
    technical prose is a surprisingly good handle, and for a scene is at
    least honest about being a handle.
    """
    prose = doc.prose(sec)
    spans = T.sentences(prose)
    if not spans:
        return f"{doc.label(sec)} — {sec.words} words."
    picks = [prose[s:e] for s, e in spans[:sentences]]
    if len(spans) > sentences + 1:
        picks.append("…")
        picks.append(prose[spans[-1][0]:spans[-1][1]])
    body = " ".join(" ".join(p.split()) for p in picks)
    return f"{doc.label(sec)} ({sec.words} words): {body}"


def build(doc: Manuscript, section: Section | None, *, request: str = "",
          style_card: str = "", document_rules: str = "", brief: str = "",
          claims: list[Claim] | None = None, budget: Budget | None = None,
          counter: TokenCounter | None = None, llm=None,
          neighbours: int = 1, system: str = "", outline_levels: int = 3,
          include_prior: bool = True):
    """Assemble a request. Raises `BandZeroWontFit` rather than degrading.

    `section` may be None — an outline pass has no section yet, and the
    whole point of routing that stage to a 24B with a small window is that
    its input is a brief rather than a manuscript.
    """
    budget = budget or offline()
    # Pass the host's model and the counts become EXACT -- and the
    # manifest stops saying "estimated" about numbers it did not have to
    # estimate. A caller that supplies neither gets the heuristic, which
    # is correct but is a strictly worse promise, and it is easy to end up
    # there by simply not passing anything: every call site in the panel
    # did exactly that until this parameter existed.
    counter = counter or TokenCounter(llm)
    cands: list[Candidate] = []

    if style_card.strip():
        cands.append(Candidate("style-card", BAND_INVARIANT,
                               "## How this document is written\n"
                               + style_card.strip(), "style card",
                               stable=True))
    if document_rules.strip():
        cands.append(Candidate("rules", BAND_INVARIANT,
                               "## Rules for this document\n"
                               + document_rules.strip(), "document rules",
                               stable=True))
    if brief.strip():
        cands.append(Candidate("brief", BAND_INVARIANT,
                               "## Brief for this passage\n" + brief.strip(),
                               "section brief", stable=False))

    if section is not None:
        order = section.order
        near = [s for s in doc.sections
                if abs(s.order - order) <= neighbours and s.order != order]
        cands.append(Candidate(
            f"sec:{section.id}", BAND_IMMEDIATE,
            f"### {doc.label(section)}\n{doc.prose(section).strip()}",
            f"{doc.label(section)}", stable=False, value=10.0,
            summary=summarise(doc, section)))
        for sec in near:
            cands.append(Candidate(
                f"sec:{sec.id}", BAND_IMMEDIATE,
                f"### {doc.label(sec)}\n{doc.prose(sec).strip()}",
                f"{doc.label(sec)} (neighbour)", stable=False, value=4.0,
                summary=summarise(doc, sec)))

    for i, claim in enumerate(claims or []):
        cands.append(Candidate(
            f"claim:{claim.id or i}", BAND_CLAIMS,
            f"- {claim.subject}: {claim.predicate} = {claim.value}"
            + (f" [{claim.source_ref}]" if claim.source_ref else ""),
            "governing claims", stable=False, value=8.0))

    outline = doc.outline_text(outline_levels)
    if outline.strip():
        cands.append(Candidate("outline", BAND_SPINE, outline,
                               f"outline ({len(doc.sections)} sections)",
                               stable=True, value=6.0))

    if include_prior:
        here = section.order if section is not None else 10 ** 6
        taken = {c.key for c in cands}
        for sec in doc.sections:
            key = f"sec:{sec.id}"
            if key in taken or not sec.words:
                continue
            distance = abs(sec.order - here) or 1
            cands.append(Candidate(
                key, BAND_PRIOR,
                f"### {doc.label(sec)}\n{doc.prose(sec).strip()}",
                doc.label(sec), stable=True,
                value=1.0 / distance, summary=summarise(doc, sec)))

    return assemble(cands, budget, request=request, counter=counter,
                    system=system)


def meter(budget: Budget, assembly=None) -> list[str]:
    """The Budget Meter, as lines. Ceiling, price, then the account."""
    lines = list(budget.meter_lines())
    if assembly is not None:
        lines.append(assembly.manifest())
        lines.append(f"Prompt: {assembly.tokens:,} of "
                     f"{assembly.budget:,} tokens.")
    return lines
