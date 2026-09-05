# SPDX-License-Identifier: Apache-2.0
"""ATK's Port implementations. Destination: `atk/core/writing_host.py`.

**REFERENCE COPY, NOT THE SHIPPED ADAPTER — read this before fixing
anything here.** ATK carries its own
`atk/core/writing_host.py`, it does not import `adapters/` at all, and
the two have diverged: ATK's panel has since
grown Storyline, Draft and Author Styles pages this copy has never had
and is roughly three times the size. What survives here is the worked
example of the ports — the smallest complete host, useful for reading and
for writing a new one. A fix made here reaches nobody. Make it in ATK, and
mirror it back only if the example is worth keeping current.

**This file lives outside `writing_workshop/` on purpose.** It knows about
ATK; the engine must not. A test in the engine's own suite walks the
package and fails the build if anything under `writing_workshop/**` ever
imports `atk.*`, which is what keeps that one-directional and makes every
craft check, the assembler, the claims model and the fingerprint runnable
in a bare interpreter with no Qt and no GPU.

It is deliberately **Qt-free**. Everything that needs a widget lives in
`writing_panel.py`; this module takes and returns plain data, so it can be
driven from a `QRunnable` without knowing what thread it is on.

Three things worth reading before the code:

* **One ticket for a whole job.** Every model call goes through
  `ai_queue.hold`, and a multi-section sweep takes ONE ticket around the
  whole batch rather than one per section — the rule CyberWolf's ensemble
  established, and the reason a forty-section pass cannot interleave with
  a chat message halfway through.
* **The budget is measured, never declared.** `info()` reads the real
  usable context from `vram`, because ATK measured a 10-100x gap between
  what a GGUF header declares and what fits on a 16 GB card.
* **The retriever is the CPU embedder, by standing rule.** It matters more
  in this workspace than anywhere else in ATK: the Red Thread re-indexes
  in the background WHILE the author is writing, so an embedder on the
  card would compete with the writing model at exactly the moment the
  author is waiting on it.

Installation into ATK, in order, each step leaving the suite green:

    1. copy this file to `atk/core/writing_host.py`
    2. copy `writing_panel.py` to `atk/ui/writing_panel.py`
    3. add `WritingPanel` to `atk/ui/panels.py` and to `WORKSPACES`
    4. run ATK's full suite
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# The engine imports nothing from ATK, which is why this direction is safe.
from writing_workshop.ports import (Host, KeywordRetriever, ModelInfo,
                                    Retrieved, Voice)

#: Held back for the model to answer in.
RESERVE_OUTPUT = 1024


# ---------------------------------------------------------------------------
# the language model
# ---------------------------------------------------------------------------


class ATKLLM:
    """`LLMEngine`, as the workshop's LLM port."""

    def __init__(self, engine, settings: dict | None = None) -> None:
        self.engine = engine
        self.settings = settings or {}
        self._info: ModelInfo | None = None
        self._info_for = ""

    # -- generation -------------------------------------------------------

    def complete(self, system: str, user: str, *, temperature: float = 0.2,
                 max_tokens: int = 1024, grammar: str = "",
                 cancel=None) -> str:
        from atk.core import ai_queue
        from atk.core.llm_engine import split_think
        if not getattr(self.engine, "is_loaded", False):
            from writing_workshop.errors import NoModelError
            raise NoModelError(
                "no model is loaded — pick one in Setup. The craft "
                "measurements, the context budget, the fingerprint and the "
                "diff all work without one.")
        messages = []
        if system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        chunks: list[str] = []
        with ai_queue.hold("Writing Workshop"):
            for piece in self.engine.chat_stream(
                    messages, temperature=temperature,
                    max_tokens=max_tokens, grammar=grammar or None):
                chunks.append(piece)
                if cancel is not None and cancel.is_set():
                    break
        # A reasoning model's <think> block is not the answer, and pasting
        # one into a diff surface would offer the author its scratch work
        # as prose.
        _thought, answer = split_think("".join(chunks))
        return answer.strip()

    # -- token counting ---------------------------------------------------

    def count_tokens(self, text: str) -> int | None:
        """The loaded model's own count, or None. NEVER a guess.

        The assembler can honestly call its own heuristic an estimate and
        cannot honestly call ours one, so a failure here returns None and
        lets it say "estimated" rather than quietly reporting a wrong
        number as exact.
        """
        llm = getattr(self.engine, "_llm", None)
        if llm is None or not text:
            return None
        try:
            return len(llm.tokenize(text.encode("utf-8", "replace"),
                                    add_bos=False, special=False))
        except Exception:                             # noqa: BLE001
            return None

    # -- what the meter shows ---------------------------------------------

    def info(self) -> ModelInfo:
        if not getattr(self.engine, "is_loaded", False):
            return ModelInfo()
        path = str(getattr(self.engine, "model_path", "") or "")
        if self._info is not None and self._info_for == path:
            return self._info
        meta = dict(getattr(self.engine, "metadata", {}) or {})
        info = ModelInfo(
            name=meta.get("model_file") or Path(path).name or "model",
            usable_tokens=int(meta.get("n_ctx") or 0),
            exact_token_counts=self.count_tokens("probe") is not None)
        self._fill_from_vram(info, path, meta)
        self._info, self._info_for = info, path
        return info

    @staticmethod
    def _fill_from_vram(info: ModelInfo, path: str, meta: dict) -> None:
        """Declared context, layer split and the RAM bill.

        Everything here is best-effort: a missing GGUF or an absent GPU
        leaves the meter honest ("Estimated — no GPU reading was
        available") rather than silently confident.
        """
        try:
            from atk.core import vram
            from atk.core.gguf_meta import read_gguf_metadata
        except Exception:                             # noqa: BLE001
            return
        try:
            gguf = read_gguf_metadata(path)
            info.declared_tokens = int(
                gguf.kv.get(f"{gguf.architecture}.context_length") or 0)
            info.total_layers = int(
                gguf.kv.get(f"{gguf.architecture}.block_count") or 0)
        except Exception:                             # noqa: BLE001
            pass
        try:
            plan = vram.plan_gpu_layers(path, n_ctx=info.usable_tokens
                                        or 8192)
            info.layers_on_card = int(plan.n_gpu_layers)
            info.total_layers = int(plan.total_layers or info.total_layers)
            info.host_mb = float(getattr(plan, "host_mb", 0.0) or 0.0)
            info.measured = True
        except Exception:                             # noqa: BLE001
            info.layers_on_card = int(meta.get("n_gpu_layers") or 0)


def alternatives(settings: dict | None = None, want: int = 0,
                 limit: int = 3) -> list[tuple[str, int]]:
    """Models in the folder that would hold more, biggest window first.

    The third line of the Budget Meter — *"Load Qwythos-9B for 75,448 and
    the whole manuscript fits."* Computed on demand, never at start-up:
    reading every GGUF header in the folder is fast but not free, and
    nothing should pay for it before the author asks what else would fit.
    """
    try:
        from atk.core import llm_engine, vram
    except Exception:                                 # noqa: BLE001
        return []
    out: list[tuple[str, int]] = []
    for path in llm_engine.discover_models(settings):
        try:
            gguf = vram.read_gguf_metadata(path)
            declared = int(
                gguf.kv.get(f"{gguf.architecture}.context_length") or 0)
        except Exception:                             # noqa: BLE001
            continue
        best = 0
        for candidate in (declared, 131072, 65536, 32768, 16384, 8192):
            if not candidate or candidate > declared:
                continue
            try:
                plan = vram.plan_gpu_layers(str(path), n_ctx=candidate)
            except Exception:                         # noqa: BLE001
                continue
            if plan.n_gpu_layers > 0:
                best = candidate
                break
        if best > want:
            out.append((path.name, best))
    out.sort(key=lambda pair: -pair[1])
    return out[:limit]


# ---------------------------------------------------------------------------
# retrieval
# ---------------------------------------------------------------------------


class ATKRetriever:
    """`SafeStore`, as the workshop's Retriever port.

    Falls back to the engine's own BM25 index when the store is absent or
    its embedder cannot load — which is a real state on a fresh install and
    must not turn every retrieval into an empty list.
    """

    TIER = "manuscript"

    def __init__(self, store, project_name: str = "manuscript") -> None:
        self.store = store
        self.project = project_name
        self._fallback = KeywordRetriever()
        self._using_fallback = store is None

    def index(self, items) -> int:
        rows = list(items)
        if self.store is None:
            return self._fallback.index(rows)
        added = 0
        for item in rows:
            try:
                self.store.ingest_text(
                    item.text, source=f"{self.project}:{item.ref}",
                    tier=self.TIER)
                added += 1
            except Exception:                         # noqa: BLE001
                self._using_fallback = True
                return added + self._fallback.index(rows[added:])
        return added

    def query(self, text: str, top_k: int = 8) -> list[Retrieved]:
        if self.store is None or self._using_fallback:
            return self._fallback.query(text, top_k)
        try:
            hits = self.store.query(text, top_k=top_k,
                                    tiers=(self.TIER, "documents"))
        except Exception:                             # noqa: BLE001
            self._using_fallback = True
            return self._fallback.query(text, top_k)
        return [Retrieved(text=h.text, score=float(h.score),
                          ref=h.source.split(":", 1)[-1]) for h in hits]


# ---------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------


class ATKLedger:
    """O.W.L., as the workshop's Ledger port. No fallback store.

    Bill, 2026-08-28: *"use owl."* Defensible because `install.bat` clones
    and installs OWL unconditionally and `subsystems.ledger` has defaulted
    ON since 2026-08-14. Building a second claims store against the
    possibility of OWL being absent would be building for a state ATK does
    not ship — so the Codex simply degrades to a plain list, the same way
    every other O.W.L. surface does.
    """

    def __init__(self, settings: dict | None = None) -> None:
        self.settings = settings or {}

    def available(self) -> bool:
        try:
            from atk.core import ledger
            return bool(ledger.enabled(self.settings))
        except Exception:                             # noqa: BLE001
            return False

    def observe(self, text: str, *, origin: str = "manuscript",
                source_ref: str = "") -> str:
        try:
            from atk.core import ledger
            return ledger.record(text, origin=origin,
                                 source_ref=source_ref,
                                 settings=self.settings)
        except Exception as exc:                      # noqa: BLE001
            return str(exc)

    def recall(self, query: str) -> list[str]:
        try:
            from atk.core import ledger
            handle = ledger.writer().handle(self.settings)
            if handle is None:
                return []
            ok, payload = handle.recall(query)
        except Exception:                             # noqa: BLE001
            return []
        if not ok:
            return []
        if isinstance(payload, (list, tuple)):
            return [str(p) for p in payload]
        return [str(payload)]


# ---------------------------------------------------------------------------
# speech
# ---------------------------------------------------------------------------


class ATKSpeech:
    """Piper, as the workshop's Speech port.

    Piper is CPU-only and near real time, so a passage is an interactive
    call. **A Piper voice speaks ONE language**, which is why `voices()`
    carries the language: an English voice handed a translated passage
    produces fluent nonsense that an operator who does not speak the
    language cannot hear.
    """

    def __init__(self, settings: dict | None = None) -> None:
        self.settings = settings or {}

    def available(self) -> bool:
        """Any voice at all, of either kind. Read off the disk."""
        try:
            from atk.core import voices as registry
            return bool(registry.list_voices())
        except Exception:                             # noqa: BLE001
            return False

    def voices(self) -> list[Voice]:
        """Cloned voices first, then Piper. Both kinds, one list.

        A cloned voice reports no language, and that absence is honest:
        Chatterbox copies a voice from a clip rather than a language's
        phonemes, so it will attempt anything. A Piper voice speaks exactly
        one language and says which — which is what stops an English voice
        being handed a translated passage and producing fluent nonsense.
        """
        try:
            from atk.core import voices as registry
            return [Voice(name=v["name"], language=v.get("language", ""),
                          label=v.get("label", "")) for v in
                    registry.list_voices()]
        except Exception:                             # noqa: BLE001
            return []

    def speak(self, text: str, *, voice: str = "",
              out_path: str = "") -> str:
        """Speak a passage. Never raises, and never returns "" merely
        because the requested voice is unavailable — the service walks a
        chain and reports which voice actually spoke."""
        try:
            from atk.core import audio_client
        except Exception:                             # noqa: BLE001
            return ""
        try:
            result = audio_client.synthesize(
                text, out_path=out_path or None, voice=voice)
        except Exception:                             # noqa: BLE001
            return ""
        return str(result.get("path") or "")

    def language_of(self, voice: str) -> str:
        try:
            from atk.core import piper
            return piper.language_of(voice)
        except Exception:                             # noqa: BLE001
            return ""


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


class ATKEvents:
    """Progress into ATK's status bar, Cognitive Flow and log.

    A forty-section sweep that says nothing for two minutes is
    indistinguishable from a hang, and ATK has shipped that bug before.
    """

    def __init__(self, ctx=None, logger=None) -> None:
        self.ctx = ctx
        self.logger = logger

    def emit(self, kind: str, message: str, **data: Any) -> None:
        if self.logger is not None:
            try:
                self.logger.info("%s: %s", kind, message)
            except Exception:                         # noqa: BLE001
                pass
        ctx = self.ctx
        if ctx is None:
            return
        try:
            if kind == "progress" and data.get("n"):
                sink = getattr(ctx, "progress_sink", None)
                if sink is not None:
                    sink(message, int(data.get("i", 0)), int(data["n"]))
            setter = getattr(ctx, "set_status", None)
            if setter is not None:
                setter(message)
            flow = getattr(ctx, "flow_event", None)
            if flow is not None and kind in ("step", "warning"):
                flow(message, kind)
        except Exception:                             # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# the bundle
# ---------------------------------------------------------------------------


def build_host(ctx, *, project_name: str = "manuscript",
               logger=None) -> Host:
    """Everything the workshop may ask of ATK, in one object.

    Built from `ctx` alone so a panel, a test and a headless script all get
    the same host. Every port here degrades on its own: no model, no
    store, no ledger and no voice is a supported configuration, and the
    craft measurements do not care about any of them.
    """
    settings = dict(getattr(ctx, "settings", {}) or {})
    return Host(
        llm=ATKLLM(getattr(ctx, "engine", None), settings),
        retriever=ATKRetriever(getattr(ctx, "store", None), project_name),
        ledger=ATKLedger(settings), speech=ATKSpeech(settings),
        events=ATKEvents(ctx, logger))
