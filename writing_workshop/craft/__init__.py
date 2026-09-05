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

from collections.abc import Callable
from dataclasses import dataclass, field
import time

from .. import doctypes as DT
from ..document import Manuscript
from ..types import DOC_TYPES, FICTION, NOTE, TECHNICAL, CraftReport, Finding


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
    #: Project-local rules from `.workshop/rules.json`. A check reads
    #: them; nothing else knows they exist. See `writing_workshop.rules`.
    rules: list = field(default_factory=list)
    #: What the manuscript is written in. A check may read it; whether a
    #: check RUNS at all is decided by `Registered.languages` in `run`.
    language: str = "en"

    def opt(self, name: str, default):
        value = self.options.get(name)
        return default if value is None else value


#: A check that is valid in ANY language — it counts structure rather
#: than words it recognises. `("*",)` rather than a list of codes,
#: because the claim is "this needs no word list", not "somebody tested
#: it in Finnish".
ANY_LANGUAGE = ("*",)


@dataclass
class Registered:
    name: str
    label: str
    fn: Callable[[Ctx], CraftReport]
    applies: tuple[str, ...]
    needs_model: bool = False
    #: Which languages this check's ARITHMETIC is valid for. Defaults to
    #: English, because that is the truth about most of them: the
    #: common-word list, the syllable heuristic, the filter words, the
    #: subordinators, the participle list and Flesch-Kincaid are all
    #: English and none of them says so from its output.
    languages: tuple[str, ...] = ("en",)

    def speaks(self, language: str) -> bool:
        return ("*" in self.languages
                or (language or "en").lower() in self.languages)


#: Name -> check. NEVER REBOUND, only filled: a host may hold a reference
#: to this dict (ATK's panel does, to build its per-check filter) and
#: rebinding it would leave that host looking at an empty copy for the
#: life of the process.
REGISTRY: dict[str, Registered] = {}


def _load() -> None:
    """Import the check modules, which IS the registration.

    Called by everything that reads the registry, not only by `run`.
    Before this existed the imports lived inside `run` alone, so
    `from writing_workshop.craft import REGISTRY` handed a caller an
    EMPTY dict and `checks_for(...)` an empty list — and ATK's per-check
    dropdown, built from that dict when a project opens, offered nothing
    but "every check" until a craft pass had been run. Built, wired,
    unreachable, and nothing failed. The empty state is now
    unobservable.

    Kept as a deferred import rather than a module-level one so `craft`
    can still be imported for its registry alone without dragging in
    every check at import time.
    """
    if REGISTRY:
        return
    from . import fiction, lyrics, rules, shared, technical  # noqa: F401


def registry() -> dict[str, Registered]:
    """The registry, guaranteed populated."""
    _load()
    return REGISTRY


def check(name: str, label: str, *applies: str,
          languages: tuple[str, ...] = ("en",)):
    """Register a craft check. `applies` defaults to both document types.

    `languages` is the honest half. Pass `ANY_LANGUAGE` only when the
    check counts structure — sentences, steps, chapter lengths, capital
    runs — rather than consulting a list of English words.
    """
    kinds = tuple(applies) or DOC_TYPES

    def wrap(fn):
        REGISTRY[name] = Registered(name, label, fn, kinds,
                                    languages=tuple(languages))
        return fn
    return wrap


def checks_for(document_type: str) -> list[Registered]:
    _load()
    return [r for r in REGISTRY.values() if document_type in r.applies]


#: How many findings from ONE check are listed before the rest are
#: summarised into a single note. The check still runs in full and the
#: true count is always stated -- this is a limit on the LIST, never on
#: the work, and `max_findings=0` turns it off.
#:
#: It exists because one check can bury the others: 409 echoes and 333
#: acronyms on one real 81,000-word document, with the twenty-eight
#: broken cross-references -- the only DEFECTS in the run -- somewhere
#: underneath them.
MAX_FINDINGS_PER_CHECK = 100


def run(doc: Manuscript, document_type: str = TECHNICAL, *,
        only: list[str] | None = None, cast: list[str] | None = None,
        terms: list[str] | None = None,
        glossary_titles: list[str] | None = None,
        options: dict | None = None, cancel=None, events=None,
        rules: list | None = None,
        language: str = "en", profile=None) -> CraftReport:
    """Run every check that applies, or the named ones.

    Failures are CONTAINED. One check raising must not cost the author the
    other nineteen — an empty craft page is indistinguishable from a clean
    manuscript, and that is the worst outcome this module has.

    **Nothing is ever dropped for taking too long.** There is no time
    budget here and there must not be one: an operator who has offloaded
    layers to the CPU has CHOSEN to wait, and a check the tool abandoned
    on a timer is a silent degradation wearing a progress bar. What a
    slow pass gets instead is `events` — progress per check, so a long
    wait is a wait rather than a hang — and `cancel`, which is the
    operator's decision and not ours.
    """
    _load()
    language = (language or "en").strip().lower() or "en"
    # A profile lets a project declare a type this package never met --
    # a screenplay, a set of release notes -- by naming a base to inherit
    # checks from and what to add or drop. Unknown types fall back to the
    # technical checks rather than to an empty report, because a project
    # whose doctypes.json was deleted must still measure.
    profile = profile or DT.get(document_type)
    merged = dict(profile.options)
    merged.update(options or {})
    ctx = Ctx(doc=doc, document_type=document_type, cast=list(cast or []),
              terms=list(terms or []), options=merged,
              rules=list(rules or []), language=language)
    if glossary_titles:
        ctx.glossary_titles = list(glossary_titles)
    report = CraftReport(doc_type=document_type)
    wanted = checks_for(profile.base) if profile.base else []
    names = {r.name for r in wanted}
    for extra in profile.add:
        if extra in REGISTRY and extra not in names:
            wanted.append(REGISTRY[extra])
            names.add(extra)
    todo = [r for r in wanted
            if r.name not in profile.drop and (not only or r.name in only)]
    total = len(todo)
    cap = int(ctx.opt("max_findings", MAX_FINDINGS_PER_CHECK))
    for i, reg in enumerate(todo, 1):
        if cancel is not None and cancel.is_set():
            report.skipped[reg.name] = "cancelled"
            continue
        if not reg.speaks(language):
            report.skipped[reg.name] = (
                f"its arithmetic is {'/'.join(reg.languages)}-only and "
                f"this project is written in {language}")
            continue
        if events is not None:
            events.emit("progress", f"craft: {reg.label}", i=i, n=total,
                        check=reg.name)
        started = time.monotonic()
        try:
            part = reg.fn(ctx)
        except Exception as exc:                       # noqa: BLE001
            report.skipped[reg.name] = f"{type(exc).__name__}: {exc}"
            if events is not None:
                events.emit("warning", f"{reg.label} did not run: {exc}",
                            check=reg.name)
            continue
        _cap(part, reg, cap)
        report.merge(part)
        report.ran.append(reg.name)
        report.timing[reg.name] = round(time.monotonic() - started, 3)
    report.ran = sorted(set(report.ran))
    if events is not None:
        events.emit("done", f"craft: {len(report.ran)} checks, "
                    f"{len(report.problems())} to look at")
    return report


def _cap(part: CraftReport, reg: Registered, cap: int) -> None:
    """Trim ONE check's finding list, and say so in the list itself."""
    if cap <= 0 or len(part.findings) <= cap:
        return
    total = len(part.findings)
    keep = part.findings[:cap]
    keep.append(Finding(
        reg.name, NOTE,
        f"{total - cap} more {reg.label.lower()} findings not listed",
        f"{total} in all; the first {cap} are shown. The check ran in "
        f"full — this is a limit on the list, not on the work. Raise "
        f"`max_findings` in the project's craft settings, or set it to 0, "
        f"to see every one.",
        data={"total": total, "shown": cap, "capped": True}))
    part.findings = keep
    part.metrics[f"{reg.name}_total_findings"] = total


__all__ = ["Ctx", "REGISTRY", "ANY_LANGUAGE", "check", "checks_for",
           "registry", "run", "FICTION", "TECHNICAL",
           "MAX_FINDINGS_PER_CHECK"]
