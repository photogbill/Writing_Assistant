# SPDX-License-Identifier: Apache-2.0
"""Craft: everything measurable, with no model loaded.

This is the phase that makes the tool trustworthy, and it is the phase the
original plan did not have at all. All of it is arithmetic over the text:
fast, repeatable, offline, and **incapable of inventing a finding**. A
workshop whose first useful answer comes from a model is a workshop the
author has to fact-check; one whose first answers are measurements has
earned the benefit of the doubt by the time a model speaks.

Every check is a plain function of a `Ctx` returning a `CraftReport`, is
registered with the document types it applies to, and may be run alone.
Nothing here retains state between runs, so a report is always about the
manuscript as it is on disk right now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..document import Manuscript
from ..types import DOC_TYPES, FICTION, TECHNICAL, CraftReport


@dataclass
class Ctx:
    """Everything a check may look at. Deliberately small."""

    doc: Manuscript
    document_type: str = TECHNICAL
    cast: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    #: Section titles that hold definitions. The default lives HERE and
    #: nowhere else: it used to be defaulted in `Project` only, so any
    #: caller that ran a check without a project got an empty list, every
    #: glossary entry was invisible, and the tool announced that three
    #: defined terms were never defined. A default that exists in one of
    #: two paths is a bug with a delay on it.
    glossary_titles: list[str] = field(
        default_factory=lambda: ["glossary", "definitions", "terms",
                                 "terminology", "abbreviations",
                                 "acronyms", "nomenclature"])
    options: dict = field(default_factory=dict)

    def opt(self, name: str, default):
        value = self.options.get(name)
        return default if value is None else value


@dataclass
class Registered:
    name: str
    label: str
    fn: Callable[[Ctx], CraftReport]
    applies: tuple[str, ...]
    needs_model: bool = False


REGISTRY: dict[str, Registered] = {}


def check(name: str, label: str, *applies: str):
    """Register a craft check. `applies` defaults to both document types."""
    kinds = tuple(applies) or DOC_TYPES

    def wrap(fn):
        REGISTRY[name] = Registered(name, label, fn, kinds)
        return fn
    return wrap


def checks_for(document_type: str) -> list[Registered]:
    return [r for r in REGISTRY.values() if document_type in r.applies]


def run(doc: Manuscript, document_type: str = TECHNICAL, *,
        only: list[str] | None = None, cast: list[str] | None = None,
        terms: list[str] | None = None,
        glossary_titles: list[str] | None = None,
        options: dict | None = None, cancel=None) -> CraftReport:
    """Run every check that applies, or the named ones.

    Failures are CONTAINED. One check raising must not cost the author the
    other nineteen — an empty craft page is indistinguishable from a clean
    manuscript, and that is the worst outcome this module has.
    """
    # Importing these IS the registration -- the decorator runs on
    # import. Done here rather than at module level so `craft` can be
    # imported for its registry alone without dragging in every check.
    from . import fiction, shared, technical      # noqa: F401

    ctx = Ctx(doc=doc, document_type=document_type, cast=list(cast or []),
              terms=list(terms or []), options=dict(options or {}))
    if glossary_titles:
        ctx.glossary_titles = list(glossary_titles)
    report = CraftReport(doc_type=document_type)
    for reg in checks_for(document_type):
        if only and reg.name not in only:
            continue
        if cancel is not None and cancel.is_set():
            report.skipped[reg.name] = "cancelled"
            continue
        try:
            part = reg.fn(ctx)
        except Exception as exc:                       # noqa: BLE001
            report.skipped[reg.name] = f"{type(exc).__name__}: {exc}"
            continue
        report.merge(part)
        report.ran.append(reg.name)
    report.ran = sorted(set(report.ran))
    return report


__all__ = ["Ctx", "REGISTRY", "check", "checks_for", "run", "FICTION",
           "TECHNICAL"]
