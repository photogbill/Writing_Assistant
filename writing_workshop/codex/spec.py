# SPDX-License-Identifier: Apache-2.0
"""The spec register: every component, quantity, value and place, in one
table.

The 2026-10-28 review's I4. Numeric claims are keyed by what they are OF
since this morning ("the torque for the lid bolts"), which turns the
numeric check from noise into something a technical writer would pay for —
and the next step is the view they actually work from: one row per
component and quantity, every value the manuscript gives for it, where,
and whether those values agree.

Built from claims, so it is exactly as trustworthy as the Codex: a value
the author REJECTED is not listed as a value, a SUPERSEDED one is listed as
history, and the state of each is on the row. Nothing here reads the
manuscript or asks a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
import io

from ..types import ACCEPTED, NUMERIC, PROPOSED, REJECTED, SUPERSEDED
from ..units import conflict, split_value


@dataclass
class SpecRow:
    """One component and one quantity, with every value given for it."""

    component: str
    quantity: str
    values: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    where: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    claim_ids: list[int] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    #: Two current values that disagree, at the precision each was written.
    conflict: bool = False

    @property
    def value(self) -> str:
        """The value, when there is one — or every value, " / " joined."""
        seen = list(dict.fromkeys(self.values))
        return " / ".join(seen)


def spec_sheet(claims) -> list[SpecRow]:
    """Rows for every numeric claim the author has not rejected.

    Grouped by (component, quantity), case-insensitively; ordered by
    component then quantity, which is how a parts list reads. A component
    with no name — a bare "torque" nothing names — is listed as "(not
    named)", because hiding it would hide exactly the claims that need a
    name before they can be checked.
    """
    rows: dict[tuple[str, str], SpecRow] = {}
    for claim in claims or []:
        if getattr(claim, "kind", "") != NUMERIC:
            continue
        state = getattr(claim, "state", PROPOSED)
        if state == REJECTED:
            continue
        component = (claim.subject or "").strip()
        quantity = (claim.predicate or "").strip()
        if quantity == "value" or not quantity:
            # A numeric claim with no quantity word is keyed by its
            # subject alone (`units.Quantity`): the subject IS the
            # quantity and nothing names the component.
            component, quantity = "", component or "value"
        key = (component.lower(), quantity.lower())
        row = rows.get(key)
        if row is None:
            row = rows[key] = SpecRow(component or "(not named)", quantity)
        where = claim.source_ref or claim.section_id or ""
        if state == SUPERSEDED:
            row.history.append(f"{claim.value} (superseded)"
                               + (f" — {where}" if where else ""))
            continue
        number, unit = split_value(claim.value)
        row.values.append(claim.value)
        row.units.append(claim.unit or unit)
        row.where.append(where)
        row.states.append(state)
        row.claim_ids.append(int(claim.id or 0))
    for row in rows.values():
        current = [split_value(v) for v in row.values]
        row.conflict = any(
            conflict(a[0], a[1], b[0], b[1])
            for i, a in enumerate(current) for b in current[i + 1:]
            if a[0] and b[0])
    return sorted(rows.values(),
                  key=lambda r: (r.component == "(not named)",
                                 r.component.lower(), r.quantity.lower()))


def to_csv(rows: list[SpecRow]) -> str:
    """The register as CSV — one line per VALUE, so a spreadsheet can sort
    and filter it, with the row's conflict flag on every line."""
    buf = io.StringIO()
    out = csv.writer(buf, lineterminator="\n")
    out.writerow(["component", "quantity", "value", "unit", "where",
                  "state", "conflict", "claim"])
    for row in rows:
        for i, value in enumerate(row.values):
            out.writerow([row.component, row.quantity, value,
                          row.units[i] if i < len(row.units) else "",
                          row.where[i] if i < len(row.where) else "",
                          row.states[i] if i < len(row.states) else "",
                          "yes" if row.conflict else "",
                          row.claim_ids[i] if i < len(row.claim_ids) else ""])
        for old in row.history:
            out.writerow([row.component, row.quantity, old, "", "",
                          SUPERSEDED, "", ""])
    return buf.getvalue()


def counts(rows: list[SpecRow]) -> dict[str, int]:
    return {"components": len({r.component for r in rows}),
            "quantities": len(rows),
            "conflicts": sum(1 for r in rows if r.conflict),
            "accepted": sum(s == ACCEPTED for r in rows for s in r.states)}
