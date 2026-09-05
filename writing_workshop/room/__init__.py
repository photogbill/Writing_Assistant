# SPDX-License-Identifier: Apache-2.0
"""The Room — assistance, last and least.

Deliberately last in the build order, because it is the commodity part and
the one most likely to damage the thing it is helping with. Two guarantees
hold it in place:

**THE MODEL NEVER WRITES INTO THE MANUSCRIPT.** Output goes to a diff
surface where the author accepts, rejects or splices, and the accepted text
enters the file by the author's decision rather than by the tool's paste.
The moment a tool can edit the book without a human keystroke, every other
promise in this package becomes a promise rather than a property.

**EVERY SUGGESTION ARRIVES WITH ITS DRIFT SCORE.** Attached and quiet — a
number beside the suggestion, not a dialog. That is what stops the slow
convergence on the model's voice that nothing else in this category admits
to.

There is deliberately **no autocomplete and no ghost text**. It is the
highest-slop-risk feature in the category: it trains the author to accept
the model's next word thousands of times a session, below the level where
any of them is a decision. Everything here is opt-in per suggestion; ghost
text is opt-out per keystroke.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import fingerprint as FP
from ..errors import NoModelError
from ..ports import NEVER, Host
from ..types import Claim, Fingerprint, Section, Suggestion
from .personas import (
    ADVERSARY,
    ALL,
    CONTINUITY_READER,
    EXPANDER,
    LINE_EDITOR,
    Persona,
    for_document,
    get,
)

__all__ = ["Room", "Persona", "for_document", "get", "ALL", "LINE_EDITOR",
           "CONTINUITY_READER", "EXPANDER", "ADVERSARY", "Critique"]


@dataclass
class Critique:
    """What a non-rewriting persona returned: notes, never an edit."""

    persona: str
    notes: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def clean(self) -> bool:
        return not self.notes


class Room:
    """One persona, one call, no shared state. That is the isolation."""

    def __init__(self, host: Host | None = None,
                 fingerprint: Fingerprint | None = None) -> None:
        self.host = host or Host()
        self.fingerprint = fingerprint

    # -- the two shapes ---------------------------------------------------

    def rewrite(self, persona: Persona, text: str, *, context: str = "",
                claims: list[Claim] | None = None, notes: str = "",
                section: Section | None = None, cancel=None) -> Suggestion:
        """Ask for revised prose. Returns a Suggestion, never a file write."""
        if not persona.returns_text:
            raise ValueError(
                f"{persona.label} returns notes, not text — send it to "
                f"critique(). A critique pasted into a manuscript is the "
                f"failure this distinction exists to prevent.")
        reply = self._ask(persona, text, context, claims, notes, cancel)
        suggestion = Suggestion(persona=persona.key, text=_strip_fence(reply),
                                target=section.body if section else None,
                                rationale=persona.blurb)
        self.attach_drift(suggestion)
        return suggestion

    def critique(self, persona: Persona, text: str, *, context: str = "",
                 claims: list[Claim] | None = None, notes: str = "",
                 cancel=None) -> Critique:
        """Ask for a reading. Returns notes that can never be applied."""
        reply = self._ask(persona, text, context, claims, notes, cancel)
        body = (reply or "").strip()
        if not body or body.strip().upper().startswith("NOTHING"):
            return Critique(persona.key, [], body)
        lines = [ln.strip(" -*•\t") for ln in body.splitlines()]
        return Critique(persona.key, [ln for ln in lines if ln], body)

    # -- drift ------------------------------------------------------------

    def attach_drift(self, suggestion: Suggestion) -> Suggestion:
        """Score the suggestion against the author's own baseline.

        Done HERE rather than in the panel, so a host cannot ship the
        suggestion without it by forgetting a call.
        """
        if self.fingerprint is None or not suggestion.text.strip():
            return suggestion
        suggestion.drifts = FP.score(self.fingerprint, suggestion.text)
        suggestion.drift_score = FP.drift_score(suggestion.drifts)
        suggestion.note = FP.describe(self.fingerprint, suggestion.drifts)
        return suggestion

    # -- what the author took ---------------------------------------------

    def accepted(self, suggestion: Suggestion, influences, *, at: str = "",
                 note: str = "") -> bool:
        """Record that the author took this text. Call it on ACCEPT.

        The host calls this at the moment the suggestion goes into the
        manuscript — by the author's keystroke, as always; nothing here
        writes a word of it. What is recorded is a note in `.workshop/`
        saying that this passage came from a persona.

        It exists because the fingerprint's central claim was
        unenforceable without it. `fit()` has always said that fitting a
        baseline on a draft containing the model's rewrites "bakes the
        drift into the baseline, and the tool then reports that
        everything matches beautifully — the exact failure it exists to
        prevent", and nothing tracked which prose that was. A defence
        that quietly disarms itself the more it is used is worse than
        none, because it reports success.
        """
        if influences is None or not suggestion.text.strip():
            return False
        return influences.record(
            suggestion.text, persona=suggestion.persona, at=at,
            note=note or suggestion.rationale)

    # -- the one place that talks to a model ------------------------------

    def _ask(self, persona: Persona, text: str, context: str,
             claims: list[Claim] | None, notes: str, cancel) -> str:
        parts = []
        if context.strip():
            parts.append(context.strip())
        if persona.wants_claims and claims:
            parts.append("## Established facts\n" + "\n".join(
                f"- {c.subject}: {c.predicate} = {c.value}"
                + (f" [{c.source_ref}]" if c.source_ref else "")
                for c in claims))
        if notes.strip():
            parts.append("## Notes and beats\n" + notes.strip())
        parts.append("## Passage\n" + text.strip())
        parts.append(persona.instruction)
        try:
            return self.host.llm.complete(
                persona.system, "\n\n".join(parts),
                temperature=persona.temperature, max_tokens=1400,
                cancel=cancel or NEVER)
        except NoModelError:
            raise
        except Exception as exc:                      # noqa: BLE001
            raise NoModelError(
                f"{persona.label} could not run: {exc}") from exc


def _strip_fence(text: str) -> str:
    """Models fence prose about a third of the time whatever you ask."""
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            body = "\n".join(lines).strip()
    return body
