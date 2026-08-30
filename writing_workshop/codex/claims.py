# SPDX-License-Identifier: Apache-2.0
"""Claims: what the document asserts about its own world.

A story bible IS an evidence ledger, and ATK already owns the machine.
O.W.L. records observations with the passage they came from, tracks what
superseded what, and answers "what decisions are standing on something that
turned out to be wrong". Rename the nouns and that is a continuity system:

    observation      a claim about the world of the document
    source_ref       the chapter and paragraph it was asserted in
    supersession     the fact changed -- the sword became steel
    reconsider       WHAT DID I WRITE THAT DEPENDED ON THE OLD FACT?

That last row is the feature no writing tool has and every writer wants.
Not "find mentions of the sword" — "you changed the sword to steel in
chapter 17; here are four passages that describe it as bronze, and one
that turns on the sound it makes when it is struck."

Claims are TYPED because different types are checkable differently, and
the numeric case is deterministic and the most valuable one in a manual.
"""

from __future__ import annotations

import re

from .. import textio as T
from ..units import UNITS, split_value, to_base
from ..types import (ATTRIBUTE, NUMERIC, RELATIONSHIP, TEMPORAL, Claim,
                     Span)

_NUM = re.compile(r"(?<![\w.])(-?\d[\d,]*(?:\.\d+)?)\s*([A-Za-z°·µ/%]{1,12})?")

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")

_IS = re.compile(
    r"\b(?P<subj>[A-Z][\w' -]{1,40}?)\s+(?:is|was|are|were)\s+"
    r"(?:the\s+|a\s+|an\s+)?(?P<val>[a-z][\w -]{1,40}?)\b(?=[.,;:]|\s+(?:and|but|which|who|when)\b|$)")
_REL = re.compile(
    r"\b(?P<a>[A-Z][\w'-]{1,25})(?:'s|’s)\s+(?P<rel>brother|sister|"
    r"mother|father|son|daughter|wife|husband|cousin|uncle|aunt|partner|"
    r"friend|master|apprentice|captain|commander)\b")
_REL2 = re.compile(
    r"\b(?P<a>[A-Z][\w'-]{1,25})\s+(?:is|was)\s+(?P<rel>[A-Z][\w'-]{1,25})"
    r"(?:'s|’s)\s+(?P<kind>brother|sister|mother|father|son|daughter|"
    r"wife|husband|cousin|uncle|aunt|partner)\b")


#: The adjectives a continuity error actually turns on. Restricted on
#: purpose: run over every adjective, "the old sword" and "the long sword"
#: become attribute claims that CONFLICT with "the bronze sword", and the
#: Codex fills with candidates the author has to dismiss one at a time.
#: Material and colour are where this class of error lives -- bronze in
#: chapter 3 and steel in chapter 17 -- and a narrow check that is right
#: beats a broad one that is noisy.
MATERIALS = {
    "bronze", "steel", "iron", "wooden", "wood", "oak", "ash", "copper",
    "brass", "silver", "gold", "golden", "aluminium", "aluminum", "tin",
    "lead", "nickel", "titanium", "plastic", "glass", "leather", "stone",
    "granite", "marble", "ceramic", "rubber", "carbon", "composite",
    "alloy", "canvas", "linen", "silk", "wool", "cotton", "paper", "clay",
}
COLOURS = {
    "black", "white", "red", "green", "blue", "yellow", "brown", "grey",
    "gray", "purple", "orange", "pink", "crimson", "scarlet", "amber",
    "auburn", "blonde", "blond", "chestnut", "hazel", "violet", "ivory",
}
_ADJ_PREDICATE = {**{w: "material" for w in MATERIALS},
                  **{w: "colour" for w in COLOURS}}


def parse_number(text: str) -> tuple[float | None, str]:
    """`40 Nm` -> (40.0, 'nm'). Returns (None, '') when there is no
    number. The raw text is kept by the caller, because how a number was
    WRITTEN carries its precision -- see `writing_workshop.units`."""
    raw, unit = split_value(text)
    if not raw:
        return None, ""
    try:
        return float(raw.replace(",", "")), unit
    except ValueError:
        return None, ""


def base_value(number: float | None, unit: str) -> float | None:
    """Normalise to the dimension's base unit."""
    return to_base(number, unit)


def dimension(unit: str) -> str:
    return UNITS[unit][0] if unit in UNITS else ""


def make(subject: str, predicate: str, value: str, *, kind: str = ATTRIBUTE,
         span: Span | None = None, source_ref: str = "",
         section_id: str = "", quote: str = "", origin: str = "author",
         note: str = "") -> Claim:
    """Build a claim, parsing a number out of the value when there is one.

    Every claim arrives PROPOSED. There is deliberately no way to construct
    an accepted one: acceptance is an act by the author, and a constructor
    that could skip it is a Codex that fills itself.
    """
    number, unit = parse_number(value) if kind in (NUMERIC, ATTRIBUTE) else (
        None, "")
    if number is not None and kind == ATTRIBUTE:
        kind = NUMERIC
    return Claim(subject=subject.strip(), kind=kind,
                 predicate=predicate.strip(), value=value.strip(),
                 unit=unit, number=number, source_ref=source_ref,
                 section_id=section_id, span=span, quote=quote,
                 origin=origin, note=note)


# ---------------------------------------------------------------------------
# deterministic extraction
# ---------------------------------------------------------------------------


def numeric_claims(doc, terms: list[str] | None = None) -> list[Claim]:
    """Every "<named quantity> is <number> <unit>" in the document.

    No model, and no guessing: a number with no quantity word near it is
    skipped rather than attached to whatever noun was closest. Inventing
    the subject is how a continuity report fills with conflicts that are
    really parser noise, and one of those costs more trust than ten real
    findings buy.
    """
    from ..units import NUM_UNIT, QUANTITY_WORDS
    extra = {T.normalise(t) for t in (terms or [])}
    out: list[Claim] = []
    for src in doc.files:
        prose = doc.prose_of_file(src.rel)
        for m in NUM_UNIT.finditer(prose):
            subject = _quantity_near(prose, m.start(), QUANTITY_WORDS, extra)
            if not subject:
                continue
            span = Span(src.rel, m.start(), m.end())
            sec = doc.section_at(span)
            out.append(make(
                subject, "value", m.group(0), kind=NUMERIC, span=span,
                source_ref=_ref(doc, span), quote=doc.quote(span),
                section_id=sec.id if sec else "", origin="measured"))
    return out


def _quantity_near(prose: str, at: int, quantity_words, extra) -> str:
    before = [T.normalise(w) for w in T.word_list(prose[max(0, at - 60):at])]
    for word in reversed(before[-6:]):
        if word in quantity_words or word in extra:
            return word
    after = [T.normalise(w) for w in T.word_list(prose[at:at + 60])][:5]
    for word in after:
        if word in quantity_words or word in extra:
            return word
    return ""


def temporal_claims(doc) -> list[Claim]:
    """Named events pinned to a weekday, a date or a duration."""
    out: list[Claim] = []
    pattern = re.compile(
        r"\b(?P<subj>[A-Za-z][\w' -]{2,30}?)\s+(?:is|was|will be|takes|"
        r"took|happens|happened|falls|fell)\s+(?:on\s+|in\s+|at\s+)?"
        r"(?P<when>" + "|".join(_WEEKDAYS + _MONTHS) +
        r"|\d{1,2}\s*(?:minutes|minute|hours|hour|days|day|weeks|week)"
        r"|\d{4}-\d{2}-\d{2})\b", re.I)
    for src in doc.files:
        prose = doc.prose_of_file(src.rel)
        for m in pattern.finditer(prose):
            subject = m.group("subj").strip()
            if T.is_common(subject) or len(subject) < 3:
                continue
            span = Span(src.rel, m.start(), m.end())
            sec = doc.section_at(span)
            out.append(make(subject, "when", m.group("when"), kind=TEMPORAL,
                            span=span, source_ref=_ref(doc, span),
                            quote=doc.quote(span),
                            section_id=sec.id if sec else "",
                            origin="measured"))
    return out


def attribute_claims(doc, subjects: list[str]) -> list[Claim]:
    """`<Subject> is <adjective/noun>`, for subjects we were told about.

    Restricted to known subjects on purpose. Run over every capitalised
    word in a novel this produces hundreds of readings, most of them
    wrong, and a Codex is only as good as the proportion of it the author
    is willing to read.
    """
    if not subjects:
        return []
    wanted = {T.normalise(s): s for s in subjects}
    out: list[Claim] = []
    for src in doc.files:
        prose = doc.prose_of_file(src.rel)
        for subj_norm, surface in wanted.items():
            rx = re.compile(
                r"\b(?:the|a|an|his|her|their|its|my|your|that|this)\s+"
                r"([a-z]{3,12})\s+" + re.escape(surface) + r"\b", re.I)
            for m in rx.finditer(prose):
                adjective = T.normalise(m.group(1))
                predicate = _ADJ_PREDICATE.get(adjective)
                if not predicate:
                    continue
                span = Span(src.rel, m.start(), m.end())
                sec = doc.section_at(span)
                out.append(make(surface, predicate, adjective,
                                kind=ATTRIBUTE, span=span,
                                source_ref=_ref(doc, span),
                                quote=doc.quote(span),
                                section_id=sec.id if sec else "",
                                origin="measured"))
        for m in _IS.finditer(prose):
            subj = T.normalise(m.group("subj"))
            if subj not in wanted:
                continue
            value = m.group("val").strip()
            if T.is_common(value) and len(value) < 5:
                continue
            span = Span(src.rel, m.start(), m.end())
            sec = doc.section_at(span)
            out.append(make(wanted[subj], "is", value, kind=ATTRIBUTE,
                            span=span, source_ref=_ref(doc, span),
                            quote=doc.quote(span),
                            section_id=sec.id if sec else "",
                            origin="measured"))
    return out


def relationship_claims(doc) -> list[Claim]:
    out: list[Claim] = []
    for src in doc.files:
        prose = doc.prose_of_file(src.rel)
        for m in _REL2.finditer(prose):
            span = Span(src.rel, m.start(), m.end())
            sec = doc.section_at(span)
            out.append(make(m.group("a"), m.group("kind") + " of",
                            m.group("rel"), kind=RELATIONSHIP, span=span,
                            source_ref=_ref(doc, span),
                            quote=doc.quote(span),
                            section_id=sec.id if sec else "",
                            origin="measured"))
    return out


def _ref(doc, span: Span) -> str:
    """`§4.2 Servicing · para 3` — the author's own numbering when it has
    one, because a reference to a number the reader cannot see is a
    reference this tool invented."""
    sec = doc.section_at(span)
    if not sec:
        return span.path
    label = doc.label(sec)
    index = 1
    for para in doc.paragraphs(sec):
        if para.span.start <= span.start < para.span.end:
            index = para.index + 1
            break
    return f"{label} · para {index}"
