# SPDX-License-Identifier: Apache-2.0
"""Lyrics written for Suno, and the voices they are sung in.

Two checks for the LYRICS document type, from the 2026-10-28 review (I12).

**`suno` — formatting discipline.** Suno reads a lyric literally, and the
mistakes that cost a generation are mechanical ones a page hides:

* a section tag spelled wrong (`[Chrous]`), which Suno sings as words;
* ALL-CAPS for emphasis, which it mispronounces — a delivery tag on the
  line before does the job;
* `(…)` inside a line, which it sings as a backing vocal;
* a vocal tag that is only a character's name, which tells Suno nothing
  about the voice — the tag must carry the timbre;
* two singers in one tag, because a second voice in one generation is
  unreliable — the other character is relayed as quoted narration;
* a song titled with a character's name;
* a style prompt or a lyric body over the length Suno takes.

The limits are numbers in the project's craft settings (`suno_max_chars`,
`suno_style_max`), because they are one author's measured practice, not
facts about music. An all-caps word that is meant (an acronym the song
spells out) is dismissed like any other finding. Drop the whole check from
a document type that is not written for Suno.

**`voice_locks` — the voice on record, never a guess.** A tag that names a
character is checked against the voice type the HOST says is on record for
them (`options["voice_types"]`, name → type). A tag that sings a character
in a different voice (a soprano tag on a Heldentenor) is a defect; a tag
that names them without the voice is a warning that says what is on
record; a character with NO voice type on record is reported so the author
can supply it. This module never infers a voice type — from the name, the
role or the lyric — because a voice nobody chose, written into a tag, is
how a character acquires a voice the author never decided on.
"""

from __future__ import annotations

from collections import defaultdict
import difflib
import re

from ..types import DEFECT, LYRICS, NOTE, WARN, CraftReport, Finding, Span
from . import ANY_LANGUAGE, Ctx, check
from .lyrics import SECTION_NAMES, _tag_name, is_aside

_TAG_LINE = re.compile(r"^\s*\[([^\]]{1,200})\]\s*$")
_CAPS = re.compile(r"(?<![\w'’])[A-Z]{3,}(?![\w'’])")
_ROMAN = re.compile(r"^[IVXLCDM]+$")
_PAREN = re.compile(r"\([^()\n]{1,80}\)")

#: Voice types, by family. A tag and a record are COMPATIBLE when they share
#: a family or the families are neighbours (a baritenor sits between tenor
#: and baritone); anything else is a broken lock.
FAMILIES = {
    "soprano": "soprano", "mezzo": "mezzo", "mezzo-soprano": "mezzo",
    "mezzosoprano": "mezzo", "contralto": "contralto", "alto": "contralto",
    "countertenor": "countertenor", "tenor": "tenor",
    "heldentenor": "tenor", "baritenor": "baritenor",
    "baritone": "baritone", "bass-baritone": "bass-baritone",
    "bassbaritone": "bass-baritone", "bass": "bass", "treble": "treble",
}
NEIGHBOURS = {frozenset(p) for p in (("tenor", "baritenor"),
                                     ("baritone", "baritenor"),
                                     ("baritone", "bass-baritone"),
                                     ("bass", "bass-baritone"),
                                     ("mezzo", "soprano"),
                                     ("mezzo", "contralto"))}

#: Words in a vocal tag that are neither the singer nor a descriptor.
_FILLER = {"vocal", "vocals", "voice", "sung", "sings", "by", "and", "the",
           "a", "an", "lead", "solo", "part"}


#: A family word next to one of these is an INSTRUMENT, not a voice: "over
#: a heavy bass drop" is not Mara sung as a bass, nor is "tenor sax".
_INSTRUMENT_AFTER = {
    "sax", "saxes", "saxophone", "saxophones", "drop", "drops", "line",
    "lines", "guitar", "guitars", "drum", "drums", "synth", "synths",
    "clarinet", "recorder", "trombone", "horn", "horns", "flute", "ukulele",
    "boost", "heavy", "riff", "riffs", "groove", "pedal", "pedals",
    "player", "section", "hits", "hit", "wobble", "kick", "note", "notes"}
_INSTRUMENT_BEFORE = {"808", "sub", "slap", "synth", "upright", "electric",
                      "double", "fretless", "acid", "deep", "booming"}
#: …and next to one of these it is a voice whatever came before it.
_VOICE_NOUNS = {"voice", "voiced", "vocal", "vocals", "singer", "register",
                "range", "timbre", "lead", "line-up"}


def voice_families(text: str) -> set[str]:
    """The voice-type families a string names. "Wagnerian Hochdramatische
    soprano" → {"soprano"}; "folk-rock register" → set(); "over a heavy bass
    drop" → set()."""
    out: set[str] = set()
    tokens: list[str] = []
    for token in re.sub(r"[^a-z0-9\-]+", " ", (text or "").lower()).split():
        if token in FAMILIES:             # mezzo-soprano, bass-baritone
            tokens.append(token)
        else:
            tokens.extend(t for t in token.split("-") if t)
    for i, word in enumerate(tokens):
        if word not in FAMILIES:
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        prv = tokens[i - 1] if i else ""
        if nxt not in _VOICE_NOUNS and (nxt in _INSTRUMENT_AFTER
                                        or prv in _INSTRUMENT_BEFORE):
            continue
        out.add(FAMILIES[word])
    return out


def compatible(tag: set[str], record: set[str]) -> bool:
    if tag & record:
        return True
    return any(frozenset((a, b)) in NEIGHBOURS for a in tag for b in record)


def names_in(text: str, cast: list[str]) -> list[str]:
    """Cast members named in `text`, longest names first so "Fake Valkyrie"
    is not also read as "Valkyrie"."""
    found: list[str] = []
    rest = text or ""
    for name in sorted({c for c in cast if c and c.strip()},
                       key=len, reverse=True):
        rx = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.I)
        if rx.search(rest):
            found.append(name)
            rest = rx.sub(" ", rest)
    return found


def _songs(doc) -> list[tuple]:
    """(song section, start, end) — a top-level section with everything
    under it, because a song written with `## Verse` headings is still one
    song."""
    out = []
    for top in doc.chapters():
        end = top.span.end
        parents = {top.id}
        for sec in doc.sections:
            if sec.parent_id in parents and sec.path == top.path:
                parents.add(sec.id)
                end = max(end, sec.span.end)
        out.append((top, top.body.start, end))
    return out


def _lines(text: str, start: int):
    pos = start
    for raw in text.splitlines(keepends=True):
        yield pos, raw.rstrip("\r\n")
        pos += len(raw)


def _head(tag: str) -> str:
    return _tag_name(tag)


def _closest(head: str) -> str:
    if len(head) < 4 or head in SECTION_NAMES:
        return ""
    match = difflib.get_close_matches(head, SECTION_NAMES, n=1, cutoff=0.75)
    return match[0] if match else ""


@check("suno", "Suno formatting", LYRICS, languages=ANY_LANGUAGE)
def suno(ctx: Ctx) -> CraftReport:
    rep = CraftReport()
    cast = list(ctx.cast or [])
    max_body = int(ctx.opt("suno_max_chars", 5000))
    max_style = int(ctx.opt("suno_style_max", 1000))
    #: Supplied by the HOST, not a threshold: the voice types on record.
    recorded = {str(k).lower() for k, v in
                (ctx.options.get("voice_types") or {}).items() if v}
    songs = 0
    for top, start, end in _songs(ctx.doc):
        src = ctx.doc.file(top.path)
        if src is None:
            continue
        text = src.text[start:end]
        label = ctx.doc.label(top)
        songs += 1
        body_chars, style, in_body = 0, [], False
        caps, parens = [], []
        for pos, line in _lines(text, start):
            bare = line.strip()
            if bare.startswith(">"):
                style.append(bare.lstrip("> ").rstrip())
                continue
            tag = _TAG_LINE.match(line)
            if tag:
                in_body = True
                body_chars += len(line) + 1
                inner = tag.group(1)
                head = _head(inner)
                # A tag that IS a character's name ("[Bridget]") is not a
                # misspelt "[Bridge]".
                guess = "" if names_in(head, cast) else _closest(head)
                span = Span(top.path, pos, pos + len(line))
                if guess:
                    rep.findings.append(Finding(
                        "suno", WARN,
                        f"[{inner}] in “{label}” looks like [{guess.title()}]",
                        "Suno only knows a section by its tag. A misspelled "
                        "one is not a section — it is sung, or ignored.",
                        span=span, section_id=top.id, evidence=[bare],
                        data={"tag": inner, "id": inner.lower()}))
                singers = names_in(inner, cast)
                if len(singers) >= 2 or re.search(r"\bduet\b", inner, re.I):
                    rep.findings.append(Finding(
                        "suno", WARN,
                        f"Two voices in one tag in “{label}”: [{inner}]",
                        "One voice per generation is what renders reliably. "
                        "Sing the other character's lines as quoted "
                        "narration with a delivery tag on the line before.",
                        span=span, section_id=top.id, evidence=[bare],
                        data={"tag": inner, "id": inner.lower(),
                              "names": singers}))
                elif singers:
                    rest = inner
                    for name in singers:
                        rest = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ",
                                      rest, flags=re.I)
                    words = [w for w in re.findall(r"[a-z]+", rest.lower())
                             if w not in _FILLER and w not in SECTION_NAMES
                             and not w.isdigit()]
                    words = [w for w in words if _tag_name(w) not in
                             SECTION_NAMES]
                    # A character WITH a voice type on record is
                    # `voice_locks`' to report, with the record quoted.
                    if not words and singers[0].lower() not in recorded:
                        rep.findings.append(Finding(
                            "suno", WARN,
                            f"[{inner}] in “{label}” names {singers[0]} "
                            f"but not the voice",
                            "A name tells Suno nothing about how to sing. "
                            "Every vocal tag carries the full timbre — the "
                            "voice type and its descriptors.",
                            span=span, section_id=top.id, evidence=[bare],
                            data={"tag": inner, "id": inner.lower(),
                                  "name": singers[0]}))
                continue
            if not in_body or not bare:
                if in_body:
                    body_chars += 1
                continue
            body_chars += len(line) + 1
            if is_aside(bare):
                continue
            words = [w for w in _CAPS.findall(line) if not _ROMAN.match(w)]
            if words:
                caps.append((pos, line, words))
            if _PAREN.search(bare):
                parens.append((pos, line))
        if caps:
            pos, line, _w = caps[0]
            every = sorted({w for _p, _l, ws in caps for w in ws})
            rep.findings.append(Finding(
                "suno", WARN,
                f"ALL-CAPS in “{label}”: {', '.join(every[:6])}"
                + (" …" if len(every) > 6 else ""),
                "Suno mispronounces words written in capitals. For "
                "emphasis, put a delivery tag on the line before "
                "([Shouted], [Belted]) and write the word normally.",
                span=Span(top.path, pos, pos + len(line)),
                section_id=top.id,
                evidence=[ln for _p, ln, _w in caps[:3]],
                data={"words": every}))
        if parens:
            pos, line = parens[0]
            rep.findings.append(Finding(
                "suno", NOTE,
                f"{len(parens)} line{'s' if len(parens) != 1 else ''} in "
                f"“{label}” with (…) inside",
                "Suno sings words in parentheses as a backing vocal. Right "
                "for an ad-lib; wrong for an aside meant to be read.",
                span=Span(top.path, pos, pos + len(line)),
                section_id=top.id, evidence=[ln for _p, ln in parens[:3]],
                data={"lines": len(parens)}))
        if names_in(top.title, cast) and \
                top.title.strip().lower() in {c.lower() for c in cast}:
            rep.findings.append(Finding(
                "suno", WARN,
                f"“{label}” is titled with a character's name",
                "A song named for a character reads as a theme or a "
                "credit. Title it for what the song is about.",
                span=top.span, section_id=top.id,
                data={"name": top.title}))
        prompt = " ".join(style).strip()
        if len(prompt) > max_style:
            rep.findings.append(Finding(
                "suno", WARN,
                f"Style prompt for “{label}” is {len(prompt):,} characters "
                f"(limit {max_style:,})",
                "The style field is cut at its limit, and what is cut is "
                "usually the end — the most specific instructions.",
                span=top.span, section_id=top.id,
                evidence=[prompt[:160] + "…"],
                data={"chars": len(prompt), "limit": max_style}))
        if body_chars > max_body:
            rep.findings.append(Finding(
                "suno", WARN,
                f"Lyric body of “{label}” is {body_chars:,} characters "
                f"(limit {max_body:,})",
                "Counted from the first [tag] to the end of the song, "
                "without the style prompt. Past the limit the end of the "
                "song is not sung.",
                span=top.span, section_id=top.id,
                data={"chars": body_chars, "limit": max_body}))
    rep.metrics["suno_songs"] = songs
    return rep


@check("voice_locks", "Voice types on record", LYRICS,
       languages=ANY_LANGUAGE)
def voice_locks(ctx: Ctx) -> CraftReport:
    rep = CraftReport()
    cast = list(ctx.cast or [])
    record = {str(k).lower(): str(v or "")
              for k, v in (ctx.options.get("voice_types") or {}).items()}
    if not cast:
        rep.quiet["voice_locks"] = (
            "no cast is known — name the characters on the Storyline page "
            "and their tags are checked against the voice types on record")
        return rep
    asked: set[str] = set()
    sung: defaultdict[str, int] = defaultdict(int)
    for top, start, end in _songs(ctx.doc):
        src = ctx.doc.file(top.path)
        if src is None:
            continue
        label = ctx.doc.label(top)
        for pos, line in _lines(src.text[start:end], start):
            tag = _TAG_LINE.match(line)
            if not tag:
                continue
            inner = tag.group(1)
            span = Span(top.path, pos, pos + len(line))
            for name in names_in(inner, cast):
                sung[name] += 1
                on_record = record.get(name.lower(), "").strip()
                if not on_record:
                    if name.lower() not in asked:
                        asked.add(name.lower())
                        rep.findings.append(Finding(
                            "voice_locks", NOTE,
                            f"{name} has no voice type on record",
                            "Sung here, and nothing says what voice they "
                            "are. Record it (the Storyline's Voice type, or "
                            "the character's sheet) — it is never guessed, "
                            "so until then this tag cannot be checked.",
                            span=span, section_id=top.id,
                            evidence=[line.strip()],
                            data={"name": name}))
                    continue
                want = voice_families(on_record)
                have = voice_families(inner)
                if have and want and not compatible(have, want):
                    rep.findings.append(Finding(
                        "voice_locks", DEFECT,
                        f"[{inner}] in “{label}” sings {name} as "
                        f"{', '.join(sorted(have))}",
                        f"{name} is on record as: {on_record}. A different "
                        f"voice type in the tag is a different singer to "
                        f"Suno, and the character's voice lock is broken.",
                        span=span, section_id=top.id,
                        evidence=[line.strip(), f"on record: {on_record}"],
                        data={"name": name, "id": inner.lower(),
                              "tag": inner}))
                elif not have:
                    rep.findings.append(Finding(
                        "voice_locks", WARN,
                        f"[{inner}] in “{label}” does not say {name}'s "
                        f"voice",
                        f"On record: {on_record}. Without it in the tag, "
                        f"Suno picks a voice — and not the same one twice.",
                        span=span, section_id=top.id,
                        evidence=[line.strip(), f"on record: {on_record}"],
                        data={"name": name, "id": inner.lower(),
                              "tag": inner}))
    rep.metrics["voice_locks_sung"] = dict(sung)
    return rep
