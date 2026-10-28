# SPDX-License-Identifier: Apache-2.0
"""Craft checks for words that are going to be sung.

Lyrics are not a kind of fiction and the difference is not stylistic. A
novel's unit is the sentence; a lyric's unit is the LINE, and a line that
will not fit the bar is a defect the singer discovers and the writer
never does. A novel that repeats itself has a problem; a chorus that does
NOT repeat itself exactly has a different one — and the commonest real
error in a finished lyric is a refrain that drifts by one word between its
second and third appearance, which is invisible on the page and obvious
the moment somebody tries to learn it.

Everything here is the same arithmetic the rest of the package uses, and
one primitive it already had and never spent: `textio.syllables`.

**On rhyme, stated plainly.** Rhyme is a fact about SOUND and this package
has no pronunciation dictionary and will not grow one — that is a data
file, and the zero-dependency rule is worth more than the last ten per
cent of a rhyme detector. So the rhyme key here is built from SPELLING:
it pairs *night/light* and *love/above* and it misses *sky/high*. Every
finding it produces says so. A check that quietly claimed to hear would
be worse than one that says what it is looking at.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import re

from .. import textio as T
from ..types import LYRICS, NOTE, WARN, CraftReport, Finding, Span
from . import ANY_LANGUAGE, Ctx, check
from .shared import describe

#: The names of the parts of a song. A PARENTHESISED line is a tag only
#: when it names one of these: `(Chorus)` is a tag and `(rise again)` is a
#: backing vocal, which used to be read as a tag — every `(ooh)` started a
#: new "section" and split the refrain it was sung over.
SECTION_NAMES = (
    "verse", "chorus", "pre-chorus", "prechorus", "post-chorus", "refrain",
    "bridge", "intro", "outro", "hook", "coda", "interlude", "breakdown",
    "instrumental", "solo", "tag", "drop", "rap", "spoken", "middle eight",
    "middle 8", "final chorus", "outro chorus", "vamp", "turnaround")
_SECTION_NAME = re.compile(
    r"^(?:" + "|".join(re.escape(n) for n in SECTION_NAMES) +
    r")(?:\s*[\d]+|\s+[ivx]+)?(?:\s*[:\-–—]\s*.{0,30}|\s*[x×]\s*\d+)?$",
    re.IGNORECASE)

#: A performance tag on its own line — `[Chorus]`, `(Verse 2)` — the way
#: lyrics are written for a singer or for a generator. A `## Chorus`
#: HEADING is a tag too, but the manuscript makes a section of it, so the
#: refrain check reads it from the section title (`_tag_of_title`).
_BRACKET = re.compile(r"^\s*\[([^\]]{1,40})\]\s*$")
_PAREN = re.compile(r"^\s*\(([^)]{1,40})\)\s*$")

_VOWELS = "aeiouy"


class _TagMatch:
    def __init__(self, name: str) -> None:
        self._name = name

    def group(self, _n: int = 1) -> str:
        return self._name


class _Tags:
    """`_TAG.match(line)`, kept as the one spelling the checks use."""

    @staticmethod
    def match(text: str):
        m = _BRACKET.match(text)
        if m:
            return _TagMatch(m.group(1))
        m = _PAREN.match(text)
        if m and _SECTION_NAME.match(m.group(1).strip()):
            return _TagMatch(m.group(1))
        return None


_TAG = _Tags()


def is_aside(text: str) -> bool:
    """A whole line in parentheses that is NOT a tag: a backing vocal,
    an ad-lib. Sung, but not the lead line — it neither counts toward the
    line's syllables nor breaks the stanza it is sung over."""
    return bool(_PAREN.match(text)) and _TAG.match(text) is None


def _tag_of_title(title: str) -> str:
    """`## Chorus` → "chorus"; a heading that is not a part's name → ""."""
    title = (title or "").strip()
    return _tag_name(title) if _SECTION_NAME.match(title) else ""


def lines_of(ctx: Ctx, sec) -> list[tuple[int, int, str]]:
    """Every sung line in a section: (start, end, text), file offsets.

    A LINE, not a sentence. Lyrics are broken by the line break and
    punctuated barely or not at all, so the sentence splitter — which is
    the right tool everywhere else in this package — would glue a whole
    verse into one 40-word "sentence" and every measurement after it
    would be about something that does not exist.
    """
    prose = ctx.doc.prose_of_file(sec.path)
    out = []
    pos = sec.body.start
    body = prose[sec.body.start:sec.body.end]
    for raw in body.splitlines(keepends=True):
        text = raw.strip()
        if text and not _TAG.match(text) and not is_aside(text):
            lead = len(raw) - len(raw.lstrip())
            out.append((pos + lead, pos + lead + len(text), text))
        pos += len(raw)
    return out


def syllables_in(text: str) -> int:
    return sum(T.syllables(w) for w in T.word_list(text))


def _is_vowel(word: str, i: int) -> bool:
    # `y` is a vowel except where it starts the word ("yes", "young"), and
    # the `u` of `qu` is a consonant ("queen" rhymes with "between").
    if word[i] not in _VOWELS:
        return False
    if word[i] == "y" and i == 0:
        return False
    return not (word[i] == "u" and i > 0 and word[i - 1] == "q")


def rhyme_key(line: str) -> str:
    """A spelling-based rhyme key for a line's last word.

    The final vowel GROUP and everything after it. `night` -> `ight`,
    `rain` -> `ain`, `day` -> `ay`, `river` -> `er`; and a silent final
    `e` is looked through, so `above`/`love` -> `ove` and `fire`/`desire`
    -> `ire`. It is an approximation of a sound and every finding that
    uses it says so.

    It used to take the last vowel LETTER: `rain` -> `in`, so rain rhymed
    with skin, and `day` -> `y` (padded to `day`), so day never rhymed
    with way.
    """
    words = T.word_list(line)
    if not words:
        return ""
    word = T.normalise(words[-1]).strip("'-")
    if len(word) < 2:
        return word
    end = len(word)
    # Look through a silent final e (and -es): consonant + e at the end of
    # a word with a vowel before it.
    for tail in ("es", "e"):
        cut = len(word) - len(tail)
        if (word.endswith(tail) and cut >= 2 and not _is_vowel(word, cut - 1)
                and any(_is_vowel(word, j) for j in range(cut - 1))):
            end = cut - 1
            break
    last = -1
    for i in range(end - 1, -1, -1):
        if _is_vowel(word, i):
            last = i
            break
    if last < 0:
        return word[-3:]
    first = last
    while first > 0 and _is_vowel(word, first - 1):
        first -= 1
    key = word[first:]
    return key if len(key) >= 2 else word[-3:]


def scheme_of(keys: list[str]) -> str:
    """`AABB`, `ABAB`, `ABCB` — the shape of one stanza's rhymes."""
    letters: dict[str, str] = {}
    out = []
    for k in keys:
        if not k:
            out.append("-")
            continue
        if k not in letters:
            letters[k] = chr(ord("A") + len(letters) % 26)
        out.append(letters[k])
    return "".join(out)


def stanzas(ctx: Ctx, sec) -> list[list[tuple[int, int, str]]]:
    """Lines grouped into stanzas, split on blank lines."""
    prose = ctx.doc.prose_of_file(sec.path)
    groups: list[list] = []
    current: list = []
    pos = sec.body.start
    body = prose[sec.body.start:sec.body.end]
    for raw in body.splitlines(keepends=True):
        text = raw.strip()
        if text and is_aside(text):
            pass                     # sung over the stanza, not part of it
        elif not text or _TAG.match(text):
            if current:
                groups.append(current)
                current = []
        else:
            lead = len(raw) - len(raw.lstrip())
            current.append((pos + lead, pos + lead + len(text), text))
        pos += len(raw)
    if current:
        groups.append(current)
    return groups


# ---------------------------------------------------------------------------
# 1. the line, and whether it can be sung
# ---------------------------------------------------------------------------


@check("lyric_lines", "Line length and syllable count", LYRICS,
       languages=ANY_LANGUAGE)
def lyric_lines(ctx: Ctx) -> CraftReport:
    """Syllables per line, against the section's OWN shape.

    Not against a rule about what a line should be — there is no such
    rule, and a tool that had one would be arguing with every form older
    than it. Against the piece's own median, because a verse whose lines
    run 8, 8, 8, 8, 14 has one line the tune has nowhere to put, and that
    is a fact about the lyric rather than a taste.
    """
    rep = CraftReport()
    tolerance = float(ctx.opt("syllable_tolerance", 1.6))
    rows = {}
    every: list[float] = []
    for sec in ctx.doc.sections:
        counts = []
        for start, end, text in lines_of(ctx, sec):
            n = syllables_in(text)
            if n:
                counts.append((n, start, end, text))
        if len(counts) < 3:
            continue
        values = [float(n) for n, _s, _e, _t in counts]
        summary = describe(values)
        rows[sec.id] = {"title": sec.title, "lines": len(counts),
                        **summary}
        every.extend(values)
        median = summary["median"] or 0.0
        sd = summary["sd"] or 0.0
        if not median:
            continue
        limit = max(3.0, sd * tolerance) if sd else max(3.0, median * 0.5)
        for n, start, end, text in counts:
            if abs(n - median) <= limit:
                continue
            span = Span(sec.path, start, end)
            rep.findings.append(Finding(
                "lyric_lines", NOTE,
                f"{ctx.doc.label(sec)}: a {n}-syllable line against a "
                f"median of {median:.0f}",
                "Long or short against the lines around it. Deliberate "
                "in a bridge and a problem in a verse — the tool cannot "
                "hear the tune and does not guess.",
                span=span, section_id=sec.id,
                evidence=[text],
                data={"syllables": n, "median": median,
                      "line": text}))
    rep.metrics["lyric_lines_by_section"] = rows
    rep.metrics["syllables_per_line"] = describe(every)
    return rep


# ---------------------------------------------------------------------------
# 2. the refrain that drifted
# ---------------------------------------------------------------------------


def _flat(text: str) -> str:
    return re.sub(r"[^\w ]+", "", " ".join(text.lower().split()))


@check("refrain", "Refrains that do not repeat exactly", LYRICS,
       languages=ANY_LANGUAGE)
def refrain(ctx: Ctx) -> CraftReport:
    """A section that repeats, and the one line in it that drifted.

    The error this check exists for: a chorus written three times, and
    the third says "and I will wait beside the water" where the others
    say "and I'll be waiting by the water". Nothing on the page shows it,
    every reader's eye skips it because they already know the line, and
    it surfaces the first time somebody tries to sing along.

    **Found by POSITION, not by similarity.** The first version of this
    compared every line to every other by word overlap, and missed the
    example above outright — a rewritten line shares almost no words with
    the line it replaced, which is exactly why it is hard to see. What
    identifies a refrain is that it is *the same part of the song*: two
    stanzas under the same tag, compared line for line. That is precise,
    it needs no threshold, and it produces the one sentence the writer
    needs: "the second chorus, line 1."

    Lyrics with no tags fall back to a similarity pass, reported as a
    NOTE, because there the tool really is guessing.
    """
    rep = CraftReport()
    tagged: defaultdict[str, list] = defaultdict(list)
    for sec in ctx.doc.sections:
        for tag, group in _tagged_stanzas(ctx, sec):
            if tag:
                tagged[tag].append((sec.id, group))

    drifted = 0
    for tag, blocks in tagged.items():
        if len(blocks) < 2:
            continue
        # THE REFERENCE IS THE MAJORITY, NOT THE FIRST (2026-10-28). When
        # the first chorus was the one that drifted, every correct repeat
        # after it was reported as the error. Each line is compared with
        # the version most occurrences agree on; with only two, or no
        # majority, the first occurrence stands in and the evidence says
        # "first:" rather than claiming a consensus that is not there.
        lengths = Counter(len(group) for _sid, group in blocks)
        size = max(lengths.items(), key=lambda kv: (
            kv[1], -[len(g) for _s, g in blocks].index(kv[0])))[0]
        alike = [(n, sid, group) for n, (sid, group) in
                 enumerate(blocks, 1) if abs(len(group) - size) <= 1]
        model = next(group for _n, _sid, group in alike if len(group) == size)
        reference: list[tuple[str, bool]] = []
        for i in range(size):
            versions = Counter(_flat(group[i][2]) for _n, _sid, group in alike
                               if i < len(group))
            text, count = versions.most_common(1)[0]
            if count * 2 > sum(versions.values()) and len(alike) >= 3:
                shown = next(group[i][2] for _n, _sid, group in alike
                             if i < len(group) and _flat(group[i][2]) == text)
                reference.append((shown, True))
            else:
                reference.append((model[i][2], False))
        for n, (section_id, other) in enumerate(blocks, 1):
            if abs(len(other) - size) > 1:
                rep.findings.append(Finding(
                    "refrain", NOTE,
                    f"“{tag}” has {len(other)} lines here and "
                    f"{size} elsewhere",
                    "A repeated section of a different length. "
                    "Deliberate in a final chorus and an accident "
                    "everywhere else.",
                    span=Span(ctx.doc.section(section_id).path
                              if ctx.doc.section(section_id) else "",
                              other[0][0], other[-1][1]),
                    section_id=section_id,
                    data={"tag": tag, "occurrence": n}))
                continue
            # WHICH lines differ is decided before ANY of them is
            # reported, because the answer changes what they mean. A
            # block where one line in four differs is a refrain that
            # drifted. A block where every line differs is a VERSE — a
            # section that recurs by name and is supposed to carry new
            # words every time — and reporting those four lines was this
            # check's first output and its first false positive.
            changed = [i for i, (_s, _e, text) in enumerate(other)
                       if i < size and _flat(text) != _flat(reference[i][0])]
            if len(changed) > max(1, len(other) // 3):
                continue
            for i in changed:
                start, end, text = other[i]
                was, agreed = reference[i]
                if not agreed and other is model:
                    continue           # the stand-in cannot differ from itself
                drifted += 1
                sec = ctx.doc.section(section_id)
                where = (f"on repeat {n}" if n > 1 else
                         "the first time it is sung")
                rep.findings.append(Finding(
                    "refrain", WARN,
                    f"“{tag}” line {i + 1} differs {where}",
                    "A refrain that does not repeat exactly. Invisible "
                    "on the page — the reader already knows the line — "
                    "and the first thing a singer finds.",
                    span=Span(sec.path if sec else "", start, end),
                    section_id=section_id,
                    evidence=[f"{'everywhere else' if agreed else 'first'}:"
                              f" {was}", f"occurrence {n}: {text}"],
                    data={"tag": tag, "occurrence": n, "line": i + 1,
                          "first": was, "then": text}))
    rep.metrics["refrain_tags"] = {k: len(v) for k, v in tagged.items()}
    rep.metrics["refrain_drifted"] = drifted

    if not tagged:
        rep.merge(_untagged_refrains(ctx))
    return rep


def _tagged_stanzas(ctx: Ctx, sec):
    """(tag, lines) for each stanza, tag being the `[Chorus]` above it.

    A stanza with no tag above it carries the last tag seen, which is how
    a lyric with `[Chorus]` written once over a two-stanza chorus reads
    to a human.
    """
    prose = ctx.doc.prose_of_file(sec.path)
    body = prose[sec.body.start:sec.body.end]
    out: list[tuple[str, list]] = []
    # A `## Chorus` heading is the tag of what is under it. The heading is
    # masked out of the prose, so without this every stanza under one had
    # no tag at all and was never compared.
    tag = _tag_of_title(sec.title)
    current: list = []
    pos = sec.body.start
    for raw in body.splitlines(keepends=True):
        text = raw.strip()
        m = _TAG.match(text) if text else None
        if text and is_aside(text):
            pos += len(raw)
            continue
        if m:
            if current:
                out.append((tag, current))
                current = []
            tag = _tag_name(m.group(1))
        elif not text:
            if current:
                out.append((tag, current))
                current = []
        else:
            lead = len(raw) - len(raw.lstrip())
            current.append((pos + lead, pos + lead + len(text), text))
        pos += len(raw)
    if current:
        out.append((tag, current))
    return out


def _tag_name(raw: str) -> str:
    """`Chorus 2` and `chorus` are the same section of the song.

    Trailing numbers are dropped on purpose — that is what makes two
    occurrences comparable. `Verse 1` and `Verse 2` collapse together
    too, and that is also correct: a verse is supposed to carry new words
    every time, so it is compared like everything else and then rejected
    by the majority rule above, which is a structural test rather than a
    list of section names somebody has to keep up to date.
    """
    name = re.sub(r"[\s\d]+$", "", raw.strip()).strip().lower()
    return name


def _untagged_refrains(ctx: Ctx) -> CraftReport:
    """Near-identical lines in a lyric with no performance tags."""
    import difflib
    rep = CraftReport()
    lines: list[tuple[str, Span, str]] = []
    for sec in ctx.doc.sections:
        for start, end, text in lines_of(ctx, sec):
            if len(T.word_list(text)) >= 3:
                lines.append((sec.id, Span(sec.path, start, end), text))
    seen: set[tuple[str, str]] = set()
    for i, (sid_a, span_a, a) in enumerate(lines):
        for _sid_b, _span_b, b in lines[i + 1:]:
            fa, fb = _flat(a), _flat(b)
            if fa == fb or (fa, fb) in seen:
                continue
            ratio = difflib.SequenceMatcher(None, fa, fb).ratio()
            if ratio < 0.62:
                continue
            seen.add((fa, fb))
            rep.findings.append(Finding(
                "refrain", NOTE,
                "Two lines that are nearly the same",
                "The lyric has no performance tags, so this is a "
                "similarity guess rather than a comparison of the same "
                "part of the song. Tag the sections and the check "
                "becomes exact.",
                span=span_a, section_id=sid_a, evidence=[a, b],
                data={"a": a, "b": b, "ratio": round(ratio, 2)}))
    return rep


# ---------------------------------------------------------------------------
# 3. the rhyme scheme, and where it breaks
# ---------------------------------------------------------------------------


@check("rhyme", "Rhyme scheme, and where it changes", LYRICS,
       languages=("en",))
def rhyme(ctx: Ctx) -> CraftReport:
    """The scheme each stanza holds, and the one stanza that does not.

    Reported only when a piece HAS a dominant scheme — most stanzas
    agreeing — because a lyric with no fixed scheme is a choice and not a
    finding, and a tool that reported it would be telling free verse it
    is broken.

    The rhyme key is built from spelling and misses `sky`/`high`. That
    limit is in the finding, every time.
    """
    rep = CraftReport()
    schemes: Counter = Counter()
    rows: list[tuple[str, str, Span, list[str]]] = []
    for sec in ctx.doc.sections:
        for group in stanzas(ctx, sec):
            if not 2 <= len(group) <= 8:
                continue
            keys = [rhyme_key(text) for _s, _e, text in group]
            shape = scheme_of(keys)
            if shape.count("-") > len(shape) // 2:
                continue
            schemes[shape] += 1
            rows.append((sec.id, shape,
                         Span(sec.path, group[0][0], group[-1][1]),
                         [t for _s, _e, t in group]))
    rep.metrics["rhyme_schemes"] = dict(schemes.most_common(8))
    if len(rows) < 4 or not schemes:
        return rep
    dominant, count = schemes.most_common(1)[0]
    if count < max(3, len(rows) * 0.5):
        rep.metrics["rhyme_dominant"] = ""
        return rep
    rep.metrics["rhyme_dominant"] = dominant
    for section_id, shape, span, lines in rows:
        if shape == dominant or len(shape) != len(dominant):
            continue
        sec = ctx.doc.section(section_id)
        rep.findings.append(Finding(
            "rhyme", NOTE,
            f"A {shape} stanza in a {dominant} lyric"
            + (f" ({ctx.doc.label(sec)})" if sec else ""),
            "Worth confirming as a choice. The rhyme key here is built "
            "from SPELLING, not from sound: it pairs night/light and "
            "love/above and it misses sky/high, so treat a single "
            "unexpected letter as a question rather than an answer.",
            span=span, section_id=section_id,
            evidence=lines[:4],
            data={"scheme": shape, "dominant": dominant}))
    return rep
