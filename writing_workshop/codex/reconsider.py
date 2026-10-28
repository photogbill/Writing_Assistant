# SPDX-License-Identifier: Apache-2.0
"""Reconsider: what did I write that depended on the old fact?

The one question a writer actually asks and no writing tool answers. Not
"find mentions of the sword" — *"you changed the sword to steel in chapter
17; here are four passages that describe it as bronze, and one that turns
on the sound it makes when it is struck."*

The first four are arithmetic and are found here. The fifth needs a model
and is offered as a CANDIDATE with the passage quoted, because a tool that
silently rewrote it would be doing the author's job badly.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from .. import textio as T
from ..types import Span
from ..units import NUM_UNIT, dimension, interval, split_value

#: A passage that names the subject AND still carries the old value.
DIRECT = 3
#: Names the subject, and sits in a section where the old value appears.
NEARBY = 2
#: Names the subject. Worth a look, nothing more.
MENTION = 1


@dataclass
class Dependent:
    span: Span
    quote: str
    strength: int
    why: str
    section_id: str = ""
    section_label: str = ""

    @property
    def certain(self) -> bool:
        return self.strength >= DIRECT


#: Function words a value's own words are matched WITHOUT. Deliberately
#: tiny: the common-English list used to be applied here, and it holds
#: gold, red, black, white, old, new, lead, short and young — exactly the
#: values the extractor emits — so "still gold under the dust" could never
#: be found as a passage carrying the old value.
_FUNCTION_WORDS = {"the", "and", "for", "with", "from", "that", "this",
                   "its", "his", "her", "their", "was", "are", "is"}


def _value_tokens(value: str) -> list[str]:
    return [T.normalise(w) for w in T.word_list(value)
            if len(w) > 2 and T.normalise(w) not in _FUNCTION_WORDS]


def _mentions_value(text: str, value: str) -> bool:
    """Does this passage still carry the old value?

    Numbers are compared at the PRECISION EACH WAS WRITTEN TO, the same
    model the units check uses — so a passage saying `29.5 lb-ft` counts
    as carrying `40 Nm`, which is the whole point: that is exactly the
    passage a reader would find contradictory and a substring search would
    miss. It is also the second place an exact-equality test got this
    wrong, which is why the arithmetic lives in one module now.
    """
    raw, unit = split_value(value)
    if raw:
        target = interval(raw, unit)
        if target is None:
            return False
        want = dimension(unit)
        for m in NUM_UNIT.finditer(text):
            found = m.group("unit")
            #: SAME DIMENSION, or it is not the old value at all. A torque
            #: of 40 Nm used to make "rated for 40 kg" and "after 40 s"
            #: CERTAIN dependents — a number is not a quantity without its
            #: unit. Temperatures, which do not convert, need the same unit.
            if dimension(found) != want:
                continue
            if want == "temperature" and found.lower() != unit.lower():
                continue
            other = interval(m.group("num"), found)
            if other is None:
                continue
            if not (other[1] < target[0] or target[1] < other[0]):
                return True
        return False
    tokens = _value_tokens(value)
    if not tokens:
        return False
    lowered = [T.normalise(w) for w in T.word_list(text)]
    return any(tok in lowered for tok in tokens)


def find(doc, subject: str, old_value: str, *, exclude: Span | None = None,
         limit: int = 50) -> list[Dependent]:
    """Passages that may depend on `subject` having been `old_value`."""
    hits = doc.find(subject)
    if not hits:
        return []
    by_section: dict[str, bool] = {}
    out: list[Dependent] = []
    seen: set[tuple[str, int]] = set()

    for span in hits:
        sec = doc.section_at(span)
        sid = sec.id if sec else ""
        para = _paragraph_at(doc, span)
        if para is None:
            continue
        key = (para.span.path, para.span.start)
        if key in seen:
            continue
        seen.add(key)
        if exclude is not None and para.span.overlaps(exclude):
            continue
        if sid not in by_section:
            by_section[sid] = bool(sec) and _mentions_value(
                doc.prose(sec), old_value)
        if _mentions_value(para.text, old_value):
            strength, why = DIRECT, (
                f"names {subject} and still carries “{old_value}”")
        elif by_section.get(sid):
            strength, why = NEARBY, (
                f"names {subject}; “{old_value}” appears in the same "
                f"section")
        else:
            strength, why = MENTION, f"names {subject}"
        out.append(Dependent(
            span=para.span, quote=" ".join(para.text.split())[:400],
            strength=strength, why=why, section_id=sid,
            section_label=doc.label(sec) if sec else ""))
    out.sort(key=lambda d: (-d.strength, d.span.path, d.span.start))
    return out[:limit]


def _paragraph_at(doc, span: Span):
    sec = doc.section_at(span)
    for para in doc.paragraphs(sec):
        if para.span.path == span.path and (
                para.span.start <= span.start < para.span.end):
            return para
    return None


def for_claim(doc, claim, superseded_by=None) -> list[Dependent]:
    """`reconsider` for a claim the author has just superseded."""
    exclude = superseded_by.span if superseded_by is not None else None
    return find(doc, claim.subject, claim.value, exclude=exclude)


PROMPT = """You are checking one passage against a fact that has CHANGED.

The fact: {subject} — {predicate} was “{old}”, and is now “{new}”.

The passage:
{passage}

Answer with one line. If nothing in the passage depends on the old value,
answer exactly: NO. Otherwise answer: YES — <the clause that depends on it>.
Do not rewrite the passage. Do not explain."""


def ask_model(host, claim, new_value: str, dependent: Dependent,
              cancel=None) -> str:
    """The fifth passage — the one that turns on the SOUND the sword makes.

    Deterministic search cannot find it: nothing in that sentence contains
    the word "bronze". A model can, and its answer is a CANDIDATE quoted
    back to the author, never an edit. Returns "" when the model declines
    or is not loaded.
    """
    from ..errors import NoModelError
    from ..ports import NEVER
    try:
        reply = host.llm.complete(
            "You are a precise continuity checker. You never rewrite text.",
            PROMPT.format(subject=claim.subject, predicate=claim.predicate,
                          old=claim.value, new=new_value,
                          passage=dependent.quote),
            temperature=0.0, max_tokens=120, cancel=cancel or NEVER)
    except NoModelError:
        return ""
    except Exception:                                # noqa: BLE001
        return ""
    reply = (reply or "").strip()
    if re.match(r"no\b", reply, re.I):
        return ""
    #: `lstrip("YES")` strips CHARACTERS, not a word: "Yes — the blade
    #: rang" came back as "es — the blade rang".
    return re.sub(r"^\s*yes\b[\s—–:\-]*", "", reply, flags=re.I).strip()
