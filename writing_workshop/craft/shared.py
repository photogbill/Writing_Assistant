# SPDX-License-Identifier: Apache-2.0
"""Craft checks that apply to a manual and a novel alike.

The single most valuable one here is `echo`, and it is also the cheapest.
A distinctive word reused two sentences later is invisible to the author
who wrote both instances an hour apart, and obvious to every reader.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
import statistics as stats

from .. import textio as T
from ..types import NOTE, WARN, CraftReport, Finding, Span
from . import Ctx, check

# ---------------------------------------------------------------------------
# helpers shared with technical.py and fiction.py
# ---------------------------------------------------------------------------


def sentence_spans(ctx: Ctx, sec) -> list[tuple[int, int]]:
    """Absolute sentence spans inside one section's prose."""
    prose = ctx.doc.prose_of_file(sec.path)
    body = prose[sec.body.start:sec.body.end]
    return T.sentences(body, base=sec.body.start)


_NAME = re.compile(r"\b([A-Z][a-z]{2,}(?:['\u2019-][A-Z]?[a-z]+)?)\b")


def detect_cast(ctx: Ctx, minimum: int = 4) -> list[str]:
    """Who is in this book, when the project has not said.

    A name is a capitalised word that appears often and NOT only at the
    start of sentences -- the second half is what keeps `Then`, `However`
    and `Suddenly` out of the cast list, and it costs one comparison.

    Lives in `shared` rather than in `fiction` because `echo` needs it
    too: a character called Aleksandr is SUPPOSED to appear twice in a
    paragraph, and an echo check that does not know the cast trains the
    author to ignore it.
    """
    if ctx.cast:
        return list(ctx.cast)
    counts: Counter = Counter()
    mid_sentence: Counter = Counter()
    for sec in ctx.doc.sections:
        prose = ctx.doc.prose_of_file(sec.path)
        for s, e in sentence_spans(ctx, sec):
            text = prose[s:e]
            for m in _NAME.finditer(text):
                word = m.group(1)
                if T.is_common(word) or len(word) < 3:
                    continue
                counts[word] += 1
                if m.start() > 1:
                    mid_sentence[word] += 1
                    # ONE mid-sentence appearance is enough. The job of
                    # this test is to reject sentence-openers like
                    # "Meanwhile" and "Nevertheless", and those essentially
                    # never appear capitalised mid-sentence; asking for a
                    # third of all mentions instead threw out real names in
                    # any book where a character mostly starts sentences.
    return sorted(
        (name for name, n in counts.items()
         if n >= minimum and mid_sentence[name] >= 1),
        key=lambda n: -counts[n])[:40]


def vocabulary(ctx: Ctx, floor: int) -> set[str]:
    """Stems the document uses often enough to be its VOCABULARY.

    The distinction echo lives or dies on. In a manual, `torque` appearing
    nine times in the torque procedure is the document working correctly;
    in a novel, `sword` is the object the book is about. Neither is an
    echo, and a check that reports them is one the author switches off
    within a day -- taking the real findings with it.
    """
    counts: Counter = Counter()
    for src in ctx.doc.files:
        for word in T.word_list(ctx.doc.prose_of_file(src.rel)):
            key = T.normalise(word).strip("'-")
            counts[_stem(key)] += 1
    return {stem for stem, n in counts.items() if n > floor}


def _stem(key: str) -> str:
    return key[:-1] if key.endswith("s") and len(key) > 5 else key


def describe(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": 0.0, "sd": 0.0, "median": 0.0,
                "p10": 0.0, "p90": 0.0, "min": 0.0, "max": 0.0}
    ordered = sorted(values)

    def pct(p):
        if len(ordered) == 1:
            return float(ordered[0])
        pos = p * (len(ordered) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(ordered) - 1)
        return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo))

    return {"n": len(values), "mean": round(stats.fmean(values), 2),
            "sd": round(stats.pstdev(values), 2) if len(values) > 1 else 0.0,
            "median": round(pct(0.5), 2), "p10": round(pct(0.10), 2),
            "p90": round(pct(0.90), 2), "min": float(min(values)),
            "max": float(max(values))}


# ---------------------------------------------------------------------------
# 1. length distributions
# ---------------------------------------------------------------------------


@check("lengths", "Sentence and paragraph lengths")
def lengths(ctx: Ctx) -> CraftReport:
    """The SHAPE, not just the mean. Rhythm lives in the variance.

    A document whose sentences are all within a few words of each other
    reads flat however good the words are, and no average will show it —
    which is why the coefficient of variation is the number that earns its
    place here and the mean is only along for the ride.
    """
    rep = CraftReport()
    all_lengths: list[float] = []
    per_section: dict[str, dict] = {}
    para_lengths: list[float] = []

    for sec in ctx.doc.sections:
        prose = ctx.doc.prose_of_file(sec.path)
        lens = [len(T.word_list(prose[s:e]))
                for s, e in sentence_spans(ctx, sec)]
        lens = [n for n in lens if n]
        if not lens:
            continue
        all_lengths.extend(lens)
        summary = describe([float(n) for n in lens])
        per_section[sec.id] = summary
        cv = summary["sd"] / summary["mean"] if summary["mean"] else 0.0
        summary["cv"] = round(cv, 3)
        if len(lens) >= 12 and cv < 0.35:
            rep.findings.append(Finding(
                "lengths", WARN,
                f"Flat rhythm in {ctx.doc.label(sec)}",
                f"{len(lens)} sentences averaging {summary['mean']:.0f} "
                f"words with a spread of only {summary['sd']:.1f}. Varying "
                f"sentence length is the cheapest way to fix a section that "
                f"reads competent and dull.",
                span=sec.body, section_id=sec.id,
                data={"cv": round(cv, 3), **summary}))

    for para in ctx.doc.paragraphs():
        n = len(T.word_list(para.text))
        if n:
            para_lengths.append(float(n))

    rep.metrics["sentence_lengths"] = describe(all_lengths)
    rep.metrics["paragraph_lengths"] = describe(para_lengths)
    rep.metrics["sentence_lengths_by_section"] = per_section
    rep.metrics["words"] = int(sum(all_lengths))
    return rep


# ---------------------------------------------------------------------------
# 2. echo
# ---------------------------------------------------------------------------


@check("echo", "Echoes — a distinctive word reused close by")
def echo(ctx: Ctx) -> CraftReport:
    """A distinctive word reused within N words.

    "Distinctive" is doing real work: without it this reports `the` four
    hundred times. A word qualifies when it is outside the common-English
    list, at least five letters, and not a name or term the project told us
    about — a character called Aleksandr is *supposed* to appear twice in a
    paragraph, and flagging that would train the author to ignore the check.
    """
    window = int(ctx.opt("echo_window", 120))
    floor = int(ctx.opt("echo_vocabulary_floor",
                        4 if ctx.document_type == "technical" else 5))
    rep = CraftReport()
    names = {T.normalise(n) for n in (ctx.cast + ctx.terms)}
    if ctx.document_type == "fiction":
        names |= {T.normalise(n) for n in detect_cast(ctx)}
    common_stems = vocabulary(ctx, floor) - {_stem(T.normalise(n))
                                             for n in ctx.terms}
    pairs = 0
    for src in ctx.doc.files:
        prose = ctx.doc.prose_of_file(src.rel)
        last: dict[str, tuple[int, int, int]] = {}
        for i, (start, end, word) in enumerate(T.words(prose)):
            key = T.normalise(word).strip("'-")
            if len(key) < 5 or T.is_common(key) or key in names:
                continue
            stem = _stem(key)
            if stem in common_stems:
                continue
            prev = last.get(stem)
            if prev and i - prev[2] <= window:
                span = Span(src.rel, prev[0], end)
                rep.findings.append(Finding(
                    "echo", WARN, f"“{word}” twice within "
                    f"{i - prev[2]} words",
                    "Reuse of a distinctive word close together. Usually "
                    "invisible to the writer and audible to the reader.",
                    span=span, section_id=_section_id(ctx, src.rel, start),
                    evidence=[ctx.doc.quote(Span(src.rel, prev[0], prev[1])),
                              ctx.doc.quote(Span(src.rel, start, end))],
                    data={"word": word, "distance": i - prev[2]}))
                pairs += 1
            last[stem] = (start, end, i)
    rep.metrics["echo_pairs"] = pairs
    return rep


def _section_id(ctx: Ctx, rel: str, pos: int) -> str:
    sec = ctx.doc.section_at(Span(rel, pos, pos + 1))
    return sec.id if sec else ""


# ---------------------------------------------------------------------------
# 3. readability
# ---------------------------------------------------------------------------


@check("readability", "Readability (a proxy, and stated as one)")
def readability(ctx: Ctx) -> CraftReport:
    """Flesch Reading Ease and Flesch–Kincaid grade, per section.

    Stated as a proxy because that is what it is: both formulas are two
    ratios and a syllable heuristic, they know nothing about whether a
    sentence is clear, and a technical author can lower the grade by
    chopping a good sentence in half. Reported as NOTE for that reason —
    a number to look at, never a defect.
    """
    rep = CraftReport()
    target = ctx.opt("target_grade", 0)
    rows = {}
    grades = []
    for sec in ctx.doc.sections:
        prose = ctx.doc.prose_of_file(sec.path)
        spans = sentence_spans(ctx, sec)
        words_all = []
        for s, e in spans:
            words_all.extend(T.word_list(prose[s:e]))
        if len(words_all) < 40 or not spans:
            continue
        syl = sum(T.syllables(w) for w in words_all)
        wps = len(words_all) / len(spans)
        spw = syl / len(words_all)
        ease = 206.835 - 1.015 * wps - 84.6 * spw
        grade = 0.39 * wps + 11.8 * spw - 15.59
        polysyll = sum(1 for w in words_all if T.syllables(w) >= 3)
        fog = 0.4 * (wps + 100 * polysyll / len(words_all))
        rows[sec.id] = {"ease": round(ease, 1), "grade": round(grade, 1),
                        "fog": round(fog, 1), "words": len(words_all)}
        grades.append(grade)
        if target and grade > float(target) + 2:
            rep.findings.append(Finding(
                "readability", NOTE,
                f"{ctx.doc.label(sec)} reads at grade {grade:.0f}",
                f"The project's target is grade {target}. This is a proxy: "
                f"it counts words per sentence and syllables per word and "
                f"nothing else. Long sentences and long technical terms "
                f"both raise it, and only one of those is a problem.",
                span=sec.body, section_id=sec.id, data=rows[sec.id]))
    rep.metrics["readability_by_section"] = rows
    rep.metrics["readability"] = describe(grades)
    return rep


# ---------------------------------------------------------------------------
# 4. filter words and adverbs
# ---------------------------------------------------------------------------

FILTER_WORDS = {
    "felt", "feel", "feels", "saw", "see", "sees", "watched", "watch",
    "heard", "hear", "hears", "noticed", "notice", "realised", "realized",
    "realise", "realize", "thought", "think", "wondered", "wonder",
    "decided", "knew", "know", "remembered", "remember", "seemed", "seem",
    "seems", "appeared", "appears", "looked", "began", "begin", "begins",
    "started", "start", "starts", "tried", "try", "tries", "managed",
    "found", "considered", "observed", "sensed", "experienced",
}

#: `\w{4,}ly` needed SIX letters, not four: the quantifier runs
#: BEFORE the literal "ly", so "badly", "sadly", "aptly" and
#: "wryly" were never adverbs as far as this package was concerned.
#: Two letters plus "ly" is the rule that was meant.
_LY = re.compile(r"\b[a-z]{2,}ly\b", re.I)
_LY_KEEP = {"only", "early", "family", "reply", "supply", "apply", "likely",
            "lonely", "holy", "italy", "ugly", "silly", "daily", "weekly",
            "monthly", "yearly", "friendly", "lovely", "assembly"}


@check("filter_words", "Filter words and adverbs")
def filter_words(ctx: Ctx) -> CraftReport:
    """Counted, not opined about.

    The craft advice about filter words is real and it is also overstated;
    what a tool can honestly contribute is the RATE, per section, against
    the rest of the document. "This section uses them at three times your
    own average" is a fact. "Delete every 'felt'" is a fashion.
    """
    rep = CraftReport()
    per_section = {}
    totals = Counter()
    doc_words = 0
    for sec in ctx.doc.sections:
        prose = ctx.doc.prose(sec)
        toks = [T.normalise(w) for w in T.word_list(prose)]
        if len(toks) < 60:
            continue
        filt = sum(1 for w in toks if w in FILTER_WORDS)
        adv = sum(1 for w in toks
                  if _LY.fullmatch(w) and w not in _LY_KEEP)
        per_section[sec.id] = {
            "words": len(toks),
            "filter_per_1000": round(1000 * filt / len(toks), 1),
            "adverbs_per_1000": round(1000 * adv / len(toks), 1)}
        totals["filter"] += filt
        totals["adverb"] += adv
        doc_words += len(toks)
    if doc_words:
        base = 1000 * totals["filter"] / doc_words
        for sid, row in per_section.items():
            if row["filter_per_1000"] > max(6.0, base * 2.5):
                sec = ctx.doc.section(sid)
                rep.findings.append(Finding(
                    "filter_words", WARN,
                    f"Filter words concentrated in {ctx.doc.label(sec)}",
                    f"{row['filter_per_1000']:.1f} per 1000 words against "
                    f"{base:.1f} across the document. Filter words put the "
                    f"viewpoint between the reader and the event: 'she saw "
                    f"the door open' rather than 'the door opened'.",
                    span=sec.body if sec else None, section_id=sid,
                    data=row))
        rep.metrics["filter_per_1000"] = round(base, 2)
        rep.metrics["adverbs_per_1000"] = round(
            1000 * totals["adverb"] / doc_words, 2)
    rep.metrics["filter_by_section"] = per_section
    return rep


# ---------------------------------------------------------------------------
# 5. passive voice
# ---------------------------------------------------------------------------

BE = {"am", "is", "are", "was", "were", "be", "been", "being", "get",
      "gets", "got", "gotten"}

IRREGULAR = {
    "been", "begun", "broken", "brought", "built", "bought", "caught",
    "chosen", "come", "cut", "done", "drawn", "driven", "eaten", "fallen",
    "felt", "found", "given", "gone", "grown", "held", "hidden", "hit",
    "kept", "known", "laid", "led", "left", "lost", "made", "meant", "met",
    "paid", "put", "read", "run", "said", "seen", "sent", "set", "shown",
    "shut", "sold", "spoken", "spent", "split", "stood", "struck", "taken",
    "taught", "told", "thought", "thrown", "understood", "worn", "won",
    "written", "drawn", "torn", "born", "beaten", "bound", "cast", "dealt",
    "fed", "fit", "hurt", "lit", "proven", "rung", "sung", "sunk", "sworn",
}

_NOT_PARTICIPLE = {"need", "indeed", "embed", "exceed", "speed", "breed",
                   "seed", "deed", "feed", "bed", "red", "shed", "wed"}


def _is_participle(word: str) -> bool:
    w = T.normalise(word)
    if w in IRREGULAR:
        return True
    if len(w) > 4 and w.endswith("ed") and w not in _NOT_PARTICIPLE:
        return True
    return False


@check("passive", "Passive voice rate")
def passive(ctx: Ctx) -> CraftReport:
    """A be-verb plus a past participle, with an adverb allowed between.

    Heuristic, and honest about it: with no part-of-speech tagger this
    catches "was tightened" and also "was tired", and it cannot tell a
    deliberate passive ("the bolt shall be torqued to 40 Nm", which is
    correct in a specification) from a limp one. Hence a RATE per section
    rather than a flag per sentence.
    """
    rep = CraftReport()
    per_section = {}
    hits_total = 0
    sent_total = 0
    for sec in ctx.doc.sections:
        prose = ctx.doc.prose_of_file(sec.path)
        spans = sentence_spans(ctx, sec)
        if len(spans) < 5:
            continue
        hits = 0
        for s, e in spans:
            toks = T.word_list(prose[s:e])
            for i, w in enumerate(toks[:-1]):
                if T.normalise(w) not in BE:
                    continue
                nxt = toks[i + 1]
                if _LY.fullmatch(T.normalise(nxt)) and i + 2 < len(toks):
                    nxt = toks[i + 2]
                if _is_participle(nxt):
                    hits += 1
                    break
        per_section[sec.id] = {"sentences": len(spans), "passive": hits,
                               "rate": round(hits / len(spans), 3)}
        hits_total += hits
        sent_total += len(spans)
    if sent_total:
        rep.metrics["passive_rate"] = round(hits_total / sent_total, 3)
    rep.metrics["passive_by_section"] = per_section
    return rep


# ---------------------------------------------------------------------------
# 6. opening variety
# ---------------------------------------------------------------------------


@check("openers", "Sentence openings")
def openers(ctx: Ctx) -> CraftReport:
    """How many consecutive sentences start `The`, `He`, `It`.

    Three in a row is a tic the writer cannot hear and the reader cannot
    unhear. Counted per section so a deliberate anaphora — three sentences
    opening the same way ON PURPOSE — shows up as one finding to dismiss
    rather than as a scattering.
    """
    run_min = int(ctx.opt("opener_run", 3))
    rep = CraftReport()
    counts = Counter()
    for sec in ctx.doc.sections:
        prose = ctx.doc.prose_of_file(sec.path)
        spans = sentence_spans(ctx, sec)
        run: list[tuple[int, int]] = []
        current = ""
        for s, e in spans:
            toks = T.word_list(prose[s:e])
            first = T.normalise(toks[0]) if toks else ""
            counts[first] += 1
            if first and first == current:
                run.append((s, e))
            else:
                _flush_run(ctx, rep, sec, run, current, run_min)
                current = first
                run = [(s, e)]
        _flush_run(ctx, rep, sec, run, current, run_min)
    rep.metrics["openers"] = dict(counts.most_common(20))
    total = sum(counts.values()) or 1
    rep.metrics["opener_variety"] = round(len(counts) / total, 3)
    return rep


def _flush_run(ctx, rep, sec, run, word, run_min) -> None:
    if len(run) < run_min or not word:
        return
    prose = ctx.doc.prose_of_file(sec.path)
    rep.findings.append(Finding(
        "openers", WARN,
        f"{len(run)} sentences in a row open with “{word}”",
        "Openings are the most repetitive part of most drafts and the "
        "easiest to vary.",
        span=Span(sec.path, run[0][0], run[-1][1]), section_id=sec.id,
        evidence=[" ".join(prose[s:e].split())[:110] for s, e in run[:3]],
        data={"word": word, "run": len(run)}))


# ---------------------------------------------------------------------------
# 7. repeated sentence openings across the whole document
# ---------------------------------------------------------------------------


@check("stock_phrases", "Repeated phrases")
def stock_phrases(ctx: Ctx) -> CraftReport:
    """Four-word phrases the document repeats.

    In a manual this is usually correct and worth confirming — a procedure
    SHOULD say "tighten to the specified torque" the same way every time.
    In a novel the same measurement finds the sentence the author has
    written eleven times without noticing. Same arithmetic, opposite
    reading, so it is reported as a NOTE with the count and left to the
    author.
    """
    rep = CraftReport()
    grams: defaultdict[str, list[Span]] = defaultdict(list)
    for src in ctx.doc.files:
        prose = ctx.doc.prose_of_file(src.rel)
        toks = T.words(prose)
        for i in range(len(toks) - 3):
            window = toks[i:i + 4]
            if all(T.is_common(w[2]) for w in window):
                continue
            key = " ".join(T.normalise(w[2]) for w in window)
            grams[key].append(Span(src.rel, window[0][0], window[-1][1]))
    threshold = int(ctx.opt("phrase_min", 4))
    rows = []
    for key, spans in grams.items():
        if len(spans) < threshold:
            continue
        rows.append((len(spans), key))
        rep.findings.append(Finding(
            "stock_phrases", NOTE,
            f"“{key}” appears {len(spans)} times",
            "Deliberate in a procedure, a tic in a narrative. The tool "
            "cannot tell which, and does not guess.",
            span=spans[0], section_id=_section_id(ctx, spans[0].path,
                                                  spans[0].start),
            evidence=[ctx.doc.quote(s) for s in spans[:3]],
            data={"phrase": key, "count": len(spans)}))
    rep.metrics["repeated_phrases"] = sorted(rows, reverse=True)[:20]
    return rep
