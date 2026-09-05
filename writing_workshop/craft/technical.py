# SPDX-License-Identifier: Apache-2.0
"""Craft checks for technical documents.

These are the ones that make a manual trustworthy, and every one of them is
deterministic. The most valuable is `units`: two different values for the
same named quantity is a defect, full stop, and finding it needs no model
at all. It is the torque-spec class of failure — 40 Nm in §4.2 and 45 Nm in
the appendix — and it is the reason this workshop exists.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re

from .. import textio as T
from ..types import DEFECT, NOTE, TECHNICAL, WARN, CraftReport, Finding, Span
from ..units import NUM_UNIT, QUANTITY_WORDS, conflict, dimension
from . import ANY_LANGUAGE, Ctx, check

# ---------------------------------------------------------------------------
# terminology drift
# ---------------------------------------------------------------------------

_TITLE_RUN = re.compile(
    r"\b(?:[A-Z][a-z0-9]+(?:[-/][A-Za-z0-9]+)*)(?:\s+"
    r"(?:[A-Z][a-z0-9]+|of|the|and|for)(?:[-/][A-Za-z0-9]+)*){0,3}\b")
_HYPHENATED = re.compile(r"\b[A-Za-z]{3,}(?:-[A-Za-z]{2,})+\b")
#: `WiFi`, `PowerSupply`, `SubSystem`. Needed as its own pattern
#: because the title-case run stops at the internal capital and
#: yields "Wi" -- so the ONE pair this check exists to catch,
#: `Wi-Fi` against `WiFi`, was invisible to it.
_CAMEL = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b")


@check("terminology", "Terminology drift", TECHNICAL)
def terminology(ctx: Ctx) -> CraftReport:
    """The same concept under three names — the defect that makes a manual
    untrustworthy, and pure measurement.

    Clusters surface forms whose `term_key` matches: `Wi-Fi` / `WiFi`,
    `e-mail` / `email`, `power supply` / `power supplies`. Case-only
    differences are deliberately NOT reported: a term at the start of a
    sentence is capitalised for grammar, and flagging that would bury the
    real finding under one per sentence.
    """
    rep = CraftReport()
    forms: defaultdict[str, Counter] = defaultdict(Counter)
    where: defaultdict[str, list[Span]] = defaultdict(list)
    seeded = {T.term_key(t) for t in ctx.terms}

    for src in ctx.doc.files:
        prose = ctx.doc.prose_of_file(src.rel)
        for rx in (_TITLE_RUN, _HYPHENATED, _CAMEL):
            for m in rx.finditer(prose):
                text, offset = _trim_term(m.group(0))
                if len(text) < 4 or T.is_common(text):
                    continue
                key = T.term_key(text)
                if len(key) < 4:
                    continue
                forms[key][text.casefold()] += 1
                where[key].append(Span(src.rel, m.start() + offset,
                                       m.start() + offset + len(text)))
    for term in ctx.terms:
        key = T.term_key(term)
        if key not in forms:
            for span in ctx.doc.find(term):
                forms[key][term.casefold()] += 1
                where[key].append(span)

    drifted = 0
    for key, counter in forms.items():
        if len(counter) < 2:
            continue
        total = sum(counter.values())
        # A PUNCTUATION VARIANT IS NEVER A COINCIDENCE. `Wi-Fi` against
        # `WiFi`, `e-mail` against `email`, `back-up` against `backup` --
        # when every surface form collapses to the same letters, one use
        # of each is already the finding. Anything else (a plural, a
        # different word order) needs more evidence before it is worth the
        # author's attention, because that is where the noise lives.
        punctuation_only = len({re.sub(r"[^a-z0-9]", "", f)
                                for f in counter}) == 1
        if total < 3 and not punctuation_only and key not in seeded:
            continue
        variants = ", ".join(f"“{name}” ×{n}"
                             for name, n in counter.most_common())
        winner = counter.most_common(1)[0][0]
        rep.findings.append(Finding(
            "terminology", WARN,
            f"{len(counter)} spellings of one term: {variants}",
            f"A reader searching for one of these will not find the "
            f"others. “{winner}” is the commonest — if that is the right "
            f"one, the rest are typos with a long half-life.",
            span=where[key][0],
            section_id=_sid(ctx, where[key][0]),
            evidence=[ctx.doc.quote(s) for s in where[key][:3]],
            data={"forms": dict(counter)}))
        drifted += 1
    rep.metrics["terminology_clusters"] = drifted
    return rep


_CONNECTIVES = {"of", "the", "and", "for", "a", "an", "to", "in", "on"}


def _trim_term(text: str) -> tuple[str, int]:
    """Strip ordinary English off both ends of a title-case run.

    The run pattern happily starts on a capital that is only capitalised
    because it opens a sentence, and swallows connectives on the way: `Use
    the Wi-Fi` came back as one term, whose key was `usethewifi`, so it
    never clustered with `WiFi` -- and the ONE pair this check exists to
    catch was invisible. Returns the trimmed term and its offset into the
    original, so the span still points at the words on the page.
    """
    parts = text.split()
    start = 0
    while parts and (T.is_common(parts[0]) or
                     parts[0].lower() in _CONNECTIVES):
        start += len(parts[0]) + 1
        parts = parts[1:]
    while parts and parts[-1].lower() in _CONNECTIVES:
        parts = parts[:-1]
    return " ".join(parts), start


def _sid(ctx: Ctx, span: Span) -> str:
    sec = ctx.doc.section_at(span)
    return sec.id if sec else ""


# ---------------------------------------------------------------------------
# definitions, undefined terms, acronyms
# ---------------------------------------------------------------------------

_DEF_PATTERNS = (
    re.compile(r"^\s*\*\*(?P<term>[^*]{2,60})\*\*\s*[—\-–:]\s*(?P<body>.+)$"),
    re.compile(r"^\s*(?P<term>[A-Z][\w \-/]{1,58}?)\s*[—–:]\s+(?P<body>.+)$"),
    re.compile(r"^\s*[-*]\s+\*?\*?(?P<term>[^*:—–]{2,60}?)\*?\*?\s*"
               r"[—–:]\s+(?P<body>.+)$"),
)
_INLINE_DEF = re.compile(
    r"\b(?P<term>[A-Z][\w\- ]{2,40}?)\s+(?:is|are)\s+"
    r"(?:defined as|known as|called|termed)\b")
_ACRONYM = re.compile(r"\b([A-Z][A-Z0-9]{1,7})(s|’s|'s)?\b")
_ACRONYM_SKIP = {"OK", "TV", "PDF", "USB", "USA", "UK", "EU", "AM", "PM",
                 "ID", "TO", "IT", "IS", "AND", "THE", "OR", "NOT", "IF",
                 "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}


@dataclass
class Definition:
    term: str
    body: str
    span: Span
    order: int
    in_glossary: bool


def _definitions(ctx: Ctx) -> list[Definition]:
    out: list[Definition] = []
    titles = {t.lower() for t in ctx.glossary_titles}
    for sec in ctx.doc.sections:
        in_gloss = any(t in sec.title.lower() for t in titles)
        src = ctx.doc.file(sec.path)
        if not src:
            continue
        prose = ctx.doc.prose_of_file(sec.path)
        for block in src.blocks:
            if not block.is_prose:
                continue
            if not (sec.body.start <= block.start < sec.body.end):
                continue
            text = prose[block.start:block.end]
            for line_off, line in _lines(text):
                for rx in _DEF_PATTERNS:
                    m = rx.match(line)
                    if not m:
                        continue
                    term = m.group("term").strip(" *_`")
                    if not term or len(term) > 60:
                        continue
                    # Outside a glossary, only a LIST ITEM counts as a
                    # definition. Tested on the block kind rather than on
                    # a leading "-": the prose is masked, the marker is
                    # already a space by the time it gets here, and the
                    # string test silently rejected every entry.
                    if not in_gloss and block.kind not in (T.LIST,
                                                           T.ORDERED):
                        continue
                    if _CAPTION.match(term + " -"):
                        continue
                    start = block.start + line_off
                    out.append(Definition(
                        term, m.group("body").strip(),
                        Span(sec.path, start, start + len(line)),
                        sec.order, in_gloss))
                    break
        for m in _INLINE_DEF.finditer(prose[sec.body.start:sec.body.end]):
            start = sec.body.start + m.start("term")
            out.append(Definition(
                m.group("term").strip(), "",
                Span(sec.path, start, start + len(m.group("term"))),
                sec.order, False))
    return out


def _lines(text: str):
    pos = 0
    for line in text.splitlines(keepends=True):
        yield pos, line.rstrip("\r\n")
        pos += len(line)


@check("definitions", "Undefined and late-defined terms", TECHNICAL)
def definitions(ctx: Ctx) -> CraftReport:
    """A term used before the glossary defines it, or never defined at all.

    The second half only fires on terms the project NAMED as terms of art,
    or on acronyms. Guessing which capitalised phrase in a manual is a term
    is how a check becomes a hundred findings the author scrolls past, and
    a check nobody reads is worse than no check.
    """
    rep = CraftReport()
    defs = _definitions(ctx)
    by_key = {T.term_key(d.term): d for d in defs}
    rep.metrics["definitions"] = len(defs)

    order_of = {s.id: s.order for s in ctx.doc.sections}
    for term in ctx.terms:
        key = T.term_key(term)
        hits = ctx.doc.find(term)
        if not hits:
            continue
        if key not in by_key:
            rep.findings.append(Finding(
                "definitions", WARN, f"“{term}” is never defined",
                f"Used {len(hits)} times and not defined in a glossary or "
                f"at first use. The project lists it as a term of art.",
                span=hits[0], section_id=_sid(ctx, hits[0]),
                evidence=[ctx.doc.quote(hits[0])],
                data={"uses": len(hits)}))
            continue
        definition = by_key[key]
        first = min(hits, key=lambda s: (order_of.get(_sid(ctx, s), 0),
                                         s.start))
        first_order = order_of.get(_sid(ctx, first), 0)
        if _defined_at_first_use(ctx, term, first):
            continue
        if first_order < definition.order:
            rep.findings.append(Finding(
                "definitions", WARN,
                f"“{term}” is used before it is defined",
                f"First used in {_label(ctx, first)}; defined later in "
                f"{_label(ctx, definition.span)}. A reader meeting it "
                f"first has nowhere to look.",
                span=first, section_id=_sid(ctx, first),
                evidence=[ctx.doc.quote(first), definition.body[:160]]))
    return rep


def _defined_at_first_use(ctx: Ctx, term: str, first: Span) -> bool:
    """`Power Supply Unit (PSU)` at first use answers the reader already.

    Without this, a manual that does the RIGHT thing -- expand on first
    use, then list it in the glossary as well -- is told off for it, which
    is the fastest way to teach an author that a check is wrong.
    """
    prose = ctx.doc.prose_of_file(first.path)
    if term.isupper() and len(term) <= 8:
        return _expanded_near(prose, first.start, term)
    sentence = ctx.doc.quote(first)
    return bool(re.search(r"[\u2014\u2013:]|\bis (?:defined|known|called)\b",
                          sentence))


def _label(ctx: Ctx, span: Span) -> str:
    sec = ctx.doc.section_at(span)
    return ctx.doc.label(sec) if sec else span.path


@check("acronyms", "Acronym first-use expansion", TECHNICAL,
       languages=ANY_LANGUAGE)
def acronyms(ctx: Ctx) -> CraftReport:
    """Every acronym expanded on first appearance, and only the first.

    Both halves are defects and the second one is the one nobody checks:
    an acronym re-expanded in section 12 tells the reader they were
    supposed to have forgotten it, which is exactly the wrong signal in a
    reference document.
    """
    rep = CraftReport()
    first_use: dict[str, Span] = {}
    expansions: dict[str, list[Span]] = defaultdict(list)
    counts: Counter = Counter()
    order: dict[str, int] = {}

    for sec in ctx.doc.sections:
        prose = ctx.doc.prose_of_file(sec.path)
        body = prose[sec.body.start:sec.body.end]
        for m in _ACRONYM.finditer(body):
            acr = m.group(1)
            if acr in _ACRONYM_SKIP or acr.isdigit():
                continue
            span = Span(sec.path, sec.body.start + m.start(),
                        sec.body.start + m.end())
            counts[acr] += 1
            if acr not in first_use:
                first_use[acr] = span
                order[acr] = sec.order
            if _expanded_near(body, m.start(), acr):
                expansions[acr].append(span)

    for acr, n in counts.items():
        if n < 2:
            continue
        spans = expansions.get(acr, [])
        if not spans:
            rep.findings.append(Finding(
                "acronyms", WARN, f"{acr} is never expanded",
                f"Used {n} times with no expansion anywhere. Spell it out "
                f"once, at first use.",
                span=first_use[acr], section_id=_sid(ctx, first_use[acr]),
                evidence=[ctx.doc.quote(first_use[acr])],
                data={"uses": n}))
            continue
        if spans[0].start > first_use[acr].start or (
                _sid(ctx, spans[0]) != _sid(ctx, first_use[acr])
                and _order(ctx, spans[0]) > order[acr]):
            rep.findings.append(Finding(
                "acronyms", WARN, f"{acr} is expanded after its first use",
                f"First used in {_label(ctx, first_use[acr])}, expanded "
                f"later in {_label(ctx, spans[0])}.",
                span=first_use[acr], section_id=_sid(ctx, first_use[acr]),
                evidence=[ctx.doc.quote(first_use[acr]),
                          ctx.doc.quote(spans[0])]))
        if len(spans) > 1:
            rep.findings.append(Finding(
                "acronyms", NOTE, f"{acr} is expanded {len(spans)} times",
                "Expanding it again tells the reader they were meant to "
                "have forgotten it.",
                span=spans[1], section_id=_sid(ctx, spans[1]),
                evidence=[ctx.doc.quote(s) for s in spans[:3]]))
    rep.metrics["acronyms"] = len(counts)
    return rep


def _order(ctx: Ctx, span: Span) -> int:
    sec = ctx.doc.section_at(span)
    return sec.order if sec else 0


def _expanded_near(text: str, at: int, acr: str) -> bool:
    """`Power Supply Unit (PSU)` or `PSU (Power Supply Unit)`."""
    letters = [c for c in acr if c.isalpha()]
    window = text[max(0, at - 90):at + 90 + len(acr)]
    for m in re.finditer(r"\(([^)]{3,80})\)", window):
        inner = m.group(1)
        if _initials_match(inner, letters):
            return True
    before = text[max(0, at - 90):at]
    if _initials_match(before, letters):
        return True
    after = text[at + len(acr):at + 120]
    if after.lstrip().startswith("("):
        return _initials_match(after[:120], letters)
    return False


def _initials_match(text: str, letters: list[str]) -> bool:
    words = [w for w in T.word_list(text) if w]
    if len(words) < len(letters):
        return False
    tail = words[-len(letters):]
    if all(w[:1].upper() == c.upper() for w, c in zip(tail, letters,
                                                strict=False)):
        return True
    head = words[:len(letters)]
    return all(w[:1].upper() == c.upper() for w, c in zip(head, letters,
                                                strict=False))


# ---------------------------------------------------------------------------
# cross-references
# ---------------------------------------------------------------------------

_XREF = re.compile(
    r"\b(?:(?P<kind>section|clause|chapter|part|appendix|annex|figure|fig"
    r"|table|step|item|equation|eq)\.?\s*(?P<id>[A-Z]?\d+(?:\.\d+)*|[A-Z])"
    r"|§\s*(?P<sid>\d+(?:\.\d+)*))\b", re.I)
_CAPTION = re.compile(
    r"^\s*\**(?P<kind>figure|fig|table)\.?\s*(?P<id>[A-Z]?\d+(?:\.\d+)*)"
    r"\**\s*[-—–:.]", re.I)
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


@check("xrefs", "Cross-reference integrity", TECHNICAL)
def xrefs(ctx: Ctx) -> CraftReport:
    """Does §4.2 exist; does Figure 7 exist; was anything referenced that
    got deleted.

    Deterministic, and it is the check that breaks silently on every edit
    pass — a section renumbered in one place leaves nine references
    pointing at nothing, and nothing in a markdown workflow notices.
    """
    rep = CraftReport()
    numbers = {s.number for s in ctx.doc.sections if s.number}
    numbers |= {s.derived_number for s in ctx.doc.sections}
    titles = {s.title.strip().lower() for s in ctx.doc.sections}
    appendices = {s.title.split()[-1].strip(":.").upper()
                  for s in ctx.doc.sections
                  if s.title.lower().startswith(("appendix", "annex"))
                  and len(s.title.split()) > 1}
    captions: defaultdict[str, set[str]] = defaultdict(set)
    for src in ctx.doc.files:
        prose = ctx.doc.prose_of_file(src.rel)
        for block in src.blocks:
            head = prose[block.start:block.end].lstrip()[:60]
            m = _CAPTION.match(head)
            if m:
                kind = "figure" if m.group("kind").lower().startswith("fig") \
                    else "table"
                captions[kind].add(m.group("id").upper())
        for sec in ctx.doc.sections:
            if sec.path == src.rel and sec.title:
                m = _CAPTION.match(sec.title)
                if m:
                    kind = ("figure" if m.group("kind").lower()
                            .startswith("fig") else "table")
                    captions[kind].add(m.group("id").upper())

    broken = 0
    checked = 0
    for src in ctx.doc.files:
        prose = ctx.doc.prose_of_file(src.rel)
        for m in _XREF.finditer(prose):
            kind = (m.group("kind") or "section").lower()
            ident = (m.group("id") or m.group("sid") or "").upper()
            if not ident:
                continue
            if kind in ("step", "item"):
                continue                      # handled by step_numbering
            checked += 1
            span = Span(src.rel, m.start(), m.end())
            ok = True
            if kind in ("section", "clause", "chapter", "part"):
                ok = (ident in numbers or ident.lower() in titles
                      or ident.lower() in {n.lower() for n in numbers})
            elif kind in ("appendix", "annex"):
                ok = ident in appendices or ident in numbers
            elif kind in ("figure", "fig"):
                ok = ident in captions["figure"]
            elif kind == "table":
                ok = ident in captions["table"]
            else:
                ok = True
            if not ok:
                broken += 1
                known = (sorted(captions[kind if kind != "fig" else
                                         "figure"])[:6]
                         if kind in ("figure", "fig", "table")
                         else sorted(numbers)[:6])
                rep.findings.append(Finding(
                    "xrefs", DEFECT,
                    f"“{m.group(0)}” does not resolve",
                    f"Nothing in the document answers to it. "
                    f"Known: {', '.join(known) or 'none'}"
                    f"{'…' if known else ''}.",
                    span=span, section_id=_sid(ctx, span),
                    evidence=[ctx.doc.quote(span)],
                    data={"kind": kind, "id": ident}))
        for m in _MD_LINK.finditer(src.text):
            target = m.group(1).split("#")[0]
            if not target or target.startswith(("http:", "https:", "mailto:",
                                                "#")):
                continue
            checked += 1
            if not (src.path.parent / target).exists():
                broken += 1
                span = Span(src.rel, m.start(), m.end())
                rep.findings.append(Finding(
                    "xrefs", DEFECT, f"Link target missing: {target}",
                    "The file this link points at is not on disk.",
                    span=span, section_id=_sid(ctx, span)))
    rep.metrics["xrefs_checked"] = checked
    rep.metrics["xrefs_broken"] = broken
    rep.metrics["figures"] = len(captions["figure"])
    rep.metrics["tables"] = len(captions["table"])
    return rep


# ---------------------------------------------------------------------------
# procedures: numbering and step length
# ---------------------------------------------------------------------------


def _procedures(ctx: Ctx, numbering_matters: bool = False):
    """Contiguous runs of ordered-list items, or of `Step N` paragraphs.

    `numbering_matters` excludes DERIVED files. A `.docx` stores no list
    numbers — Word's renderer supplies them — so the whole premise of the
    step-numbering check ("the source is the truth here, not the render")
    is false there, and running it would report gaps this package
    invented while reading the file. Length inside a step is still real,
    so `long_steps` asks for everything.
    """
    for src in ctx.doc.files:
        if numbering_matters and src.derived:
            continue
        run: list[T.Block] = []
        for block in src.blocks:
            number = 0
            if block.kind == T.ORDERED:
                number = block.number
            elif block.kind == T.PARA:
                number = T.step_number(block.text)
            if number:
                block.number = number
                run.append(block)
            elif block.kind in (T.PARA, T.HEADING) and run:
                if block.kind == T.HEADING or len(block.text) > 200:
                    yield src, run
                    run = []
        if run:
            yield src, run


@check("steps", "Step numbering integrity", TECHNICAL,
       languages=ANY_LANGUAGE)
def steps(ctx: Ctx) -> CraftReport:
    """Gaps, duplicates and restarts in a numbered procedure.

    A markdown renderer silently renumbers ordered lists, so `1. 2. 2. 4.`
    displays as `1 2 3 4` and looks perfect — while the text of step 4 says
    "as in step 3" and means something else. The source is the truth here,
    not the render.
    """
    rep = CraftReport()
    procedures = 0
    skipped = [s.rel for s in ctx.doc.derived_files]
    if skipped:
        rep.metrics["steps_not_checked"] = skipped
    for src, run in _procedures(ctx, numbering_matters=True):
        if len(run) < 3:
            continue
        procedures += 1
        nums = [b.number for b in run]
        span = Span(src.rel, run[0].start, run[-1].end)
        expected = list(range(nums[0], nums[0] + len(nums)))
        if nums == expected:
            continue
        seen = Counter(nums)
        dupes = [n for n, c in seen.items() if c > 1]
        gaps = [n for n in range(min(nums), max(nums) + 1)
                if n not in seen]
        detail = []
        if dupes:
            detail.append("duplicated: " + ", ".join(map(str, sorted(dupes))))
        if gaps:
            detail.append("missing: " + ", ".join(map(str, gaps)))
        if not detail:
            detail.append(f"runs {nums[0]}…{nums[-1]} out of order")
        rep.findings.append(Finding(
            "steps", DEFECT,
            f"Step numbering broken in {_label(ctx, span)}",
            "; ".join(detail) + ". A renderer will renumber these and hide "
            "it, so a cross-reference to “step 3” may point at the wrong "
            "instruction.",
            span=span, section_id=_sid(ctx, span),
            evidence=[" ".join(b.text.split())[:90] for b in run[:4]],
            data={"numbers": nums}))
    rep.metrics["procedures"] = procedures
    return rep


@check("long_steps", "Long instructions", TECHNICAL,
       languages=ANY_LANGUAGE)
def long_steps(ctx: Ctx) -> CraftReport:
    """Sentence length INSIDE a numbered step, not sentence length
    generally.

    A forty-word instruction is an instruction somebody will get wrong at
    3am with cold hands and a torch in their teeth. Long sentences in the
    surrounding prose are a matter of taste; long sentences in a step are a
    safety property, which is why this is its own check with its own
    threshold rather than a slice of the length distribution.
    """
    warn = int(ctx.opt("step_words_warn", 30))
    bad = int(ctx.opt("step_words_defect", 40))
    rep = CraftReport()
    worst = 0
    total = 0
    for src, run in _procedures(ctx):
        for block in run:
            total += 1
            prose = ctx.doc.prose_of_file(src.rel)
            body = prose[block.start:block.end]
            for s, e in T.sentences(body, base=block.start):
                n = len(T.word_list(prose[s:e]))
                worst = max(worst, n)
                if n < warn:
                    continue
                span = Span(src.rel, s, e)
                rep.findings.append(Finding(
                    "long_steps", DEFECT if n >= bad else WARN,
                    f"Step {block.number}: a {n}-word instruction",
                    "Split it. One action per step is the only rule of "
                    "procedural writing that survives contact with a tired "
                    "reader.",
                    span=span, section_id=_sid(ctx, span),
                    evidence=[" ".join(prose[s:e].split())],
                    data={"words": n, "step": block.number}))
    rep.metrics["steps_total"] = total
    rep.metrics["longest_step_words"] = worst
    return rep


# ---------------------------------------------------------------------------
# normative register
# ---------------------------------------------------------------------------

_MODALS = ("shall", "must", "should", "may", "will", "can")


@check("register", "Normative language (shall / should / may)", TECHNICAL)
def register(ctx: Ctx) -> CraftReport:
    """In a specification these are not stylistic choices.

    `shall` and `must` both state a requirement; using both in one document
    invites a reader to look for a distinction that is not there. `may` is
    permission and `can` is capability, and swapping them changes what the
    document licenses. Counted, with the dominant form named — the tool has
    no opinion about WHICH convention, only about mixing them.
    """
    rep = CraftReport()
    counts: Counter = Counter()
    where: defaultdict[str, list[Span]] = defaultdict(list)
    for src in ctx.doc.files:
        prose = ctx.doc.prose_of_file(src.rel)
        for m in re.finditer(r"\b(" + "|".join(_MODALS) + r")\b", prose,
                             re.I):
            word = m.group(1).lower()
            counts[word] += 1
            where[word].append(Span(src.rel, m.start(), m.end()))
    rep.metrics["modals"] = dict(counts)
    if counts["shall"] >= 3 and counts["must"] >= 3:
        rep.findings.append(Finding(
            "register", WARN,
            f"Requirements are written both ways: “shall” ×"
            f"{counts['shall']} and “must” ×{counts['must']}",
            "Both state a requirement. Using both invites a reader to hunt "
            "for a distinction the document does not make. Pick one and "
            "make the other mean something else, or nothing.",
            span=where["shall"][0], section_id=_sid(ctx, where["shall"][0]),
            evidence=[ctx.doc.quote(where["shall"][0]),
                      ctx.doc.quote(where["must"][0])]))
    if counts["may"] >= 3 and counts["can"] >= 3:
        rep.findings.append(Finding(
            "register", NOTE,
            f"“may” ×{counts['may']} and “can” ×{counts['can']}",
            "`may` grants permission; `can` states a capability. Worth a "
            "pass to confirm each one means what it says.",
            span=where["may"][0], section_id=_sid(ctx, where["may"][0])))
    return rep


# ---------------------------------------------------------------------------
# units and numbers
# ---------------------------------------------------------------------------

@check("units", "Unit and number consistency", TECHNICAL)
def units(ctx: Ctx) -> CraftReport:
    """The same quantity given two values anywhere in the document.

    This catches the torque-spec class of defect before any model is
    involved, and it is deterministic. Two quantities disagree when their
    STATED-PRECISION intervals do not overlap — so `40 Nm` in §4.2 and
    `29.5 lb-ft` in the appendix are recognised as the author's own correct
    conversion rather than reported as a contradiction, while `40 Nm` and
    `45 Nm` are a defect. See `writing_workshop.units` for why that is a
    precision question and not a tolerance anybody has to justify.
    """
    rep = CraftReport()
    seen: defaultdict[str, list[tuple[str, str, str, Span]]] = defaultdict(
        list)
    styles: defaultdict[str, Counter] = defaultdict(Counter)
    commas = 0
    plain = 0

    for src in ctx.doc.files:
        prose = ctx.doc.prose_of_file(src.rel)
        for m in NUM_UNIT.finditer(prose):
            raw = m.group("num")
            if "," in raw:
                commas += 1
            elif len(raw.split(".")[0]) > 3:
                plain += 1
            unit = m.group("unit").lower()
            dim = dimension(unit)
            span = Span(src.rel, m.start(), m.end())
            styles[dim][m.group("unit")] += 1
            subject = _quantity_before(prose, m.start(), ctx)
            if not subject:
                continue
            seen[f"{subject}|{dim}"].append(
                (raw, unit, m.group(0), span))

    for key, rows in seen.items():
        pairs = [(a, b) for i, a in enumerate(rows) for b in rows[i + 1:]
                 if conflict(a[0], a[1], b[0], b[1])]
        if not pairs:
            continue
        subject, dim = key.split("|", 1)
        values = sorted({r[2] for pair in pairs for r in pair})
        first = min((r[3] for pair in pairs for r in pair),
                    key=lambda sp: (sp.path, sp.start))
        rep.findings.append(Finding(
            "units", DEFECT,
            f"“{subject}” is given {len(values)} different values",
            "Two values for one named quantity is a contradiction "
            "somewhere. Compared at the precision each was written to, so "
            "this is neither a units mismatch nor a rounding difference — "
            "the numbers really differ.",
            span=first, section_id=_sid(ctx, first),
            evidence=[f"{_label(ctx, r[3])}: {r[2]}"
                      for pair in pairs[:2] for r in pair],
            data={"subject": subject, "dimension": dim, "values": values}))

    for dim, counter in styles.items():
        if len(counter) > 1 and sum(counter.values()) >= 4:
            variants = ", ".join(f"{n}×{c}" for n, c in
                                 counter.most_common())
            if len({n.lower() for n in counter}) > 1:
                rep.findings.append(Finding(
                    "units", WARN,
                    f"{dim.title()} is written several ways: {variants}",
                    "Pick one symbol and use it. A reader scanning for a "
                    "figure searches for the symbol, not the dimension.",
                    data={"dimension": dim, "forms": dict(counter)}))
    if commas and plain:
        rep.findings.append(Finding(
            "units", NOTE,
            f"Large numbers are written both ways ({commas} with a "
            f"separator, {plain} without)",
            "Cosmetic, and the sort of thing a reviewer sends back.",
            data={"grouped": commas, "plain": plain}))
    rep.metrics["quantities"] = sum(len(v) for v in seen.values())
    return rep


def _quantity_before(prose: str, at: int, ctx: Ctx) -> str:
    """The quantity word governing a number, looking both ways.

    `torque of 40 Nm`, `torque: 40 Nm`, `40 Nm of torque`, `tighten the
    bolt to 40 Nm` (which finds nothing, correctly — an unnamed number is
    not a claim about a named quantity and guessing one would manufacture
    conflicts).
    """
    extra = {T.normalise(t) for t in ctx.terms}
    before = prose[max(0, at - 60):at]
    after = prose[at:at + 60]
    words_before = [T.normalise(w) for w in T.word_list(before)]
    for word in reversed(words_before[-6:]):
        if word in QUANTITY_WORDS or word in extra:
            return word
    words_after = [T.normalise(w) for w in T.word_list(after)][:5]
    for word in words_after:
        if word in QUANTITY_WORDS or word in extra:
            return word
    return ""
