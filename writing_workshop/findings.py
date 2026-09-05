# SPDX-License-Identifier: Apache-2.0
"""Giving a finding an identity, so the author can be done with one.

A craft pass over a real 81,000-word document produces around nine
hundred findings. Run it again on Tuesday and it produces the same nine
hundred, including the four hundred the author looked at on Monday and
decided were deliberate. A tool that cannot be told *"yes, I know"* is one
whose second run is worth less than its first, and by the fifth run the
one finding that mattered is underneath four hundred the author has
already judged.

So a finding gets a **content key**, and the author gets a dismissal list.

**The key deliberately does not contain an offset.** A paragraph that
moves is the same finding; a sentence that is rewritten is a new one, and
should be, because the thing the author dismissed is no longer there.
Numbers in titles are normalised to `#` for the same reason: three
sentences opening with "The" and four sentences opening with "The" are one
decision, not two.

**Nothing here dismisses anything by itself.** There is no confidence
threshold, no auto-hide and no "clear all" — a dismissal is an act by the
author, recorded with a date and, if they gave one, a reason. That is the
same rule that governs accepting a claim, for the same reason: the moment
the tool starts deciding what the author has already seen, the list stops
being trustworthy in the one direction that matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re

from .state import DISMISSED, LAST_RUN, Store
from .types import Finding

#: Fields of `Finding.data` that name WHAT a finding is about, in the
#: order they are looked for. Counts and distances are deliberately absent
#: — `"echo" × 40 words apart` and `"echo" × 60 words apart` are one
#: finding the author has already read.
SUBJECT_FIELDS = ("word", "phrase", "name", "term", "acronym", "subject",
                  "forms", "kind", "id", "step", "dimension")

_NUM = re.compile(r"\d[\d,.:]*")
_WS = re.compile(r"\s+")


def _flat(value) -> str:
    if isinstance(value, (list, tuple)):
        return ",".join(_flat(v) for v in value)
    if isinstance(value, dict):
        return ",".join(f"{k}={_flat(v)}" for k, v in sorted(value.items()))
    return str(value)


def _norm(text: str) -> str:
    """Lowercase, digits blanked, whitespace collapsed, bounded."""
    return _WS.sub(" ", _NUM.sub("#", (text or "").lower())).strip()[:300]


def subject_of(finding: Finding) -> str:
    """What this finding is ABOUT, from the check's own data."""
    for name in SUBJECT_FIELDS:
        if name in finding.data:
            value = _flat(finding.data[name])
            if value:
                return _norm(value)
    return ""


def key(finding: Finding) -> str:
    """A stable identity for one finding. Twelve hex characters.

    Short on purpose: this ends up in a JSON file the author may open,
    and a 64-character hash in a list of four hundred is unreadable. Two
    findings colliding costs one dismissal that covers both; a key nobody
    can scan costs a feature nobody uses.
    """
    parts = [finding.check, subject_of(finding), _norm(finding.title),
             _norm(finding.evidence[0] if finding.evidence else "")]
    digest = hashlib.sha1("|".join(parts).encode("utf-8"))
    return digest.hexdigest()[:12]


def stamp(findings: list[Finding]) -> list[Finding]:
    """Fill in `Finding.key` in place. Returns the same list."""
    for finding in findings:
        finding.key = key(finding)
    return findings


# ---------------------------------------------------------------------------
# the dismissal list
# ---------------------------------------------------------------------------


class Dismissals:
    """What the author has already looked at and decided about.

    Held in `.workshop/dismissed.json` beside the manuscript, so it
    travels with the project and is readable by a human who wants to know
    what they told the tool to stop saying.
    """

    def __init__(self, store: Store) -> None:
        self.store = store
        data = store.read(DISMISSED, {})
        entries = data.get("entries") if isinstance(data, dict) else None
        self.entries: dict[str, dict] = dict(entries or {})

    # -- reading ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, item) -> bool:
        return self.holds(item)

    def holds(self, item) -> bool:
        return (item if isinstance(item, str) else key(item)) in self.entries

    def reason(self, item) -> str:
        row = self.entries.get(item if isinstance(item, str) else key(item))
        return (row or {}).get("reason", "")

    def all(self) -> list[dict]:
        rows = []
        for k, row in self.entries.items():
            rows.append({"key": k, **row})
        return sorted(rows, key=lambda r: r.get("at", ""), reverse=True)

    # -- writing ----------------------------------------------------------

    def add(self, finding: Finding, *, reason: str = "", at: str = "",
            save: bool = True) -> str:
        """Record one decision. The author's, never the tool's."""
        k = key(finding)
        self.entries[k] = {"check": finding.check, "title": finding.title,
                           "reason": reason.strip(), "at": at,
                           "severity": finding.severity}
        if save:
            self.save()
        return k

    def remove(self, item, *, save: bool = True) -> bool:
        k = item if isinstance(item, str) else key(item)
        if k not in self.entries:
            return False
        del self.entries[k]
        if save:
            self.save()
        return True

    def save(self) -> None:
        self.store.write(DISMISSED, {"version": 1, "entries": self.entries})


# ---------------------------------------------------------------------------
# the delta — what changed since last time
# ---------------------------------------------------------------------------


@dataclass
class Triage:
    """One craft report, sorted into what the author actually needs.

    `fresh` is the field this whole module exists for. An author who has
    spent an afternoon in chapter nine wants the twelve findings that
    appeared, not the nine hundred that were already there and that they
    have walked past four times.
    """

    shown: list[Finding] = field(default_factory=list)
    hidden: list[Finding] = field(default_factory=list)
    fresh: list[Finding] = field(default_factory=list)
    gone: list[dict] = field(default_factory=list)
    had_previous: bool = False

    @property
    def counts(self) -> dict[str, int]:
        return {"shown": len(self.shown), "dismissed": len(self.hidden),
                "new": len(self.fresh), "resolved": len(self.gone)}

    def summary(self) -> str:
        """One line, and it says what it does not know."""
        head = f"{len(self.shown)} to look at"
        if self.hidden:
            head += f" · {len(self.hidden)} dismissed"
        if not self.had_previous:
            return head + " · no previous run to compare against"
        return (head + f" · {len(self.fresh)} new since the last run"
                + (f" · {len(self.gone)} gone" if self.gone else ""))


def triage(findings: list[Finding], *, dismissals: Dismissals | None = None,
           previous: dict | None = None) -> Triage:
    """Split a report into shown, dismissed, new and resolved.

    Purely a sort. Nothing is deleted, and `hidden` is returned rather
    than dropped so a host can always offer "show what I dismissed" —
    a dismissal the author cannot review is a decision they cannot undo.
    """
    stamp(findings)
    result = Triage()
    seen = dict((previous or {}).get("keys") or {})
    result.had_previous = bool(seen)
    live: set[str] = set()
    for finding in findings:
        live.add(finding.key)
        if dismissals is not None and dismissals.holds(finding.key):
            result.hidden.append(finding)
            continue
        result.shown.append(finding)
        if seen and finding.key not in seen:
            result.fresh.append(finding)
    for k, title in seen.items():
        if k not in live:
            result.gone.append({"key": k, "title": title})
    return result


def remember(store: Store, findings: list[Finding], *, at: str = "") -> None:
    """Record this run's keys, so the next one can show the delta.

    Keys and titles only. The findings themselves are not cached: craft is
    stateless on purpose and a stale report is worse than no report, so
    what is kept is the minimum needed to answer "is this one new".
    """
    stamp(findings)
    store.write(LAST_RUN, {
        "version": 1, "at": at,
        "keys": {f.key: f.title for f in findings}})


def previous(store: Store) -> dict:
    data = store.read(LAST_RUN, {})
    return data if isinstance(data, dict) else {}
