# SPDX-License-Identifier: Apache-2.0
"""Reading the manuscript aloud — proofing by ear.

Read-aloud finds clunky dialogue and unspeakable instructions better than
any metric does. **This module was designed around a constraint that has
since been lifted, and it is worth recording rather than quietly editing
out.** The plan assumed diffusion TTS, where a 6,000-word chapter is
minutes of synthesis rather than a play button, so every chapter went into
a background queue. ATK now runs Piper only: CPU, no VRAM, near real time.
So a passage is an interactive call again, and the queue is one option of
two:

* **`passages()` + `speak()`** — a paragraph, a line of dialogue, one
  numbered step, on demand. The high-value case: an author proofs the
  sentence they are unsure of, not the whole chapter.
* **`chapter_jobs()`** — queue the chapters, walk away, listen on
  headphones away from the screen. Still worth having: listening AWAY from
  the manuscript is how proofreading by ear actually works, and that is
  about attention, not about how fast the synthesiser is.

**One rule this module will not bend.** A speaking character is read in
the voice ATK has ESTABLISHED for them. If a character has no established
voice type, this module returns them in `needs_voice` and reads them in
the narrator's voice — it does not pick one. Assigning a voice by guess is
how a character acquires a voice type nobody chose, in a tool whose whole
argument is that it does not put words in the author's mouth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from . import textio as T
from .types import Span

#: Piper is comfortable well past this; the limit is the AUTHOR's, not the
#: synthesiser's. A clip longer than a paragraph cannot be re-listened to
#: without scrubbing, which is the whole activity.
MAX_PASSAGE_CHARS = 900

_SPEAKER = re.compile(
    r"[\"”’']\s*,?\s*(?:said\s+)?([A-Z][a-z]{2,})\b|"
    r"\b([A-Z][a-z]{2,})\s+(?:said|asked|replied|answered|murmured|"
    r"shouted|whispered)\b")
_QUOTED = re.compile(r"[\"“]([^\"“”]{2,600}?)[\"”]",
                     re.S)


@dataclass
class Line:
    """One speakable unit and who says it."""

    text: str
    span: Span
    speaker: str = ""            # "" = narration
    voice: str = ""
    language: str = ""

    @property
    def is_dialogue(self) -> bool:
        return bool(self.speaker)


@dataclass
class Job:
    """One queued render. Shaped for ATK's `render_queue`."""

    title: str
    out_path: str
    lines: list[Line] = field(default_factory=list)
    section_id: str = ""

    @property
    def chars(self) -> int:
        return sum(len(line.text) for line in self.lines)


def passages(doc, sec, *, max_chars: int = MAX_PASSAGE_CHARS,
             cast: list[str] | None = None) -> list[Line]:
    """Split a section into speakable units on sentence boundaries.

    Never mid-sentence. A synthesiser handed half a sentence produces a
    reading with the wrong intonation, and the author hears a problem in
    their prose that is really a problem in the split.
    """
    prose = doc.prose_of_file(sec.path)
    body = prose[sec.body.start:sec.body.end]
    names = {n for n in (cast or [])}
    out: list[Line] = []
    buf: list[tuple[int, int]] = []
    size = 0
    for start, end in T.sentences(body, base=sec.body.start):
        length = end - start
        if buf and size + length > max_chars:
            out.append(_line(doc, sec, prose, buf, names))
            buf, size = [], 0
        buf.append((start, end))
        size += length
    if buf:
        out.append(_line(doc, sec, prose, buf, names))
    return out


def _line(doc, sec, prose, spans, names) -> Line:
    start, end = spans[0][0], spans[-1][1]
    text = " ".join(prose[start:end].split())
    return Line(text=text, span=Span(sec.path, start, end),
                speaker=_speaker_of(text, names))


def _speaker_of(text: str, names: set[str]) -> str:
    if not _QUOTED.search(text):
        return ""
    for m in _SPEAKER.finditer(text):
        name = m.group(1) or m.group(2)
        if name and (not names or name in names):
            return name
    return ""


def assign_voices(lines: list[Line], *, narrator: str = "",
                  character_voices: dict[str, str] | None = None,
                  voice_languages: dict[str, str] | None = None
                  ) -> tuple[list[Line], list[str]]:
    """Give every line a voice, and NAME the characters that have none.

    Returns (lines, needs_voice). `needs_voice` is not a warning to log and
    move past — it is the list the host puts in front of the author, so
    they choose. Every character has an established voice type somewhere;
    if the workshop cannot find it, the answer is to ask, not to pick.
    """
    known = {k.lower(): v for k, v in (character_voices or {}).items()}
    langs = voice_languages or {}
    missing: list[str] = []
    for line in lines:
        if line.speaker and line.speaker.lower() in known:
            line.voice = known[line.speaker.lower()]
        else:
            if line.speaker and line.speaker not in missing:
                missing.append(line.speaker)
            line.voice = narrator
        line.language = langs.get(line.voice, "")
    return lines, missing


def chapter_jobs(doc, out_dir: str | Path, *, cast: list[str] | None = None,
                 narrator: str = "",
                 character_voices: dict[str, str] | None = None,
                 voice_languages: dict[str, str] | None = None,
                 sections=None) -> tuple[list[Job], list[str]]:
    """One job per chapter, ready for a render queue."""
    out_dir = Path(out_dir)
    jobs: list[Job] = []
    missing: list[str] = []
    for sec in (sections if sections is not None else doc.chapters()):
        lines = passages(doc, sec, cast=cast)
        if not lines:
            continue
        lines, gaps = assign_voices(
            lines, narrator=narrator, character_voices=character_voices,
            voice_languages=voice_languages)
        for name in gaps:
            if name not in missing:
                missing.append(name)
        slug = re.sub(r"[^A-Za-z0-9]+", "-",
                      (sec.number or sec.derived_number) + "-"
                      + sec.title).strip("-").lower()[:60] or sec.id
        jobs.append(Job(title=doc.label(sec),
                        out_path=str(out_dir / f"{slug}.wav"),
                        lines=lines, section_id=sec.id))
    return jobs, missing


def speak(host, line: Line, out_path: str = "") -> str:
    """Say one passage now. Returns the audio path, or "" if there is no
    speech engine — which is a state, not an error."""
    speech = getattr(host, "speech", None)
    if speech is None or not speech.available():
        return ""
    try:
        return speech.speak(line.text, voice=line.voice, out_path=out_path)
    except Exception:                                 # noqa: BLE001
        return ""


def render_job(host, job: Job, joiner=None) -> list[str]:
    """Synthesise every line of a chapter job. Returns the clip paths.

    Left as clips unless the host supplies a `joiner`: concatenating audio
    needs a codec library, this package has no runtime dependencies, and
    ATK already owns that machinery.
    """
    speech = getattr(host, "speech", None)
    if speech is None or not speech.available():
        return []
    base = Path(job.out_path)
    clips: list[str] = []
    for i, line in enumerate(job.lines):
        target = base.with_name(f"{base.stem}-{i:03d}{base.suffix}")
        try:
            path = speech.speak(line.text, voice=line.voice,
                                out_path=str(target))
        except Exception:                             # noqa: BLE001
            continue
        if path:
            clips.append(path)
    if joiner is not None and clips:
        joined = joiner(clips, job.out_path)
        if joined:
            return [joined]
    return clips
