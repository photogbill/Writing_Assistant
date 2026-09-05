# SPDX-License-Identifier: Apache-2.0
"""Craft checks for fiction.

A novel's shape is visible in its pacing curve and nowhere else, and the
author cannot see it from inside chapter nineteen. Everything here is the
same arithmetic the technical checks use, pointed at a different failure:
not "is this document consistent with itself" but "is this book the shape
its author thinks it is".
"""

from __future__ import annotations

from collections import Counter
import re

from .. import textio as T
from ..types import FICTION, NOTE, WARN, CraftReport, Finding, Span
from . import ANY_LANGUAGE, Ctx, check
from .shared import describe, detect_cast

_DQUOTE = re.compile(r"[\"“]([^\"“”]{2,600}?)[\"”]", re.S)
_SQUOTE = re.compile(r"(?<![A-Za-z])[‘']([^‘’']{4,600}?)[’'](?![A-Za-z])",
                     re.S)

INTERIOR = {"thought", "felt", "knew", "wondered", "realised", "realized",
            "remembered", "hoped", "feared", "wanted", "decided", "noticed",
            "supposed", "guessed", "understood", "believed", "considered",
            "regretted", "wished", "suspected", "recalled"}

SAID = {"said", "says", "asked", "asks", "replied", "answered", "told"}

def _quoted_spans(text: str) -> list[tuple[int, int]]:
    spans = [(m.start(1), m.end(1)) for m in _DQUOTE.finditer(text)]
    if not spans:
        spans = [(m.start(1), m.end(1)) for m in _SQUOTE.finditer(text)]
    return spans


# ---------------------------------------------------------------------------
# pacing
# ---------------------------------------------------------------------------


@check("pacing", "Pacing curve", FICTION, languages=ANY_LANGUAGE)
def pacing(ctx: Ctx) -> CraftReport:
    """Scene and chapter lengths over the document, as a series to draw.

    The finding is not "this chapter is too long" — no arithmetic knows
    that. It is "this chapter is three times your own median", which is a
    fact about the book the author can act on or dismiss in one look.
    """
    rep = CraftReport()
    chapters = []
    for sec in ctx.doc.chapters():
        scenes = ctx.doc.scenes(sec)
        prose = ctx.doc.prose_of_file(sec.path)
        scene_words = [len(T.word_list(prose[s.start:s.end])) for s in scenes]
        chapters.append({"id": sec.id, "title": sec.title,
                         "words": sec.words, "scenes": len(scenes),
                         "scene_words": scene_words})
    rep.metrics["pacing"] = chapters
    counts = [float(c["words"]) for c in chapters if c["words"]]
    summary = describe(counts)
    rep.metrics["chapter_words"] = summary
    median = summary["median"] or 0
    if median and len(counts) >= 4:
        for row in chapters:
            if row["words"] > median * 2.2:
                sec = ctx.doc.section(row["id"])
                rep.findings.append(Finding(
                    "pacing", NOTE,
                    f"{row['title']} is {row['words']:,} words — "
                    f"{row['words'] / median:.1f}× your median chapter",
                    "Long chapters are a choice; this one is far enough "
                    "from the rest of the book to be worth confirming as "
                    "one.",
                    span=sec.body if sec else None, section_id=row["id"],
                    data=row))
            elif row["words"] and row["words"] < median * 0.35:
                sec = ctx.doc.section(row["id"])
                rep.findings.append(Finding(
                    "pacing", NOTE,
                    f"{row['title']} is {row['words']:,} words — well "
                    f"under your median",
                    "Short chapters accelerate. Deliberate here?",
                    span=sec.body if sec else None, section_id=row["id"],
                    data=row))
    return rep


# ---------------------------------------------------------------------------
# dialogue
# ---------------------------------------------------------------------------


@check("dialogue", "Dialogue-to-narration ratio", FICTION,
       languages=ANY_LANGUAGE)
def dialogue(ctx: Ctx) -> CraftReport:
    rep = CraftReport()
    rows = {}
    total_q = total_w = 0
    for sec in ctx.doc.chapters():
        prose = ctx.doc.prose_of_file(sec.path)
        body = prose[sec.body.start:sec.body.end]
        words = len(T.word_list(body))
        if words < 100:
            continue
        quoted = sum(len(T.word_list(body[s:e]))
                     for s, e in _quoted_spans(body))
        rows[sec.id] = {"title": sec.title, "words": words,
                        "dialogue": quoted,
                        "ratio": round(quoted / words, 3)}
        total_q += quoted
        total_w += words
    rep.metrics["dialogue_by_chapter"] = rows
    if total_w:
        overall = total_q / total_w
        rep.metrics["dialogue_ratio"] = round(overall, 3)
        for sid, row in rows.items():
            if abs(row["ratio"] - overall) > 0.30:
                sec = ctx.doc.section(sid)
                which = "far more" if row["ratio"] > overall else "far less"
                rep.findings.append(Finding(
                    "dialogue", NOTE,
                    f"{row['title']}: {which} dialogue than the book "
                    f"({row['ratio']:.0%} against {overall:.0%})",
                    "A chapter that is nearly all dialogue or nearly none "
                    "reads at a different speed from the rest.",
                    span=sec.body if sec else None, section_id=sid,
                    data=row))
    return rep


@check("dialogue_tags", "Dialogue tag habits", FICTION)
def dialogue_tags(ctx: Ctx) -> CraftReport:
    """`said` versus the ninety alternatives.

    `said` is invisible and that is its job. The finding is the RATIO and
    the specific exotics, because a writer who has used `expostulated` once
    wants to know, and a writer who uses `hissed` forty times has a tic.
    """
    rep = CraftReport()
    tags: Counter = Counter()
    adverbial = []
    for src in ctx.doc.files:
        prose = ctx.doc.prose_of_file(src.rel)
        for m in re.finditer(
                r"[\"”'’]\s*,?\s*(?:[A-Z][a-z]+\s+)?([a-z]{3,15})(ed|s)?\b"
                r"(\s+\w+ly)?", prose):
            verb = T.normalise(m.group(1) + (m.group(2) or ""))
            if verb in T.STOPWORDS or T.is_common(verb) and verb not in SAID:
                if verb not in SAID and not verb.endswith(("ed", "s")):
                    continue
            tags[verb] += 1
            if m.group(3):
                adverbial.append((Span(src.rel, m.start(), m.end()),
                                  verb, m.group(3).strip()))
    total = sum(tags.values())
    said = sum(tags[v] for v in SAID)
    rep.metrics["dialogue_tags"] = dict(tags.most_common(25))
    if total >= 20:
        rep.metrics["said_share"] = round(said / total, 3)
        exotics = [(v, n) for v, n in tags.most_common()
                   if v not in SAID and n >= max(4, total // 25)]
        if exotics:
            rep.findings.append(Finding(
                "dialogue_tags", NOTE,
                "Tag verbs used often: "
                + ", ".join(f"{v} ×{n}" for v, n in exotics[:8]),
                f"“said” is {said / total:.0%} of your tags. It is "
                f"invisible to a reader, which is what makes it useful; "
                f"anything else asks to be noticed.",
                data={"exotics": exotics[:12], "said_share": said / total}))
    if len(adverbial) >= 4:
        rep.findings.append(Finding(
            "dialogue_tags", WARN,
            f"{len(adverbial)} dialogue tags carry an adverb",
            "“said angrily” usually means the line itself is not angry "
            "enough. Worth reading the line aloud without the adverb.",
            span=adverbial[0][0], evidence=[
                f"{verb} {adv}" for _s, verb, adv in adverbial[:6]]))
    return rep


# ---------------------------------------------------------------------------
# point of view
# ---------------------------------------------------------------------------


@check("pov", "Point-of-view drift", FICTION)
def pov(ctx: Ctx) -> CraftReport:
    """A scene that changes whose head it is in, without a break.

    Measured, not judged: within one scene, count the characters who are
    given INTERIORITY — "Mira knew", "he wondered" — because that is what
    a viewpoint actually is. Two of them in one scene is either a
    deliberate omniscient narrator or the commonest continuity error in
    drafting, and the tool says which scene rather than which it thinks.
    """
    rep = CraftReport()
    cast = detect_cast(ctx)
    if not cast:
        rep.metrics["pov"] = "no cast detected"
        return rep
    names = {T.normalise(n): n for n in cast}
    flagged = 0
    for sec in ctx.doc.chapters():
        prose = ctx.doc.prose_of_file(sec.path)
        for scene in ctx.doc.scenes(sec):
            body = prose[scene.start:scene.end]
            if len(T.word_list(body)) < 150:
                continue
            holders: Counter = Counter()
            for s, e in T.sentences(body):
                toks = T.word_list(body[s:e])
                for i, word in enumerate(toks[:-1]):
                    key = T.normalise(word)
                    nxt = T.normalise(toks[i + 1])
                    if nxt in INTERIOR and key in names:
                        holders[names[key]] += 1
                    elif nxt in INTERIOR and key in ("he", "she", "they",
                                                     "i"):
                        holders[key] += 1
            strong = [n for n, c in holders.items() if c >= 2]
            if len(strong) >= 2:
                flagged += 1
                rep.findings.append(Finding(
                    "pov", WARN,
                    f"Two viewpoints in one scene of {sec.title}: "
                    + ", ".join(strong[:3]),
                    "Both are given thoughts inside the same scene with no "
                    "break between them. Deliberate omniscience, or a head "
                    "hop — the tool cannot tell and does not guess.",
                    span=scene, section_id=sec.id,
                    data={"holders": dict(holders)}))
    rep.metrics["pov_scenes_flagged"] = flagged
    return rep


# ---------------------------------------------------------------------------
# character presence
# ---------------------------------------------------------------------------


@check("presence", "Character presence over time", FICTION)
def presence(ctx: Ctx) -> CraftReport:
    """Who is on the page, chapter by chapter.

    Somebody vanishing for eleven chapters is usually a mistake and always
    worth seeing. This is the fiction half of dropped-thread detection —
    the continuity module does the same arithmetic for objects, places and
    promises.
    """
    rep = CraftReport()
    cast = detect_cast(ctx)
    chapters = ctx.doc.chapters()
    if not cast or len(chapters) < 3:
        rep.metrics["presence"] = {}
        return rep
    matrix: dict[str, list[int]] = {}
    for name in cast:
        row = []
        for sec in chapters:
            prose = ctx.doc.prose_of_file(sec.path)
            body = prose[sec.body.start:sec.body.end]
            row.append(len(re.findall(rf"(?<!\w){re.escape(name)}(?!\w)",
                                      body)))
        matrix[name] = row
    rep.metrics["presence"] = {
        "chapters": [s.title for s in chapters], "matrix": matrix}

    gap_min = int(ctx.opt("absence_chapters", max(4, len(chapters) // 3)))
    for name, row in matrix.items():
        if sum(row) < 6:
            continue
        present = [i for i, n in enumerate(row) if n]
        if not present:
            continue
        longest, at = 0, 0
        for a, b in zip(present, present[1:], strict=False):
            if b - a - 1 > longest:
                longest, at = b - a - 1, a
        trailing = len(row) - 1 - present[-1]
        if longest >= gap_min:
            rep.findings.append(Finding(
                "presence", NOTE,
                f"{name} is absent for {longest} chapters "
                f"({chapters[at].title} → {chapters[at + longest + 1].title})",
                "A character the reader was tracking goes quiet. Fine if "
                "intended; the point is that it is now visible.",
                section_id=chapters[at].id,
                data={"name": name, "gap": longest, "row": row}))
        if trailing >= gap_min and sum(row) >= 10:
            rep.findings.append(Finding(
                "presence", WARN,
                f"{name} disappears after {chapters[present[-1]].title}",
                f"Mentioned {sum(row)} times and then not at all for the "
                f"last {trailing} chapters. Chekhov's other gun.",
                section_id=chapters[present[-1]].id,
                data={"name": name, "trailing": trailing, "row": row}))
    return rep
