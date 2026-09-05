# SPDX-License-Identifier: Apache-2.0
"""The Ports — everything the host provides — and a working default for each.

Ports are `typing.Protocol` classes, so a host implements them
**structurally**: no inheritance, no import of anything from this package.
That is what lets ATK wire the workshop to `LLMEngine`, `SafeStore`,
`ledger` and Piper without the engine ever importing `atk.*` — and a test
in this repo walks the package and fails the build if it ever does.

**Every port ships a default that actually works**, not a stub that raises.
That is a deliberate difference from the usual Null Object: this package's
whole thesis is that the useful half needs no model, so the hostless path
has to be a real path. `KeywordRetriever` is a real BM25 index in the
standard library; `SilentEvents` really is silent; only `NullLLM` refuses,
and it refuses with `NoModelError`, which the host is expected to catch and
render as "that part needs a model loaded" rather than as a crash.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
import datetime as _dt
import math
import re
import threading
from typing import Any, Protocol, runtime_checkable

from .errors import NoModelError

# ---------------------------------------------------------------------------
# cancellation
# ---------------------------------------------------------------------------


@runtime_checkable
class CancelToken(Protocol):
    """The one thing a host may call from another thread.

    A whole-manuscript pass on forty sections is minutes of work, so a GUI
    host needs a defined way to stop one. The core checks between sections
    and before every model call — never inside a measurement, because those
    are milliseconds and a half-finished report is worse than a slow one.
    """

    def is_set(self) -> bool: ...


class Cancel:
    """A thread-safe `CancelToken`. Hosts may use this or bring their own."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


class NeverCancelled:
    def is_set(self) -> bool:
        return False


NEVER = NeverCancelled()


# ---------------------------------------------------------------------------
# the language model
# ---------------------------------------------------------------------------


@dataclass
class ModelInfo:
    """What the host knows about the loaded model, for the Budget Meter.

    `usable_tokens` is the MEASURED usable context, not the declared one.
    ATK measured a 10-100x gap between the two across its own model folder
    — Qwythos says 1M in its filename and gets 75k — and a budget computed
    from the declared number is a budget that fails at the worst moment.
    `measured=False` says so out loud rather than presenting a default as a
    reading.
    """

    name: str = ""
    usable_tokens: int = 0
    declared_tokens: int = 0
    layers_on_card: int = 0
    total_layers: int = 0
    host_mb: float = 0.0
    measured: bool = False
    alternative: str = ""
    exact_token_counts: bool = False


@runtime_checkable
class LLM(Protocol):
    """A single, synchronous completion. No streaming, no chat history.

    *A host may assume* the core calls this from a worker thread, one call
    at a time, and honours `cancel` between calls but not during one.

    *A host must guarantee* that `complete` either returns text or raises;
    that `grammar`, when given, constrains the output (ATK has GBNF, and an
    outline generated under a JSON grammar cannot come back unparseable —
    which deletes an entire failure class the 2023-era markdown parser had);
    and that `count_tokens` returns the loaded model's real count or None.
    Returning a guess from `count_tokens` is worse than returning None: the
    assembler can say "estimated" about its own heuristic and cannot say it
    about yours.
    """

    def complete(self, system: str, user: str, *, temperature: float = 0.2,
                 max_tokens: int = 1024, grammar: str = "",
                 cancel: CancelToken = NEVER) -> str: ...

    def count_tokens(self, text: str) -> int | None: ...

    def info(self) -> ModelInfo: ...


class NullLLM:
    """No model. Everything that does not need one still works.

    This is the state on a laptop with the GPU cold, and it is a supported
    state rather than an error condition — blocks 1, 2, 2b and 5 of the
    build never call this class at all.
    """

    def complete(self, system: str, user: str, *, temperature: float = 0.2,
                 max_tokens: int = 1024, grammar: str = "",
                 cancel: CancelToken = NEVER) -> str:
        raise NoModelError(
            "this needs a language model and none is loaded. The craft "
            "measurements, the context budget, the fingerprint and the "
            "diff all work without one.")

    def count_tokens(self, text: str) -> int | None:
        return None

    def info(self) -> ModelInfo:
        return ModelInfo()


# ---------------------------------------------------------------------------
# retrieval
# ---------------------------------------------------------------------------


@dataclass
class Retrieved:
    """One passage a retriever thought was relevant."""

    text: str
    score: float = 0.0
    ref: str = ""
    section_id: str = ""
    order: int = 0


@runtime_checkable
class Retriever(Protocol):
    """Semantic or lexical search over the manuscript.

    ATK wires `SafeStore` here, whose embedders all run on the CPU by
    standing rule. That rule matters more in this workspace than anywhere
    else in ATK: the Red Thread re-indexes in the background while the
    author is writing, so an embedder on the card would compete with the
    writing model at exactly the moment the author is waiting on it.
    """

    def index(self, items: Iterable[Retrieved]) -> int: ...

    def query(self, text: str, top_k: int = 8) -> list[Retrieved]: ...


_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]+")


class KeywordRetriever:
    """A real BM25 index in the standard library. The hostless default.

    Not a placeholder. Retrieval in this workshop is mostly "find the
    passages that mention this subject", which is a lexical question, and
    BM25 answers it well enough that the Codex and the Red Thread are
    genuinely usable before an embedder exists. When ATK wires `SafeStore`
    in, this is replaced; when it does not, nothing silently returns [].
    """

    K1 = 1.5
    B = 0.75

    def __init__(self) -> None:
        self._docs: list[Retrieved] = []
        self._tokens: list[Counter] = []
        self._lens: list[int] = []
        self._df: Counter = Counter()

    def index(self, items: Iterable[Retrieved]) -> int:
        added = 0
        for item in items:
            toks = Counter(w.lower() for w in _WORD.findall(item.text))
            if not toks:
                continue
            self._docs.append(item)
            self._tokens.append(toks)
            self._lens.append(sum(toks.values()))
            for term in toks:
                self._df[term] += 1
            added += 1
        return added

    def clear(self) -> None:
        self.__init__()

    def query(self, text: str, top_k: int = 8) -> list[Retrieved]:
        if not self._docs:
            return []
        terms = [w.lower() for w in _WORD.findall(text)]
        if not terms:
            return []
        n = len(self._docs)
        avg = sum(self._lens) / n
        scored: list[tuple[float, int]] = []
        for i, toks in enumerate(self._tokens):
            score = 0.0
            for term in set(terms):
                tf = toks.get(term, 0)
                if not tf:
                    continue
                df = self._df.get(term, 0) or 1
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                norm = 1 - self.B + self.B * self._lens[i] / avg
                score += idf * tf * (self.K1 + 1) / (tf + self.K1 * norm)
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        out = []
        for score, i in scored[:top_k]:
            hit = self._docs[i]
            out.append(Retrieved(hit.text, score, hit.ref, hit.section_id,
                                 hit.order))
        return out


# ---------------------------------------------------------------------------
# the evidence ledger (O.W.L.)
# ---------------------------------------------------------------------------


@runtime_checkable
class Ledger(Protocol):
    """Mirror of accepted claims into ATK's O.W.L.

    Only ACCEPTED claims are mirrored. A ledger that receives a model's
    proposals is a ledger whose provenance means nothing, and provenance is
    the only reason to use one.
    """

    def available(self) -> bool: ...

    def observe(self, text: str, *, origin: str = "manuscript",
                source_ref: str = "") -> str: ...

    def recall(self, query: str) -> list[str]: ...


class NoLedger:
    """O.W.L. absent or off. The Codex degrades to a plain list."""

    def available(self) -> bool:
        return False

    def observe(self, text: str, *, origin: str = "manuscript",
                source_ref: str = "") -> str:
        return ""

    def recall(self, query: str) -> list[str]:
        return []


# ---------------------------------------------------------------------------
# speech
# ---------------------------------------------------------------------------


@dataclass
class Voice:
    name: str
    language: str = ""
    label: str = ""


@runtime_checkable
class Speech(Protocol):
    """Read-aloud. ATK wires Piper, which is CPU-only and near real time.

    The plan this was built from assumed diffusion TTS and pushed every
    chapter into a background queue for that reason. Piper changed the
    trade: a passage is effectively instant, so `speak` is an interactive
    call again, and `readaloud.chapter_jobs` is an option rather than the
    only shape. Both are still here, because listening to a chapter away
    from the screen is how proofreading by ear actually works.

    A PIPER VOICE SPEAKS ONE LANGUAGE. `Voice.language` is not decoration —
    an English voice handed a translated passage produces fluent nonsense
    that an operator who does not speak the language cannot hear.
    """

    def available(self) -> bool: ...

    def voices(self) -> list[Voice]: ...

    def speak(self, text: str, *, voice: str = "",
              out_path: str = "") -> str: ...


class NoSpeech:
    def available(self) -> bool:
        return False

    def voices(self) -> list[Voice]:
        return []

    def speak(self, text: str, *, voice: str = "", out_path: str = "") -> str:
        return ""


# ---------------------------------------------------------------------------
# progress and events
# ---------------------------------------------------------------------------


@runtime_checkable
class Events(Protocol):
    """Where progress goes. A forty-section sweep that says nothing for two
    minutes is indistinguishable from a hang, and ATK has shipped that bug
    before."""

    def emit(self, kind: str, message: str, **data: Any) -> None: ...


class SilentEvents:
    def emit(self, kind: str, message: str, **data: Any) -> None:
        return None


class CollectingEvents:
    """Keeps what it was told. The tests use it; so can a CLI."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def emit(self, kind: str, message: str, **data: Any) -> None:
        self.records.append((kind, message, data))

    def messages(self) -> list[str]:
        return [m for _k, m, _d in self.records]


# ---------------------------------------------------------------------------
# the clock
# ---------------------------------------------------------------------------


@runtime_checkable
class Clock(Protocol):
    def now(self) -> str: ...


class SystemClock:
    def now(self) -> str:
        return _dt.datetime.now().replace(microsecond=0).isoformat(" ")


class FixedClock:
    def __init__(self, stamp: str = "2026-01-01 00:00:00") -> None:
        self.stamp = stamp

    def now(self) -> str:
        return self.stamp


# ---------------------------------------------------------------------------
# the bundle
# ---------------------------------------------------------------------------


@dataclass
class Host:
    """Everything the workshop may ask of its host, in one object.

    Defaults are the working ones above, so `Host()` is a complete,
    functioning host with no model — which is exactly the configuration
    blocks 1, 2, 2b and 5 are meant to run in.
    """

    llm: Any = field(default_factory=NullLLM)
    retriever: Any = field(default_factory=KeywordRetriever)
    ledger: Any = field(default_factory=NoLedger)
    speech: Any = field(default_factory=NoSpeech)
    events: Any = field(default_factory=SilentEvents)
    clock: Any = field(default_factory=SystemClock)

    def has_model(self) -> bool:
        try:
            return bool(self.llm.info().name)
        except Exception:               # noqa: BLE001 - a host may raise
            return False
