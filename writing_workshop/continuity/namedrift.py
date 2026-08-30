# SPDX-License-Identifier: Apache-2.0
"""Name drift: Aleksandr / Alexander / Alex / Sasha.

The fiction version of terminology drift, and the same machine. It PROPOSES
and never merges — a tool that quietly decided two names were one person
would be rewriting the cast list, and there is no undo for a belief.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import textio as T

#: Diminutives that no edit-distance test will ever find. Short, and
#: extended by the project rather than by guessing.
NICKNAMES = {
    "aleksandr": {"alexander", "alex", "sasha", "sacha", "aleksei"},
    "alexander": {"aleksandr", "alex", "sasha", "xander"},
    "elizabeth": {"eliza", "liz", "beth", "betty", "libby", "lisbeth"},
    "katherine": {"kate", "katie", "kathy", "kitty", "cat", "catherine"},
    "margaret": {"maggie", "meg", "peggy", "greta", "rita"},
    "william": {"will", "bill", "billy", "liam"},
    "richard": {"rick", "dick", "richie"},
    "robert": {"rob", "bob", "bobby", "bert"},
    "james": {"jim", "jimmy", "jamie"},
    "john": {"jack", "johnny", "jon"},
    "michael": {"mike", "mick", "mikey", "micha"},
    "nicholas": {"nick", "nico", "niko", "colin"},
    "theodore": {"theo", "ted", "teddy"},
    "victoria": {"vicky", "vic", "tori"},
    "dmitri": {"dima", "mitya", "dmitry"},
    "yekaterina": {"katya", "katerina", "katia"},
}


@dataclass
class Variant:
    canonical: str
    forms: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    reason: str = ""

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _edit_distance(a: str, b: str, cap: int = 2) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
        if min(previous) > cap:
            return cap + 1
    return previous[-1]


def _related(a: str, b: str) -> str:
    la, lb = T.normalise(a), T.normalise(b)
    if la == lb:
        return ""
    if lb in NICKNAMES.get(la, ()) or la in NICKNAMES.get(lb, ()):
        return "a known diminutive"
    short, long = sorted((la, lb), key=len)
    if len(short) >= 4 and long.startswith(short):
        return "one is a shortening of the other"
    if min(len(la), len(lb)) >= 5 and _edit_distance(la, lb) <= 2:
        return "one or two characters apart"
    if la.replace("k", "c") == lb.replace("k", "c"):
        return "a spelling variant"
    return ""


def find(doc, names: list[str]) -> list[Variant]:
    """Groups of names that may be one person, with counts and a reason.

    The reason matters: "one or two characters apart" is a claim the
    author can check in a second, and it is also the honest description
    of what the tool actually did.
    """
    counts: dict[str, int] = {}
    for name in names:
        hits = len(doc.find(name))
        if hits:
            counts[name] = hits
    live = sorted(counts, key=lambda n: -counts[n])
    used: set[str] = set()
    out: list[Variant] = []
    for i, a in enumerate(live):
        if a in used:
            continue
        group = Variant(canonical=a, forms=[a], counts={a: counts[a]})
        for b in live[i + 1:]:
            if b in used:
                continue
            why = _related(a, b)
            if not why:
                continue
            group.forms.append(b)
            group.counts[b] = counts[b]
            group.reason = why
            used.add(b)
        if len(group.forms) > 1:
            used.add(a)
            out.append(group)
    return out
