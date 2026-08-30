# SPDX-License-Identifier: Apache-2.0
"""`workshop` — the whole no-model half of the tool, from a terminal.

Exists for two reasons beyond convenience. It is the proof that the core
runs with no host and no GPU, and it is how a defect in a craft check gets
reproduced without launching a desktop application.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import codex as CX
from . import continuity as CN
from . import context as CT
from . import diff as DF
from . import export as EX
from . import fingerprint as FP
from .craft import run as run_craft
from .document import Manuscript
from .project import Project
from .types import DEFECT, FICTION, TECHNICAL, WARN
from .version import __version__
from .versions import Versions


def _load(path: str) -> tuple[Project, Manuscript]:
    project = Project.open(path, create=False)
    return project, project.manuscript()


def _print_findings(findings, verbose: bool) -> int:
    problems = 0
    for finding in sorted(findings, key=lambda f: (
            {DEFECT: 0, WARN: 1}.get(f.severity, 2), f.check)):
        mark = {"defect": "!!", "warn": " !", "note": "  "}[finding.severity]
        print(f"{mark} [{finding.check}] {finding.title}")
        if verbose and finding.detail:
            print(f"      {finding.detail}")
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
    report = run_craft(doc, args.type or project.document_type,
                       only=args.only, cast=project.cast,
                       terms=project.terms,
                       glossary_titles=project.glossary_titles)
    if args.json:
        print(json.dumps({"metrics": report.metrics,
                          "findings": [f.__dict__ for f in
                                       report.findings]}, default=str,
                         indent=2))
        return 0
    problems = _print_findings(report.findings, args.verbose)
    print(f"\n{len(report.ran)} checks ran, {problems} things to look at.")
    for name, why in report.skipped.items():
        print(f"   skipped {name}: {why}")
    return 1 if any(f.severity == DEFECT for f in report.findings) else 0


def cmd_continuity(args) -> int:
    project, doc = _load(args.path)
    claims = CX.deterministic(doc, terms=project.terms,
                              subjects=project.cast or None)
    sweep = CN.sweep(doc, claims, cast=project.cast, terms=project.terms)
    _print_findings(sweep.findings, args.verbose)
    print(f"\n{sweep.metrics}")
    return 1 if sweep.metrics.get("deterministic_conflicts") else 0


def cmd_codex(args) -> int:
    project, doc = _load(args.path)
    store = CX.Codex(project.codex_db)
    if args.extract:
        added = store.add_many(
            CX.deterministic(doc, terms=project.terms,
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
    fp = FP.from_manuscript(doc)
    FP.save(fp, project.fingerprint_file)
    print(f"Fitted on {fp.n_words:,} words in "
          f"{fp.metrics.get('_windows', 0)} windows "
          f"({'usable' if fp.trustworthy else 'thin — treat as indicative'})")
    for key, label, _u, _d in FP.METRICS:
        if key in fp.metrics:
            print(f"  {label:38} {fp.metrics[key]:8.3f} "
                  f"± {fp.spread.get(key, 0):.3f}")
    if args.score:
        text = Path(args.score).read_text(encoding="utf-8")
        drifts = FP.score(fp, text)
        print(f"\ndrift {FP.drift_score(drifts)}")
        print(FP.describe(fp, drifts))
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
        sub.set_defaults(fn=fn)
        return sub

    sub = add("outline", cmd_outline, "the derived structure")
    sub.add_argument("--levels", type=int, default=3)

    sub = add("craft", cmd_craft, "the measurements — no model needed")
    sub.add_argument("--type", choices=[TECHNICAL, FICTION])
    sub.add_argument("--only", nargs="*")
    sub.add_argument("--json", action="store_true")

    add("continuity", cmd_continuity, "contradictions, threads, names")

    sub = add("codex", cmd_codex, "the claims store")
    sub.add_argument("--extract", action="store_true",
                     help="propose every claim readable with no model")
    sub.add_argument("--state")

    sub = add("fingerprint", cmd_fingerprint, "fit the author's own style")
    sub.add_argument("--score", help="a file to score against the baseline")

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
        return 130


if __name__ == "__main__":                            # pragma: no cover
    raise SystemExit(main())
