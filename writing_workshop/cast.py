# SPDX-License-Identifier: Apache-2.0
"""Who is in this book, when the project has not said.

Lived in `craft.shared` until the Codex needed it too, and it needed it
badly: `codex.deterministic()` ran `attribute_claims` only when it was
handed a list of subjects, and the CLI handed it `project.cast or None`.
An author who had not typed a cast list therefore got **zero** attribute
claims — measured, on a 155,000-word novel — so contradiction detection
had nothing to compare and the Continuity page was emptiest on exactly
the document type it was built for.

The detection itself is unchanged and its one clever part is worth
restating: a name is a capitalised word that appears often and **not only
at the start of sentences**. That second half is what keeps `Then`,
`However` and `Suddenly` out of the cast list, and it costs one
comparison.

A detected cast is a PROPOSAL like everything else here. `deterministic()`
uses it to read claims, and every claim it reads arrives `proposed` — the
author still decides who is a character.
"""

from __future__ import annotations

from collections import Counter
import re

from . import textio as T

_NAME = re.compile(r"\b([A-Z][a-z]{2,}(?:['’-][A-Z]?[a-z]+)?)\b")

#: The calendar. Capitalised, used mid-sentence, and frequent — everything
#: the detector asks of a name — so on a 150,000-word book "Tuesday",
#: "Thursday", "Monday" and "Friday" were all proposed as characters.
#: Several are also real names (April, June, May, August), so they are
#: not simply refused: a calendar word is a name only when MOST of its
#: uses are not calendar uses — see `calendar_use`.
CALENDAR = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "christmas", "easter", "midsummer", "michaelmas", "lent", "advent",
}

#: What comes before a date and not before a person.
_CAL_BEFORE = {"in", "on", "of", "since", "until", "till", "by", "last",
               "next", "early", "late", "mid", "every", "this", "that",
               "each", "from", "through", "during", "before", "after",
               "come", "one", "a", "the"}

#: A name has to appear this often before it is worth proposing.
MINIMUM = 4

#: How many names to propose. A cast list nobody reads is a cast list that
#: hides the one dropped character who mattered.
LIMIT = 40


def calendar_use(text: str, start: int, end: int) -> bool:
    """Is the calendar word at `text[start:end]` being used as a DATE?
    "On Tuesday", "in April", "Tuesday 4th", "April 3" — yes. "April
    said", "June laughed" — no."""
    before = re.findall(r"[A-Za-z]+", text[max(0, start - 20):start])
    if before and before[-1].lower() in _CAL_BEFORE:
        return True
    return bool(re.match(r"\s*(?:\d|the\s+\d|morning|afternoon|evening|"
                         r"night|week|next|last)", text[end:end + 16], re.I))


def detect(doc, minimum: int = MINIMUM, limit: int = LIMIT) -> list[str]:
    """Proper names that behave like a cast, commonest first."""
    counts: Counter = Counter()
    mid_sentence: Counter = Counter()
    as_date: Counter = Counter()
    for sec in doc.sections:
        prose = doc.prose_of_file(sec.path)
        body = prose[sec.body.start:sec.body.end]
        for s, e in T.sentences(body):
            text = body[s:e]
            for m in _NAME.finditer(text):
                word = m.group(1)
                if T.is_common(word) or len(word) < 3:
                    continue
                counts[word] += 1
                if word.lower() in CALENDAR and calendar_use(
                        text, m.start(1), m.end(1)):
                    as_date[word] += 1
                if m.start() > 1:
                    mid_sentence[word] += 1
                    # ONE mid-sentence appearance is enough. The job of
                    # this test is to reject sentence-openers like
                    # "Meanwhile" and "Nevertheless", and those
                    # essentially never appear capitalised mid-sentence;
                    # asking for a third of all mentions instead threw
                    # out real names in any book where a character mostly
                    # starts sentences.
    return sorted(
        (name for name, n in counts.items()
         if n >= minimum and mid_sentence[name] >= 1
         and as_date[name] * 2 < n),
        key=lambda n: -counts[n])[:limit]
