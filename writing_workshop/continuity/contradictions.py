# SPDX-License-Identifier: Apache-2.0
"""Two claims that cannot both be true.

The honest split runs through the middle of this module. Numeric and
temporal conflicts are ARITHMETIC — 40 Nm and 45 Nm for one named quantity
is a defect and may be stated flatly. Attribute conflicts are a READING,
are reported as candidates with both passages quoted side by side, and the
author adjudicates. The tool never "fixes" anything either way.
"""

from __future__ import annotations

from collections import defaultdict
import re

from .. import textio as T
from ..units import conflict as _values_conflict
from ..units import dimension, split_value
from ..types import (ATTRIBUTE, NUMERIC, REJECTED, RELATIONSHIP, TEMPORAL,
                     Claim, Conflict)

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday")
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(minute|hour|day|week|month|"
                       r"year|second)s?", re.I)
_SCALE = {"second": 1, "minute": 60, "hour": 3600, "day": 86400,
          "week": 604800, "month": 2629800, "year": 31557600}


def _when_key(value: str) -> tuple[str, float | str] | None:
    """Normalise a temporal value to something comparable, or None."""
    low = T.normalise(value)
    for day in _WEEKDAYS:
        if day in low:
            return ("weekday", day)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low)
    if m:
        return ("date", m.group(0))
    m = _DURATION.search(low)
    if m:
        return ("duration", float(m.group(1)) * _SCALE[m.group(2).lower()])
    return None


def find(claims: list[Claim], *, include_proposed: bool = True
         ) -> list[Conflict]:
    """Every pair of claims about one subject-and-predicate that disagree.

    Grouped by `Claim.key`, which is subject plus predicate lowercased —
    so `torque` and `Torque` meet, and `torque` and `clearance` never do.
    A superseded claim is excluded: the author already told us the fact
    changed, and re-reporting it as a contradiction would punish them for
    using the feature.
    """
    live = [c for c in claims
            if c.state != REJECTED and c.superseded_by == 0
            and (include_proposed or c.state == "accepted")]
    groups: defaultdict[str, list[Claim]] = defaultdict(list)
    for claim in live:
        groups[claim.key].append(claim)

    out: list[Conflict] = []
    for _key, group in groups.items():
        if len(group) < 2:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                conflict = _compare(a, b)
                if conflict is not None:
                    out.append(conflict)
    out.sort(key=lambda c: (not c.deterministic, c.a.subject))
    return out


def _compare(a: Claim, b: Claim) -> Conflict | None:
    if a.kind == NUMERIC and b.kind == NUMERIC:
        return _numeric(a, b)
    if a.kind == TEMPORAL and b.kind == TEMPORAL:
        return _temporal(a, b)
    if a.kind == RELATIONSHIP and b.kind == RELATIONSHIP:
        if T.normalise(a.value) == T.normalise(b.value):
            return None
        return Conflict(a, b, RELATIONSHIP, False,
                        f"{a.subject} is “{a.value}” in {a.source_ref} and "
                        f"“{b.value}” in {b.source_ref}.")
    if a.kind == ATTRIBUTE or b.kind == ATTRIBUTE:
        if T.normalise(a.value) == T.normalise(b.value):
            return None
        return Conflict(a, b, ATTRIBUTE, False,
                        f"{a.subject} is “{a.value}” in {a.source_ref} and "
                        f"“{b.value}” in {b.source_ref}. Both passages are "
                        f"quoted; the tool does not decide which is right.")
    return None


def _numeric(a: Claim, b: Claim) -> Conflict | None:
    """Compared at the precision each value was WRITTEN to.

    `40 Nm` and `29.5 lb-ft` are the author's own conversion and agree;
    `40 Nm` and `45 Nm` do not. An exact-equality test with a small
    tolerance reported the first pair as a contradiction, which is the
    most expensive kind of false positive this package can produce.
    """
    a_raw, a_unit = split_value(a.value)
    b_raw, b_unit = split_value(b.value)
    if not a_raw or not b_raw:
        return None
    if dimension(a_unit) != dimension(b_unit):
        # Different dimensions under one name is a naming problem, not a
        # value contradiction, and calling it one would be wrong twice.
        return None
    if not _values_conflict(a_raw, a_unit, b_raw, b_unit):
        return None
    return Conflict(a, b, NUMERIC, True,
                    f"{a.subject} is {a.value} in {a.source_ref} and "
                    f"{b.value} in {b.source_ref}. Compared at the "
                    f"precision each was written to, so this is neither a "
                    f"units mismatch nor rounding — the numbers differ.")


def _temporal(a: Claim, b: Claim) -> Conflict | None:
    ka, kb = _when_key(a.value), _when_key(b.value)
    if ka is None or kb is None:
        if T.normalise(a.value) == T.normalise(b.value):
            return None
        return Conflict(a, b, TEMPORAL, False,
                        f"{a.subject}: “{a.value}” and “{b.value}”.")
    if ka[0] != kb[0]:
        return None
    if ka[1] == kb[1]:
        return None
    return Conflict(a, b, TEMPORAL, True,
                    f"{a.subject} is {a.value} in {a.source_ref} and "
                    f"{b.value} in {b.source_ref}.")
