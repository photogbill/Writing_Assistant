# SPDX-License-Identifier: Apache-2.0
"""Running the project's own rules as a craft check.

Registered for every document type, because a rule the author wrote
applies to whatever they wrote it for. It reads `ctx.rules`, which the
caller loads from `.workshop/rules.json` — this module knows nothing about
where they came from, so a host can supply rules from anywhere.
"""

from __future__ import annotations

import fnmatch

from .. import textio as T
from ..types import DEFECT, WARN, CraftReport, Finding, Span
from . import ANY_LANGUAGE, Ctx, check


def _scoped(ctx: Ctx, src, scope: str) -> list[tuple[int, int, str]]:
    """The (start, end, text) windows one scope offers in one file.

    Windows rather than one string, so a rule scoped to `steps` reports
    the step it matched in and not an offset into a concatenation.
    """
    prose = ctx.doc.prose_of_file(src.rel)
    if scope == "raw":
        return [(0, len(src.text), src.text)]
    if scope == "prose":
        return [(0, len(prose), prose)]
    if scope == "headings":
        return [(b.start, b.end, b.text) for b in src.blocks
                if b.kind == T.HEADING]
    if scope == "steps":
        out = []
        for block in src.blocks:
            number = (block.number if block.kind == T.ORDERED
                      else T.step_number(block.text)
                      if block.kind == T.PARA else 0)
            if number:
                out.append((block.start, block.end,
                            prose[block.start:block.end]))
        return out
    return []


@check("rules", "The project's own rules", languages=ANY_LANGUAGE)
def project_rules(ctx: Ctx) -> CraftReport:
    """Every rule in `.workshop/rules.json`, against the manuscript.

    The author's own house style, enforced by arithmetic. A rule that did
    not compile reports itself rather than going quiet — a rule someone
    believes is running and is not is worse than no rule at all.
    """
    rep = CraftReport()
    rules = list(ctx.rules or [])
    if not rules:
        rep.metrics["rules"] = 0
        return rep

    broken = 0
    for rule in rules:
        if rule.error:
            broken += 1
            rep.findings.append(Finding(
                "rules", DEFECT,
                f"Rule “{rule.id}” is not running: {rule.error}",
                "It is in the project's rules file and it did not "
                "compile, so nothing was checked against it. Fixing the "
                "file is the whole remedy.",
                data={"rule": rule.id, "source": rule.source,
                      "error": rule.error}))

    limit = int(ctx.opt("rule_hits", 40))
    counts: dict[str, int] = {}
    for rule in rules:
        if not rule.enabled or rule.error or rule.regex is None:
            continue
        hits = 0
        for src in ctx.doc.files:
            if rule.files and not fnmatch.fnmatch(src.rel, rule.files):
                continue
            for start, _end, text in _scoped(ctx, src, rule.scope):
                for m in rule.regex.finditer(text):
                    hits += 1
                    if hits > limit:
                        continue
                    span = Span(src.rel, start + m.start(),
                                start + m.end())
                    sec = ctx.doc.section_at(span)
                    rep.findings.append(Finding(
                        "rules", rule.severity,
                        f"{rule.label}: “{m.group(0)}”",
                        rule.hint or f"Project rule “{rule.id}”"
                        + (" (house)" if rule.source == "house" else "")
                        + ".",
                        span=span, section_id=sec.id if sec else "",
                        evidence=[ctx.doc.quote(span)],
                        data={"rule": rule.id, "match": m.group(0),
                              "source": rule.source, "scope": rule.scope}))
        if hits:
            counts[rule.id] = hits
        if hits > limit:
            rep.findings.append(Finding(
                "rules", WARN,
                f"Rule “{rule.id}” matched {hits} times; "
                f"{limit} are listed",
                "The rule ran over the whole manuscript — this is a "
                "limit on the list, not on the work. Raise `rule_hits` "
                "in the project's craft settings to see the rest.",
                data={"rule": rule.id, "total": hits, "shown": limit}))
    rep.metrics["rules"] = len(rules)
    rep.metrics["rules_broken"] = broken
    rep.metrics["rule_hits"] = counts
    return rep
