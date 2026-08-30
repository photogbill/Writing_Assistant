# SPDX-License-Identifier: Apache-2.0
"""The vocabulary. This module and `ports.py` are the public contract.

Everything here is a plain dataclass with no behaviour beyond arithmetic on
its own fields, because these cross the boundary into a host that must not
have to import our machinery to read a result.

Two conventions worth stating once:

* **Offsets are character offsets into a named file**, never into a
  concatenation of the manuscript. A finding that cannot be pointed at in
  the file the author is editing is a finding they cannot act on.
* **Nothing here carries a "fixed" or "applied" flag.** The workshop never
  writes into the manuscript; the author does. A type that could record an
  automatic edit is a type that invites one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# severities
#
# Three, deliberately, and they are about ACTION rather than about how loud
# the tool feels. Adding a fourth is how a findings list becomes a colour
# chart nobody triages.
# ---------------------------------------------------------------------------

#: Something measured, offered without a claim that it is wrong. Readability
#: scores, pacing, the dialogue ratio. Never counted as a problem.
NOTE = "note"

#: Worth the author's eye. Craft flags, echoes, a long step. May be
#: deliberate — the tool does not know the author's intent and does not
#: pretend to.
WARN = "warn"

#: Provably inconsistent WITH THE DOCUMENT ITSELF: a dead cross-reference,
#: two values for one quantity, a duplicated step number. No taste involved,
#: which is why it may be stated flatly.
DEFECT = "defect"

SEVERITIES = (NOTE, WARN, DEFECT)

# ---------------------------------------------------------------------------
# document types
# ---------------------------------------------------------------------------

TECHNICAL = "technical"
FICTION = "fiction"
DOC_TYPES = (TECHNICAL, FICTION)


@dataclass(frozen=True)
class Span:
    """A character range inside one file."""

    path: str
    start: int
    end: int

    def __len__(self) -> int:
        return max(0, self.end - self.start)

    def overlaps(self, other: "Span") -> bool:
        return (self.path == other.path
                and self.start < other.end and other.start < self.end)


@dataclass
class Section:
    """One heading and the prose under it, down to the next heading.

    `number` is the document's own numbering when the heading carries one
    ("## 4.2 Torque" -> "4.2") and a derived one otherwise. Cross-reference
    integrity depends on telling those apart: a reference to "§4.2" must
    resolve against a number the AUTHOR wrote, not one this parser invented,
    or the check reports a defect the reader can never see.
    """

    id: str
    title: str
    level: int
    span: Span
    body: Span                     # the prose, heading line excluded
    number: str = ""               # "4.2" — author's own, when present
    derived_number: str = ""       # "4.2" — always populated
    parent_id: str = ""
    order: int = 0                 # position in reading order
    words: int = 0

    @property
    def path(self) -> str:
        return self.span.path


@dataclass
class Paragraph:
    """A paragraph, with the section it belongs to and where it starts."""

    section_id: str
    index: int                     # 0-based within the section
    text: str
    span: Span

    def source_ref(self, section_label: str = "") -> str:
        label = section_label or self.section_id
        return f"{label} para {self.index + 1}"


@dataclass
class Finding:
    """Something the workshop noticed, and where.

    `evidence` holds the quoted text a human needs to judge it without
    opening the file — the rule ATK settled on for CyberWolf's case files:
    a finding with no evidence is an assertion, and an assertion the reader
    cannot check is worse than silence.
    """

    check: str
    severity: str
    title: str
    detail: str = ""
    span: Span | None = None
    section_id: str = ""
    evidence: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_problem(self) -> bool:
        return self.severity in (WARN, DEFECT)


@dataclass
class CraftReport:
    """What a craft pass produced: numbers to show, and things to look at.

    The split is deliberate. Metrics are measurements the author reads;
    findings are places to go. Collapsing them into one list is how a
    readability score ends up rendered as a problem.
    """

    doc_type: str = TECHNICAL
    metrics: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    ran: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    def problems(self) -> list[Finding]:
        return [f for f in self.findings if f.is_problem]

    def by_check(self, check: str) -> list[Finding]:
        return [f for f in self.findings if f.check == check]

    def merge(self, other: "CraftReport") -> None:
        self.metrics.update(other.metrics)
        self.findings.extend(other.findings)
        self.ran.extend(other.ran)
        self.skipped.update(other.skipped)


# ---------------------------------------------------------------------------
# claims — the Codex
# ---------------------------------------------------------------------------

ATTRIBUTE = "attribute"        # "the sword is bronze"
RELATIONSHIP = "relationship"  # "Mira is Aleksandr's sister"
TEMPORAL = "temporal"          # "the wedding is on Wednesday"
NUMERIC = "numeric"            # "40 Nm", "three days' ride"
CLAIM_KINDS = (ATTRIBUTE, RELATIONSHIP, TEMPORAL, NUMERIC)

PROPOSED = "proposed"
ACCEPTED = "accepted"
REJECTED = "rejected"
SUPERSEDED = "superseded"
CLAIM_STATES = (PROPOSED, ACCEPTED, REJECTED, SUPERSEDED)


@dataclass
class Claim:
    """One assertion the document makes about its own world.

    STATE IS THE POINT. A claim arrives `proposed` — including every claim a
    model extracted — and only the author moves it to `accepted`. A Codex
    that fills itself with a model's readings becomes a bible the author
    never wrote and cannot trust, and every continuity answer computed from
    it inherits that.
    """

    subject: str
    kind: str
    predicate: str                 # "material", "sister of", "torque"
    value: str
    id: int = 0
    unit: str = ""
    number: float | None = None    # parsed numeric value, when there is one
    source_ref: str = ""           # "§4.2 para 3", "ch 17 para 12"
    section_id: str = ""
    span: Span | None = None
    quote: str = ""                # the sentence it came from
    state: str = PROPOSED
    origin: str = "author"         # "author" | "extracted" | "measured"
    superseded_by: int = 0
    note: str = ""

    @property
    def key(self) -> str:
        """What two claims must share to be candidates for a conflict."""
        return f"{self.subject.strip().lower()}|{self.predicate.strip().lower()}"


@dataclass
class Conflict:
    """Two claims that cannot both be true, or might not be.

    `deterministic` is the honest half of this type. A numeric conflict is
    arithmetic and may be stated. An attribute conflict is a reading, is
    reported as a candidate, and quotes both passages so the author
    adjudicates rather than the tool.
    """

    a: Claim
    b: Claim
    kind: str
    deterministic: bool
    detail: str = ""

    @property
    def severity(self) -> str:
        return DEFECT if self.deterministic else WARN


@dataclass
class Thread:
    """A tracked entity or topic, and its shape across the document."""

    name: str
    kind: str = "entity"
    mentions: list[tuple[int, Span]] = field(default_factory=list)
    first_order: int = 0
    last_order: int = 0
    sections: set[str] = field(default_factory=set)
    emphasis: float = 0.0          # how loudly it was introduced
    resolved_at: int | None = None

    @property
    def count(self) -> int:
        return len(self.mentions)


# ---------------------------------------------------------------------------
# context assembly
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """One thing that might go into the prompt, priced.

    `reason` is not decoration: it is what lets the manifest be written, and
    the manifest is what turns "the model missed something obvious" into
    "that section was not in view", which is a fixable complaint.
    """

    key: str
    band: int
    text: str
    reason: str
    tokens: int = 0
    stable: bool = True
    value: float = 1.0             # value-per-token multiplier within a band
    summary: str = ""              # band-5 fallback if this cannot be carried


@dataclass
class Assembly:
    """A packed prompt and an honest account of what is in it."""

    text: str
    tokens: int
    budget: int
    carried: list[Candidate] = field(default_factory=list)
    summarised: list[Candidate] = field(default_factory=list)
    dropped: list[Candidate] = field(default_factory=list)
    exact_counts: bool = False

    def manifest(self) -> str:
        """The line the Budget Meter shows under the model name."""
        def names(items):
            return ", ".join(c.reason for c in items) or "nothing"
        about = "" if self.exact_counts else " (token counts estimated)"
        return (f"Carrying: {names(self.carried)}. "
                f"Summarised: {names(self.summarised)}. "
                f"Out of view: {names(self.dropped)}.{about}")


@dataclass
class Budget:
    """What the loaded model can actually hold, and what it costs.

    Both halves matter and the second one is new. Before layer offload,
    context was a wall; now it is a purchase, and an operator who raises the
    context without being told the price experiences it as ATK mysteriously
    getting slower.
    """

    model: str = ""
    usable_tokens: int = 0
    declared_tokens: int = 0
    layers_on_card: int = 0
    total_layers: int = 0
    host_mb: float = 0.0
    reserve_output: int = 1024
    alternative: str = ""          # "Load Qwythos-9B for 75,448 …"
    measured: bool = False         # False = a default, not a reading

    @property
    def reserve(self) -> int:
        """What is actually held back for the answer.

        Clamped to half the window. A fixed 1024-token reserve against a
        model measured at 900 usable tokens produced an INPUT BUDGET OF
        ZERO, which the assembler then read as "unset" and replaced with
        its 8k default -- so the smallest model in the folder was given
        the largest budget, and the meter reported it confidently.
        """
        if not self.usable_tokens:
            return self.reserve_output
        return max(64, min(self.reserve_output, self.usable_tokens // 2))

    @property
    def input_tokens(self) -> int:
        return max(0, self.usable_tokens - self.reserve)

    def meter_lines(self) -> list[str]:
        """Two lines: the ceiling, then the price. Never one without the
        other — the price line is the whole reason this exists."""
        if not self.model:
            return ["No model loaded — measurement and craft checks only."]
        head = f"{self.model} · {self.usable_tokens:,} tokens usable"
        if self.total_layers:
            head += (f" · {self.layers_on_card} of {self.total_layers} "
                     f"layers on the card")
        lines = [head + "."]
        if self.host_mb > 1:
            lines.append(
                f"{self.host_mb / 1024:.1f} GB in system RAM. Drafting will "
                f"be slower than with every layer on the card.")
        if self.alternative:
            lines.append(self.alternative)
        if not self.measured:
            lines.append("Estimated — no GPU reading was available.")
        return lines


# ---------------------------------------------------------------------------
# style fingerprint
# ---------------------------------------------------------------------------


@dataclass
class Fingerprint:
    """A measurable description of how this author writes, on this project.

    `n_words` is carried because a fingerprint fitted on two paragraphs is
    not a fingerprint, and the only thing worse than no baseline is a
    confident one built from nothing.
    """

    metrics: dict[str, float] = field(default_factory=dict)
    spread: dict[str, float] = field(default_factory=dict)
    n_words: int = 0
    n_sentences: int = 0
    fitted_on: str = ""
    version: int = 1

    @property
    def trustworthy(self) -> bool:
        return self.n_words >= 2000 and self.n_sentences >= 100


@dataclass
class Drift:
    """One metric of a suggestion, against the author's baseline."""

    metric: str
    label: str
    baseline: float
    value: float
    z: float
    direction: str = ""            # "shorter", "denser", …

    @property
    def notable(self) -> bool:
        return abs(self.z) >= 1.5


@dataclass
class Suggestion:
    """Something a persona proposed. It is text, and it is not applied."""

    persona: str
    text: str
    target: Span | None = None
    rationale: str = ""
    drifts: list[Drift] = field(default_factory=list)
    drift_score: float = 0.0
    note: str = ""


# ---------------------------------------------------------------------------
# diff and versions
# ---------------------------------------------------------------------------


@dataclass
class Hunk:
    """One sentence-level change. `op` is equal / insert / delete / replace.

    SENTENCES, not lines. A paragraph is one line, so a line diff of prose
    renders a one-word change as a whole-paragraph rewrite — which destroys
    the only thing a version feature exists to provide.
    """

    op: str
    old: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    old_span: tuple[int, int] = (0, 0)
    new_span: tuple[int, int] = (0, 0)
    id: int = 0

    @property
    def changed(self) -> bool:
        return self.op != "equal"


@dataclass
class VersionInfo:
    """A named draft. Named in the author's words, and visible.

    Hidden version control is a data-loss trap: when it goes wrong the
    author has no model of what happened and no vocabulary to ask about it.
    """

    id: str
    name: str
    created: str
    note: str = ""
    files: int = 0
    words: int = 0
