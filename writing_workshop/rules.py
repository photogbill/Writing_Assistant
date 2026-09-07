# SPDX-License-Identifier: Apache-2.0
"""The project's own rules — the check the author writes.

Every other check in this package is a Python function inside the package,
which means the one thing a documentation team actually asks for is the
one thing they cannot have: *"never write 'simply'"*, *"say 'select', not
'click'"*, *"no first person in a procedure"*, *"every warning opens with
the hazard"*. Those are house style, they differ per organisation, and
nobody is going to fork an engine to add one.

So they live in `.workshop/rules.json` (and, for a rule the whole shelf
shares, in a `house.json` above the project — see `project.House`).

**This is still measurement.** A rule is a pattern and a message. It runs
with the GPU cold, it cannot invent a finding, and it says exactly what it
matched. That is the same promise every other craft check makes, which is
why this belongs here and not in The Room.

**A broken rule is reported, never swallowed.** A regex that will not
compile becomes a finding against the rule file itself, with the error in
it. The alternative is a rule the author believes is running and is not,
which is worse than no rule at all — it is the failure this package spends
`skipped` and `not_checked` and "estimated" on avoiding everywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from .types import DEFECT, NOTE, SEVERITIES, WARN

#: Where a rule may look. `prose` is the masked text — no code fences, no
#: tables, no front matter — which is what almost every rule wants and
#: what stops "never write TODO" firing inside a code sample.
SCOPES = ("prose", "raw", "headings", "steps")
DEFAULT_SCOPE = "prose"


@dataclass
class Rule:
    """One thing this project has decided about its own prose."""

    id: str
    message: str = ""
    pattern: str = ""
    phrase: str = ""
    severity: str = WARN
    scope: str = DEFAULT_SCOPE
    files: str = ""                 # fnmatch pattern against the rel path
    ignorecase: bool = True
    whole_word: bool = True
    hint: str = ""
    enabled: bool = True
    source: str = "project"         # "project" | "house"
    #: Filled by `compile_one`. A rule that did not compile still exists,
    #: still appears in the list, and reports itself.
    error: str = ""
    regex: object = field(default=None, repr=False, compare=False)

    @property
    def label(self) -> str:
        return self.message or self.id or self.phrase or self.pattern


def _severity(value: str) -> str:
    value = str(value or "").strip().lower()
    return value if value in SEVERITIES else WARN


def compile_one(raw: dict, *, source: str = "project",
                index: int = 0) -> Rule:
    """One rule out of one JSON object, compiling what it can.

    Never raises. A rule the author typed wrongly is a rule that has to
    tell them so, and the only place it can is the findings list.
    """
    if not isinstance(raw, dict):
        return Rule(id=f"rule-{index + 1}", source=source, enabled=False,
                    error="not an object")
    rule = Rule(
        id=str(raw.get("id") or f"rule-{index + 1}"),
        message=str(raw.get("message") or ""),
        pattern=str(raw.get("pattern") or ""),
        phrase=str(raw.get("phrase") or ""),
        severity=_severity(raw.get("severity")),
        scope=str(raw.get("scope") or DEFAULT_SCOPE).lower(),
        files=str(raw.get("files") or ""),
        ignorecase=bool(raw.get("ignorecase", True)),
        whole_word=bool(raw.get("whole_word", True)),
        hint=str(raw.get("hint") or ""),
        enabled=bool(raw.get("enabled", True)),
        source=source)
    if rule.scope not in SCOPES:
        rule.error = (f"scope {rule.scope!r} is not one of "
                      f"{', '.join(SCOPES)}")
        return rule
    if not rule.pattern and not rule.phrase:
        rule.error = "needs either a `phrase` or a `pattern`"
        return rule
    body = rule.pattern
    if not body:
        body = re.escape(rule.phrase)
        if rule.whole_word:
            body = rf"(?<!\w){body}(?!\w)"
    try:
        rule.regex = re.compile(body, re.I if rule.ignorecase else 0)
    except re.error as exc:
        rule.error = f"pattern will not compile: {exc}"
    return rule


def parse(data, *, source: str = "project") -> list[Rule]:
    """A rules document into rules. Accepts a list or `{"rules": [...]}`."""
    if isinstance(data, dict):
        data = data.get("rules")
    if not isinstance(data, list):
        return []
    return [compile_one(raw, source=source, index=i)
            for i, raw in enumerate(data)]


def merge(house: list[Rule], project: list[Rule]) -> list[Rule]:
    """House rules first, then the project's — which may override by id.

    Override rather than accumulate, because the point of a house rule is
    that one project is allowed to be the exception and say so in its own
    file, rather than by editing everybody else's.
    """
    out: dict[str, Rule] = {}
    for rule in [*house, *project]:
        out[rule.id] = rule
    return list(out.values())


def example() -> list[dict]:
    """A starter file, so the format is discoverable without a manual."""
    return [
        {"id": "no-simply", "phrase": "simply", "severity": "warn",
         "message": "“simply” tells the reader the thing they are stuck "
                    "on is easy",
         "hint": "Delete it. It never adds information and it is the "
                 "word readers quote back when a step goes wrong."},
        {"id": "click-vs-select", "phrase": "click", "severity": "note",
         "message": "house style is “select”, not “click”",
         "hint": "“Select” covers a mouse, a keyboard and a touchscreen."},
        {"id": "no-first-person-in-steps", "scope": "steps",
         "pattern": r"\b(?:I|we|our)\b", "ignorecase": False,
         "severity": "warn",
         "message": "a procedure step written in the first person"},
    ]


#: What a rule is ALLOWED to carry into the file, and their defaults. A key
#: at its default is left out, so a rules file an author opens in an editor
#: is the decisions they made rather than eleven fields of boilerplate per
#: rule. `source`, `error` and `regex` are deliberately absent: the first is
#: where the rule was READ from and writing it into the project file would
#: make a house rule a copy, and the other two are what compiling produced.
WRITTEN = {"id": "", "message": "", "pattern": "", "phrase": "",
           "severity": WARN, "scope": DEFAULT_SCOPE, "files": "",
           "ignorecase": True, "whole_word": True, "hint": "",
           "enabled": True}


def to_json(rules: list) -> dict:
    """Rules back into the shape `parse` reads. Round-trips.

    A test asserts `parse(to_json(rules))` gives the same rules back,
    because a settings editor that cannot read its own output is a settings
    editor that eats the author's rules the second time they open it.
    """
    out = []
    for rule in rules:
        row = {"id": rule.id}
        for name, default in WRITTEN.items():
            if name == "id":
                continue
            value = getattr(rule, name, default)
            if value != default:
                row[name] = value
        out.append(row)
    return {"rules": out}


__all__ = ["Rule", "SCOPES", "DEFAULT_SCOPE", "compile_one", "parse",
           "merge", "example", "to_json", "WRITTEN", "NOTE", "WARN",
           "DEFECT"]
