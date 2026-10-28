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

**But a number that names the thing is not a count.** Key version 1
blanked every digit everywhere, so "Flat rhythm in Chapter 3" and "Flat
rhythm in Chapter 9" were one key — one dismissal hid every chapter's,
including chapters not written yet — and a dismissed "torque: 40 vs 45 Nm"
also hid "40 vs 400". Version 2 keeps digits in the SUBJECT (a term, a
figure id, a step), in the section a finding names, and in the values a
contradiction is between, and blanks them only in the prose of the title
and the evidence, which is where the counts live. Dismissals made under
version 1 still hold, but only for a finding whose title is exactly the
one the author dismissed.

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
                  "forms", "kind", "id", "step", "dimension", "rule")

#: Fields that are part of the identity AS WELL AS the subject, digits and
#: all: the section a finding is about (`craft.run` records it whenever
#: the title names one) and the values a contradiction is between.
IDENTITY_FIELDS = ("section", "values", "id")

#: Bumped when `key` changes. `last-run.json` from another version is not
#: compared against — every finding would otherwise be "new" at once.
KEY_VERSION = 2

_NUM = re.compile(r"\d[\d,.:]*")
_WS = re.compile(r"\s+")


def _flat(value) -> str:
    if isinstance(value, (list, tuple)):
        return ",".join(_flat(v) for v in value)
    if isinstance(value, dict):
        return ",".join(f"{k}={_flat(v)}" for k, v in sorted(value.items()))
    return str(value)


def _name(value) -> str:
    """A subject, normalised but with its digits: `Figure 3` is not
    `Figure 9`. A dict contributes its KEYS only — `forms` maps each
    spelling to a count, and the count is exactly what must not matter —
    and a list is sorted, so its order is not part of the identity."""
    if isinstance(value, dict):
        value = list(value)
    if isinstance(value, (list, tuple, set)):
        return ",".join(sorted(_name(v) for v in value))
    return _WS.sub(" ", str(value).lower()).strip()[:300]


def _norm(text: str) -> str:
    """Lowercase, digits blanked, whitespace collapsed, bounded."""
    return _WS.sub(" ", _NUM.sub("#", (text or "").lower())).strip()[:300]


def subject_of(finding: Finding) -> str:
    """What this finding is ABOUT, from the check's own data."""
    for name in SUBJECT_FIELDS:
        if name in finding.data:
            value = _name(finding.data[name])
            if value:
                return value
    return ""


def _identity(finding: Finding) -> str:
    return ";".join(f"{name}={_name(finding.data[name])}"
                    for name in IDENTITY_FIELDS if finding.data.get(name))


def key(finding: Finding) -> str:
    """A stable identity for one finding. Twelve hex characters.

    Short on purpose: this ends up in a JSON file the author may open,
    and a 64-character hash in a list of four hundred is unreadable. Two
    findings colliding costs one dismissal that covers both; a key nobody
    can scan costs a feature nobody uses.
    """
    parts = [finding.check, subject_of(finding), _identity(finding),
             _norm(finding.title),
             _norm(finding.evidence[0] if finding.evidence else "")]
    digest = hashlib.sha1("|".join(parts).encode("utf-8"))
    return digest.hexdigest()[:12]


def key_v1(finding: Finding) -> str:
    """The version-1 key, kept ONLY to honour dismissals made with it.

    Never used to hide a finding on its own: v1 keys collide (see the
    module docstring), so a v1 dismissal holds a finding only when the
    title it recorded is this finding's title, character for character.
    """
    subject = ""
    for name in SUBJECT_FIELDS[:-1]:
        if name in finding.data:
            value = _flat(finding.data[name])
            if value:
                subject = _norm(value)
                break
    parts = [finding.check, subject, _norm(finding.title),
             _norm(finding.evidence[0] if finding.evidence else "")]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


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
        self.entries: dict[str, dict] = self._load()
        #: What THIS object changed since it was read. `save` re-reads the
        #: file and applies only these, so an entry another window removed
        #: is not re-asserted from our stale copy of it.
        self._added: dict[str, dict] = {}
        self._removed: set[str] = set()

    def _load(self) -> dict[str, dict]:
        data = self.store.read(DISMISSED, {})
        entries = data.get("entries") if isinstance(data, dict) else None
        return {k: v for k, v in (entries or {}).items()
                if isinstance(v, dict)} if isinstance(entries, dict) else {}

    @property
    def problem(self) -> str:
        """Why the file could not be read as it is, or ""."""
        return self.store.problems.get(DISMISSED, "")

    # -- reading ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, item) -> bool:
        return self.holds(item)

    def _key_of(self, item) -> str | None:
        """The entry that holds `item` — a key, or a finding — or None."""
        if isinstance(item, str):
            return item if item in self.entries else None
        k = item.key or key(item)
        if k in self.entries:
            return k
        old = key_v1(item)
        row = self.entries.get(old)
        if row is not None and not row.get("v") and \
                row.get("title") == item.title:
            return old
        return None

    def holds(self, item) -> bool:
        return self._key_of(item) is not None

    def reason(self, item) -> str:
        k = self._key_of(item)
        return (self.entries.get(k) or {}).get("reason", "") if k else ""

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
                           "severity": finding.severity, "v": KEY_VERSION}
        self._added[k] = self.entries[k]
        self._removed.discard(k)
        if save:
            self.save()
        return k

    def remove(self, item, *, save: bool = True) -> bool:
        k = self._key_of(item)
        if k is None:
            return False
        del self.entries[k]
        self._added.pop(k, None)
        self._removed.add(k)
        if save:
            self.save()
        return True

    def save(self) -> None:
        """Re-read, merge, write.

        Two windows on one project -- the ATK page and the CLI, or two
        pages -- each hold their own copy. Writing ours over the file
        would drop whatever the other one recorded since we read it, and
        a dismissal that silently un-happens is the one failure this
        module cannot have.
        """
        merged = self._load()
        for k in self._removed:
            merged.pop(k, None)
        merged.update(self._added)
        self.store.write(DISMISSED, {"version": KEY_VERSION,
                                     "entries": merged})
        self.entries = merged
        # Applied, so no longer pending. Kept, every later save re-applied
        # them over the re-read file: a dismissal another window removed
        # came back, and one it added was deleted again.
        self._added.clear()
        self._removed.clear()


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
        if dismissals is not None and dismissals.holds(finding):
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
        "version": KEY_VERSION, "at": at,
        "keys": {f.key: f.title for f in findings}})


def previous(store: Store) -> dict:
    """The last run's keys, or {} when there is none to compare against.

    A run recorded under another key version counts as none: its keys
    cannot match, so comparing would call every finding "new" and every
    old one "gone" — a delta that is all noise, once, and teaches the
    author to ignore it."""
    data = store.read(LAST_RUN, {})
    if not isinstance(data, dict) or data.get("version") != KEY_VERSION:
        return {}
    return data
