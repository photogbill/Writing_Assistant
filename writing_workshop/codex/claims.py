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
from ..types import ATTRIBUTE, NUMERIC, RELATIONSHIP, TEMPORAL, Claim, Span
from ..units import dimension as _dimension, split_value, to_base

_NUM = re.compile(r"(?<![\w.])(-?\d[\d,]*(?:\.\d+)?)\s*([A-Za-z°·µ/%]{1,12})?")

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")

_IS = re.compile(
    r"\b(?P<subj>[A-Z][\w' -]{1,40}?)\s+(?:is|was|are|were)\s+"
    r"(?P<art>the\s+|a\s+|an\s+)?(?P<val>[a-z][\w -]{1,40}?)\b"
    r"(?=[.,;:]|\s+(?:and|but|which|who|when)\b|$)")
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
#: The two the original list left out, and the argument for adding them.
#: Material and colour are where the CLASSIC continuity error lives --
#: bronze in chapter 3 and steel in chapter 17 -- and the case for keeping
#: the net narrow was that a broad one fills the Codex with candidates the
#: author has to dismiss one at a time. That cost has changed: a finding
#: can now be dismissed ONCE and stay dismissed (`writing_workshop.
#: findings`), so a slightly wider net is affordable where it was not.
#:
#: Size and age are the next two places the error actually lives -- the
#: tall guard who is short a hundred pages later, the new housing that was
#: ageing in §2 -- and both remain a CLOSED list rather than "any
#: adjective", which is the property that made the original narrow.
SIZES = {
    "small", "large", "big", "huge", "tiny", "enormous", "vast",
    "narrow", "wide", "tall", "short", "thick", "thin", "slender",
    "massive", "immense", "compact", "miniature",
}
AGES = {
    "old", "new", "young", "ancient", "elderly", "modern", "antique",
    "aged", "brand-new", "newborn", "middle-aged", "venerable",
}
_ADJ_PREDICATE = {**dict.fromkeys(MATERIALS, "material"),
                  **dict.fromkeys(COLOURS, "colour"),
                  **dict.fromkeys(SIZES, "size"),
                  **dict.fromkeys(AGES, "age")}


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
    return _dimension(unit)


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
    """Every stated quantity in the document, named by what it is OF.

    No model, and no guessing: a number with no quantity word near it (and
    no imperative naming what it is set on) is skipped rather than attached
    to whatever noun was closest.

    THE SUBJECT IS THE OBJECT, THE PREDICATE THE QUANTITY (2026-10-28):
    "The torque for the lid bolts is 40 Nm" is `lid bolts: torque = 40 Nm`,
    and "Tighten the wheel nuts to 110 Nm" is `wheel nuts: torque = 110 Nm`.
    It used to be `torque: value = …` for both, so every torque in a manual
    shared one key and N different specs made N(N−1)/2 "certain"
    contradictions. A quantity nothing names stays `torque: value = …` and
    is compared only within its own section — see `contradictions`.
    """
    from ..units import quantities
    extra = {T.normalise(t) for t in (terms or [])}
    out: list[Claim] = []
    for src in doc.files:
        prose = doc.prose_of_file(src.rel)
        for q in quantities(prose, extra):
            span = Span(src.rel, q.start, q.end)
            sec = doc.section_at(span)
            out.append(make(
                q.subject, q.predicate, q.text, kind=NUMERIC, span=span,
                source_ref=_ref(doc, span), quote=doc.quote(span),
                section_id=sec.id if sec else "", origin="measured"))
    return out


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
        for surface in wanted.values():
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
            subj = _wanted_at_end(T.normalise(m.group("subj")), wanted)
            if subj is None:
                continue
            value = m.group("val").strip()
            #: FILED UNDER THE SAME PREDICATE AS THE ADJECTIVE FORM
            #: (2026-10-28). "Excalibur was bronze" used to be predicate
            #: "is" while "the steel Excalibur" was "material", so the
            #: headline case of this whole package never met itself. And
            #: ANY lowercase phrase counted: "Mira was tired", "happy", "in
            #: the kitchen" made six candidate conflicts about one woman's
            #: afternoon. A value is kept when it is a known attribute word
            #: (material, colour, size, age) or an identity introduced by
            #: an article ("Mira is a soldier"); states are not facts.
            predicate = _ADJ_PREDICATE.get(T.normalise(value))
            if predicate is None:
                if not m.group("art") or (T.is_common(value)
                                          and len(value) < 5):
                    continue
                predicate = "is"
            span = Span(src.rel, m.start(), m.end())
            sec = doc.section_at(span)
            out.append(make(wanted[subj], predicate, value, kind=ATTRIBUTE,
                            span=span, source_ref=_ref(doc, span),
                            quote=doc.quote(span),
                            section_id=sec.id if sec else "",
                            origin="measured"))
    return out


def _wanted_at_end(subject: str, wanted: dict) -> str | None:
    """The known subject a captured phrase ENDS with: "Yesterday Mira" is
    Mira, "The sword" is the sword. Whole words only."""
    if subject in wanted:
        return subject
    for key in wanted:
        if subject.endswith(" " + key):
            return key
    return None


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
