# SPDX-License-Identifier: Apache-2.0
"""Which prose came out of The Room — the fingerprint's missing input.

`fingerprint.fit` says it plainly and has never been able to act on it:

    *"Accepted" is load-bearing. Fitting on a draft that already contains
    the model's rewrites bakes the drift into the baseline, and the tool
    then reports that everything matches beautifully — the exact failure
    it exists to prevent.*

Nothing tracked it. `from_manuscript` fitted on whatever was on disk, so
the longer an author used The Room the more the baseline became the
model's voice, and the drift score fell towards zero while the drift
itself grew. A defence that quietly disarms itself with use is worse than
none, because it reports success.

**The record lives in `.workshop/`, never in the manuscript.** Not a
marker, not a comment, not an HTML span. The rule that nothing but the
author writes into the book is not suspended for the tool's own
bookkeeping.

**Text, not offsets.** A span recorded on Tuesday points at the wrong
characters on Wednesday, because the author has been writing. So what is
kept is the accepted TEXT, and it is re-located in the manuscript when it
is needed. That has a property worth having on purpose: once the author
has rewritten an accepted passage enough that it can no longer be found,
it stops counting as the model's — which is exactly right, because by
then it is theirs.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .state import INFLUENCE, Store
from .types import Span

#: How much of one accepted passage to keep. Enough to find it again;
#: this file is not a second copy of the manuscript.
MAX_KEPT = 4000


@dataclass
class Accepted:
    """One passage the author took from a persona, as recorded."""

    text: str
    persona: str = ""
    at: str = ""
    note: str = ""
    path: str = ""

    @property
    def words(self) -> int:
        return len(self.text.split())


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class Influences:
    """What The Room contributed, and where it still is."""

    def __init__(self, store: Store) -> None:
        self.store = store
        data = store.read(INFLUENCE, {})
        rows = data.get("accepted") if isinstance(data, dict) else None
        self.accepted: list[Accepted] = [
            Accepted(text=str(r.get("text") or ""),
                     persona=str(r.get("persona") or ""),
                     at=str(r.get("at") or ""),
                     note=str(r.get("note") or ""),
                     path=str(r.get("path") or ""))
            for r in (rows or []) if isinstance(r, dict)
            and str(r.get("text") or "").strip()]

    def __len__(self) -> int:
        return len(self.accepted)

    @property
    def words(self) -> int:
        return sum(row.words for row in self.accepted)

    def record(self, text: str, *, persona: str = "", at: str = "",
               note: str = "", path: str = "", save: bool = True) -> bool:
        """Note that the author accepted this text. Called on ACCEPT only.

        Returns False for text too short to be worth tracking — a
        three-word splice is not a voice, and a store full of fragments
        would find them everywhere.
        """
        body = _flat(text)[:MAX_KEPT]
        if len(body.split()) < 12:
            return False
        if any(_flat(row.text) == body for row in self.accepted):
            return True
        self.accepted.append(Accepted(body, persona, at, note, path))
        if save:
            self.save()
        return True

    def forget(self, index: int, *, save: bool = True) -> bool:
        if not 0 <= index < len(self.accepted):
            return False
        del self.accepted[index]
        if save:
            self.save()
        return True

    def save(self) -> None:
        self.store.write(INFLUENCE, {"version": 1, "accepted": [
            {"text": r.text, "persona": r.persona, "at": r.at,
             "note": r.note, "path": r.path} for r in self.accepted]})

    # -- finding it again -------------------------------------------------

    def spans_in(self, doc) -> list[Span]:
        """Where the accepted passages still are, in the current text.

        A passage that has been rewritten past recognition is not found,
        and that is the intended answer rather than a miss.
        """
        out: list[Span] = []
        for row in self.accepted:
            needle = _flat(row.text)
            if not needle:
                continue
            for src in doc.files:
                prose = doc.prose_of_file(src.rel)
                at = _locate(prose, needle)
                if at >= 0:
                    out.append(Span(src.rel, at, at + len(needle)))
                    break
        return out

    def still_present(self, doc) -> int:
        return len(self.spans_in(doc))


def _locate(body: str, needle: str) -> int:
    """Find text whose whitespace may have been reflowed since.

    The same problem `codex.extract` solves for a model's quote, and the
    same answer: whitespace is allowed to differ and nothing else is.
    """
    at = body.find(needle)
    if at >= 0:
        return at
    flat = re.sub(r"\s+", " ", body)
    at = flat.find(needle)
    if at < 0:
        return -1
    consumed = 0
    for i, ch in enumerate(body):
        if consumed == at:
            return i
        if not (ch.isspace() and i and body[i - 1].isspace()):
            consumed += 1
    return -1


def blank(text: str, spans: list[Span], path: str) -> str:
    """Replace influenced ranges with spaces of the same length.

    Spaces rather than deletion, exactly as `textio.mask_nonprose` does
    it, so every offset in the result still points at the file on disk.
    """
    if not spans:
        return text
    out = list(text)
    for span in spans:
        if span.path != path:
            continue
        for i in range(max(0, span.start), min(len(out), span.end)):
            if not out[i].isspace():
                out[i] = " "
    return "".join(out)
