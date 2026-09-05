# SPDX-License-Identifier: Apache-2.0
"""`workshop` — the whole no-model half of the tool, from a terminal.

Exists for two reasons beyond convenience. It is the proof that the core
runs with no host and no GPU, and it is how a defect in a craft check gets
reproduced without launching a desktop application.

**Nothing here is on a timer.** A pass over a long manuscript on a machine
with its layers offloaded to the CPU is supposed to take as long as it
takes; `--progress` says where it has got to and Ctrl-C is the only thing
that stops it early. A tool that abandoned a check to feel responsive
would be making the operator's decision for them and calling the result a
report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import codex as CX
from . import context as CT
from . import continuity as CN
from . import diff as DF
from . import doctypes as DT
from . import drift as DR
from . import export as EX
from . import findings as FD
from . import fingerprint as FP
from .craft import registry as craft_registry
from .craft import run as run_craft
from .document import Manuscript
from .influence import Influences
from .project import Project
from .types import DEFECT, FICTION, LYRICS, TECHNICAL, WARN
from .version import __version__
from .versions import Versions


class _Progress:
    """Events to stderr, so `--json` on stdout stays machine-readable."""

    def __init__(self, on: bool) -> None:
        self.on = on

    def emit(self, kind: str, message: str, **data) -> None:
        if not self.on:
            return
        n, i = data.get("n"), data.get("i")
        where = f"[{i}/{n}] " if i and n else ""
        print(f"  {where}{message}", file=sys.stderr, flush=True)


def _load(path: str) -> tuple[Project, Manuscript]:
    project = Project.open(path, create=False)
    doc = project.manuscript()
    for note in doc.notes():
        print(f"note: {note}", file=sys.stderr)
    return project, doc


def _print_findings(findings, verbose: bool) -> int:
    problems = 0
    for finding in sorted(findings, key=lambda f: (
            {DEFECT: 0, WARN: 1}.get(f.severity, 2), f.check)):
        mark = {"defect": "!!", "warn": " !", "note": "  "}[finding.severity]
        key = f" ({finding.key})" if finding.key else ""
        print(f"{mark} [{finding.check}] {finding.title}{key}")
        if verbose and finding.detail:
            for line in finding.detail.splitlines():
                print(f"      {line}")
        if verbose:
            for quote in finding.evidence[:2]:
                print(f"      | {quote[:110]}")
        problems += 1 if finding.is_problem else 0
    return problems


def cmd_outline(args) -> int:
    _project, doc = _load(args.path)
    print(doc.outline_text(args.levels))
    print(f"\n{len(doc.sections)} sections · {doc.words:,} words · "
          f"{len(doc.files)} files")
    return 0


def cmd_craft(args) -> int:
    project, doc = _load(args.path)
    doc_type = args.type or project.document_type
    # The profile has to follow the type the OPERATOR asked for, not the
    # one saved in project.json. `--type lyrics` on a project saved as
    # technical ran the sixteen technical checks and reported them under
    # the lyrics heading, which is a report about the wrong document.
    profile = DT.get(doc_type, project.doctypes())
    report = run_craft(
        doc, doc_type, only=args.only, cast=project.cast,
        terms=project.effective_terms(),
        glossary_titles=project.effective_glossary_titles(),
        options=project.craft_options(), rules=project.rules(),
        language=project.language, profile=profile,
        events=_Progress(args.progress))

    store = project.store
    dismissals = FD.Dismissals(store)
    sorted_out = FD.triage(report.findings, dismissals=dismissals,
                           previous=FD.previous(store))
    shown = (report.findings if args.all else
             sorted_out.fresh if args.new else sorted_out.shown)

    if args.json:
        print(json.dumps({
            "metrics": report.metrics, "timing": report.timing,
            "skipped": report.skipped, "counts": sorted_out.counts,
            "findings": [{**f.__dict__} for f in shown]},
            default=str, indent=2))
    else:
        problems = _print_findings(shown, args.verbose)
        print(f"\n{len(report.ran)} checks ran, {problems} things to look "
              f"at.")
        print(sorted_out.summary())
        for name, why in report.skipped.items():
            print(f"   not run — {name}: {why}")
        if args.timing:
            for name, secs in sorted(report.timing.items(),
                                     key=lambda kv: -kv[1]):
                print(f"   {secs:6.2f}s  {name}")
    if args.remember:
        FD.remember(store, report.findings, at=_now())
    return 1 if any(f.severity == DEFECT for f in shown) else 0


def _now() -> str:
    import datetime as _dt
    return _dt.datetime.now().replace(microsecond=0).isoformat(" ")


def cmd_dismiss(args) -> int:
    """Record that the author has looked at a finding and is done with it."""
    project, doc = _load(args.path)
    store = project.store
    dismissals = FD.Dismissals(store)
    if args.list:
        for row in dismissals.all():
            print(f"{row['key']}  {row.get('at', ''):19}  "
                  f"[{row.get('check', '')}] {row.get('title', '')}")
            if row.get("reason"):
                print(f"          reason: {row['reason']}")
        print(f"\n{len(dismissals)} dismissed.")
        return 0
    if args.restore:
        ok = dismissals.remove(args.restore)
        print("restored" if ok else "no such key")
        return 0 if ok else 1
    if not args.key:
        print("give a finding key (workshop craft shows one per line), "
              "--list, or --restore KEY")
        return 2
    doc_type = args.type or project.document_type
    report = run_craft(doc, doc_type,
                       cast=project.cast, terms=project.effective_terms(),
                       glossary_titles=project.effective_glossary_titles(),
                       options=project.craft_options(),
                       rules=project.rules(), language=project.language,
                       profile=DT.get(doc_type, project.doctypes()))
    FD.stamp(report.findings)
    for finding in report.findings:
        if finding.key == args.key:
            dismissals.add(finding, reason=args.reason, at=_now())
            print(f"dismissed [{finding.check}] {finding.title}")
            return 0
    print(f"no current finding with key {args.key}")
    return 1


def cmd_checks(args) -> int:
    """What this build can measure. Also proves the registry is loaded."""
    project = None
    try:
        project = Project.open(args.path, create=False)
    except Exception:                                 # noqa: BLE001
        pass
    doc_type = args.type or (project.document_type if project else "")
    for name, reg in sorted(craft_registry().items()):
        mark = "*" if not doc_type or doc_type in reg.applies else " "
        langs = "any" if "*" in reg.languages else "/".join(reg.languages)
        print(f"{mark} {name:16} {langs:6} "
              f"{','.join(reg.applies):26} {reg.label}")
    if project is not None:
        print()
        for key, profile in sorted(project.doctypes().items()):
            mark = "*" if key == project.document_type else " "
            print(f"{mark} {key:16} base={profile.base:10} "
                  f"{profile.blurb}")
    return 0


def cmd_rules(args) -> int:
    project, _doc = _load(args.path)
    if args.init:
        path = project.write_example_rules()
        print(f"rules at {path}")
    rules = project.rules()
    for rule in rules:
        state = "!" if rule.error else (" " if rule.enabled else "-")
        print(f"{state} {rule.id:24} {rule.severity:6} {rule.scope:8} "
              f"{rule.source:8} {rule.label}")
        if rule.error:
            print(f"      {rule.error}")
    print(f"\n{len(rules)} rules.")
    return 0


def cmd_continuity(args) -> int:
    project, doc = _load(args.path)
    claims = CX.deterministic(doc, terms=project.effective_terms(),
                              subjects=project.cast or None)
    sweep = CN.sweep(doc, claims, cast=project.cast,
                     terms=project.effective_terms(),
                     events=_Progress(args.progress))
    _print_findings(sweep.findings, args.verbose)
    chron = sweep.chronology or {}
    print(f"\n{sweep.metrics.get('claims', 0)} claims · "
          f"{sweep.metrics.get('conflicts', 0)} conflicts "
          f"({sweep.metrics.get('deterministic_conflicts', 0)} certain) · "
          f"{sweep.metrics.get('threads', 0)} threads, "
          f"{sweep.metrics.get('dropped', 0)} dropped")
    if chron:
        print(f"{chron.get('total', 0)} time markers: "
              + ", ".join(f"{k} {v}" for k, v in
                          sorted(chron.get("by_kind", {}).items())))
        days = chron.get("weekday_sequence") or []
        if days:
            print("weekdays in reading order: " + " → ".join(days[:16])
                  + ("…" if len(days) > 16 else ""))
    return 1 if sweep.metrics.get("deterministic_conflicts") else 0


def cmd_codex(args) -> int:
    project, doc = _load(args.path)
    store = CX.Codex(project.codex_db)
    if args.extract:
        who = CX.subjects_for(doc, project.cast or None)
        if who and not project.cast:
            print(f"cast read from the document: {', '.join(who[:12])}"
                  + ("…" if len(who) > 12 else ""))
        added = store.add_many(
            CX.deterministic(doc, terms=project.effective_terms(),
                             subjects=project.cast or None))
        print(f"{len(added)} claims proposed.")
    for claim in store.all(state=args.state or None):
        print(f"#{claim.id:<4} [{claim.state:10}] {claim.kind:12} "
              f"{claim.subject} · {claim.predicate} = {claim.value}  "
              f"({claim.source_ref})")
    print(f"\n{store.counts()}")
    store.close()
    return 0


def cmd_fingerprint(args) -> int:
    project, doc = _load(args.path)
    influences = Influences(project.store)
    exclude = influences.spans_in(doc) if args.exclude_room else []
    if args.exclude_room:
        print(f"excluding {len(exclude)} of {len(influences)} accepted "
              f"passages still present in the manuscript")
    fp = FP.from_manuscript(doc, exclude=exclude)
    FP.save(fp, project.fingerprint_file)
    print(f"Fitted on {fp.n_words:,} words in "
          f"{fp.metrics.get('_windows', 0)} windows "
          f"({'usable' if fp.trustworthy else 'thin — treat as indicative'})")
    for key, label, _u, _d in FP.METRICS:
        if key in fp.metrics:
            print(f"  {label:38} {fp.metrics[key]:8.3f} "
                  f"± {fp.spread.get(key, 0):.3f}")
    if args.speakers:
        print("\nPer speaker:")
        for name, one in sorted(FP.by_speaker(doc, project.cast).items()):
            print(f"  {name:20} {one.n_words:6,} words  "
                  f"sentence {one.metrics.get('sentence_words', 0):5.1f}  "
                  f"rarity {one.metrics.get('rarity', 0):.3f}")
    if args.score:
        text = Path(args.score).read_text(encoding="utf-8")
        drifts = FP.score(fp, text)
        print(f"\ndrift {FP.drift_score(drifts)}")
        print(FP.describe(fp, drifts))
    return 0


def cmd_drift(args) -> int:
    """Has the book drifted from the voice it started in?"""
    project, doc = _load(args.path)
    versions = Versions(project)
    if not args.since:
        for info in versions.list():
            print(f"{info.id:<28} {info.created}  {info.words:>7,} words  "
                  f"{info.name}")
        print("\nPick one: workshop drift PATH --since VERSION_ID")
        return 0
    influences = Influences(project.store)
    report = DR.since_version(doc, versions, args.since,
                              exclude=influences.spans_in(doc)
                              if args.exclude_room else None)
    for line in report.summary():
        print(line)
    if not report.sections:
        return 0
    print()
    for row in sorted(report.sections, key=lambda s: -s.score):
        print(f"  {row.score:5.2f}  {row.label}")
        if args.verbose:
            for one in row.notable[:3]:
                print(f"         {one.direction} on {one.label} "
                      f"({one.value:.2f} against {one.baseline:.2f})")
    return 0


def cmd_budget(args) -> int:
    _project, doc = _load(args.path)
    budget = CT.offline()
    budget.model = args.model or "(no model)"
    budget.usable_tokens = args.tokens
    budget.measured = bool(args.model)
    section = doc.sections[args.section] if doc.sections else None
    assembly = CT.build(doc, section, request="Draft the next paragraph.",
                        budget=budget)
    for line in CT.meter(budget, assembly):
        print(line)
    return 0


def cmd_versions(args) -> int:
    project, _doc = _load(args.path)
    versions = Versions(project)
    if args.save:
        info = versions.save(args.save, args.note or "")
        print(f"saved “{info.name}” ({info.files} files, "
              f"{info.words:,} words)")
        return 0
    if args.diff:
        for rel, hunks in versions.diff(args.diff).items():
            print(f"--- {rel}")
            print(DF.render(hunks))
        return 0
    for info in versions.list():
        print(f"{info.id:<28} {info.created}  {info.words:>7,} words  "
              f"{info.name}")
    return 0


def cmd_export(args) -> int:
    project, doc = _load(args.path)
    if args.format == "shunn":
        spec = EX.shunn_spec(doc, title=args.title or project.name,
                             author=args.author)
        text = EX.shunn_markdown(spec)
    elif args.format == "numbered":
        text = EX.numbered_markdown(doc, title=args.title or project.name)
    else:
        text = EX.plain_markdown(doc)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="workshop",
        description="The ATK Writing Workshop — measurement first.")
    parser.add_argument("--version", action="version",
                        version=f"writing-workshop {__version__}")
    subs = parser.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_text):
        sub = subs.add_parser(name, help=help_text)
        sub.add_argument("path", help="the project folder")
        sub.add_argument("-v", "--verbose", action="store_true")
        sub.add_argument("--progress", action="store_true",
                         help="say which check is running, on stderr")
        sub.set_defaults(fn=fn)
        return sub

    sub = add("outline", cmd_outline, "the derived structure")
    sub.add_argument("--levels", type=int, default=3)

    sub = add("craft", cmd_craft, "the measurements — no model needed")
    sub.add_argument("--type", choices=[TECHNICAL, FICTION, LYRICS])
    sub.add_argument("--only", nargs="*")
    sub.add_argument("--json", action="store_true")
    sub.add_argument("--all", action="store_true",
                     help="include findings already dismissed")
    sub.add_argument("--new", action="store_true",
                     help="only what appeared since the last --remember")
    sub.add_argument("--remember", action="store_true",
                     help="record this run, so the next can show the delta")
    sub.add_argument("--timing", action="store_true",
                     help="seconds per check, slowest first")

    sub = add("dismiss", cmd_dismiss, "be done with a finding")
    sub.add_argument("key", nargs="?", help="the key shown by `craft`")
    sub.add_argument("--reason", default="")
    sub.add_argument("--list", action="store_true")
    sub.add_argument("--restore", metavar="KEY")
    sub.add_argument("--type", choices=[TECHNICAL, FICTION, LYRICS])

    sub = add("checks", cmd_checks, "what this build can measure")
    sub.add_argument("--type")

    sub = add("rules", cmd_rules, "the project's own rules")
    sub.add_argument("--init", action="store_true",
                     help="write a starter rules file if there is none")

    add("continuity", cmd_continuity, "contradictions, threads, names")

    sub = add("codex", cmd_codex, "the claims store")
    sub.add_argument("--extract", action="store_true",
                     help="propose every claim readable with no model")
    sub.add_argument("--state")

    sub = add("fingerprint", cmd_fingerprint, "fit the author's own style")
    sub.add_argument("--score", help="a file to score against the baseline")
    sub.add_argument("--speakers", action="store_true",
                     help="a baseline per speaking character")
    sub.add_argument("--exclude-room", action="store_true",
                     help="leave out passages accepted from The Room")

    sub = add("drift", cmd_drift, "the book against its own earlier draft")
    sub.add_argument("--since", metavar="VERSION_ID")
    sub.add_argument("--exclude-room", action="store_true")

    sub = add("budget", cmd_budget, "what fits, and what it costs")
    sub.add_argument("--model", default="")
    sub.add_argument("--tokens", type=int, default=8192)
    sub.add_argument("--section", type=int, default=0)

    sub = add("versions", cmd_versions, "named drafts and diffs")
    sub.add_argument("--save", metavar="NAME")
    sub.add_argument("--note", default="")
    sub.add_argument("--diff", metavar="VERSION_ID")

    sub = add("export", cmd_export, "shunn / numbered / plain")
    sub.add_argument("--format", choices=["shunn", "numbered", "plain"],
                     default="plain")
    sub.add_argument("--title", default="")
    sub.add_argument("--author", default="")
    sub.add_argument("--out", default="")

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":                            # pragma: no cover
    raise SystemExit(main())
