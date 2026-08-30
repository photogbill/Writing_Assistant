# ATK Writing Workshop — build plan

> **READ THIS FIRST — BUILT 2026-08-29/30, and two things in here are
> now out of date.** The workshop is built: its own repo in this
> folder, vendored into ATK. **§6 and decision 5 are SUPERSEDED** —
> F5-TTS has been removed from ATK and Piper is the only speech
> engine, so the read-aloud trade-off both sections reason about no
> longer exists. Everything else here held up and was built as
> written.

*Extracted from `ATK/FUTURE_PLANS.md` on 2026-08-29. That file is the plan of record; this is a standalone copy of the Writing Workshop section, §§1–11 including §4b The Context Architecture.*

*Developed from Bill's original brief (`Here is the comprehensive, end-to-e.txt`, in this folder) — scoped to large technical manuals, books, documents and novels. **Design only: none of this is built yet.** The two `vram.py` fixes that came out of measuring for it (the 52x hybrid KV over-estimate and the under-offloading layer planner) ARE built and live in ATK.*

---

## ✍️ WRITING WORKSHOP — long-form documents, fiction and technical — 🔴 SCOPED 2026-08-28

Bill brought a build plan for a writing assistant (`Here is the comprehensive
endtoe.txt`) and asked for it to be developed rather than built. He then set
the scope: *"I don't want to reinvent the wheel, only give ATK the best
writing assistant possible. One that can help write large technical manuals,
books, documents, etc."*

This section is that rewrite. The original is a competent generic plan; it was
written without knowledge of ATK, and that shows in two ways — **most of it is
already built**, and the parts that are not are ordered worst-first.

### The thesis change, and everything follows from it

The original plan optimises for **generation**: rewrite this, expand that,
dictate here. That is the commodity half of the problem. Every writing tool on
earth has a "make it better" button, they all produce the same flattened
prose, and none of them is the reason anybody would keep ATK's version.

The differentiating capability is **memory and measurement**:

> **A workshop that knows the whole document better than the author can hold
> in their head, and never writes in the author's place.**

That is the right thesis for a 200-page manual and a 120,000-word novel alike,
because they share a failure mode. Nobody can hold either in working memory,
so both fail the same way: **the sword is bronze in chapter 3 and steel in
chapter 17; the torque spec is 40 Nm in §4.2 and 45 Nm in the appendix.** The
same defect, and the only tool that can catch it is one that has read
everything and remembers where each claim came from.

ATK is unusually well placed for this, because that is *already what it does*.
Extraction with provenance, an evidence ledger that tracks what superseded
what, a graph of entities and relationships, temporal edges, a semantic store
— every one of those was built for intelligence work and every one of them is
the right machine for a long document. **The writing workshop is ATK's
existing spine pointed at a manuscript.**

### What this changes about the build order

The original order is shell → RAG → agents → VRAM → polish. Reordered:

**Measurement comes first, and needs no model at all.** A large part of what a
serious writer or technical author needs is arithmetic: reading level,
terminology drift, dropped threads, echo detection, step-numbering integrity,
cross-reference validity, sentence-length distribution. It is fast, it runs on
a dead battery, and **it cannot hallucinate** — which is what makes the rest of
the tool believable. A workshop whose first useful answer comes from a model
is a workshop the author has to fact-check; one whose first answers are
measurements has earned the benefit of the doubt by the time a model speaks.

Assisted editing goes LAST, because it is the commodity part and the one most
likely to damage the thing it is helping with.

### 1. What the plan proposes that ATK already has — VERIFIED 2026-08-28

Checked against the source, not remembered. Roughly **three quarters of the
original plan is already in the tree**, and building it as written would give
ATK a second copy of its own subsystems.

| The plan proposes | ATK already has | Where |
|---|---|---|
| Python + PySide6 desktop UI | the entire application | `atk/ui/` |
| `llama.cpp` CUDA, VS C++ build | the source-build installer and engine | `install.bat`, `llm_engine.py` |
| Embeddings for RAG | four embedder backends, GGUF included | `vector_store.py`, `embed_engine.py` |
| ChromaDB or FAISS | `SafeStore` + `Hit` retrieval | `vector_store.py:230` |
| "Split notes by headers" | `chunk_text` — paragraphs, then sentences, tables kept intact | `vector_store.py:63` |
| `whisper.cpp` dictation + hotkey | faster-whisper service + `VoiceRecorder` + `MeetingRecorder` | `audio_service.py`, `ui/voice.py` |
| Piper TTS read-aloud | F5-TTS with voice cloning and a voice registry | `audio_service.py`, `core/voices.py` |
| Persona swapping for editor roles | personas, MoE ladder, Thinking Workshop, Athena | `personas.py`, `workshop.py`, `athena.py` |
| Rolling summarisation of old context | conversation compression with a visible summary | `conversation.py:315` |
| VRAM / layer management | `plan_gpu_layers` against measured free VRAM | `vram.py:183` |
| Auto-extraction of new entities | extraction + Pass-0 triage + the categorise-Other pass | `extract.py`, `triage.py` |
| "Chat with characters" from lore cards | a `characters` table: name, voice type, history, notes | `cognitive_library.py:341` |
| — | **spell check with a personal dictionary** (the plan omits it) | `ui/spellcheck.py` |
| — | **Markdown → .docx export** (the plan omits it) | `reports.py:388` |

**Genuinely new, and therefore what this section is actually about:** the
editor shell itself, version branching, the diff/accept-reject surface, and
the continuity engine — which the original mentions in one bullet and is the
most valuable idea in it.

### 2. Four faults in the original, and what to do instead

**2a. `Qwen3-Embedding-8B` is the wrong size — but not for the reason I first
gave.** This argument's premise moved on 2026-08-28, when Bill ruled that
**every embedder in ATK runs on the CPU**, so it is restated rather than left
standing on a fact that changed.

The original objection was VRAM: an 8B embedder at Q8 is ~8–9 GB, and with a
7–9B writing model and a long-context KV cache the 16 GB ceiling is gone
before the manuscript loads. **On the CPU that objection disappears** — an 8B
embedder costs zero VRAM and ~8.5 GB of the 64 GB of system RAM, which fits.

What is left is throughput, and it still decides the answer. The Red Thread
embeds continuously in the BACKGROUND while the author writes, and an 8B
forward pass on CPU is roughly an order of magnitude slower than a 0.6B —
enough to keep cores busy through a writing session for retrieval quality
nobody would notice. **Keep Qwen3-Embedding-0.6B-Q8_0** (`config.py:80`,
~640 MB) for the live path.

The more interesting consequence: CPU-only makes a large embedder *possible*
where it used to be excluded. A one-off deep index of a finished manuscript —
run once, overnight, at higher quality — is now a real option costing RAM and
time rather than the card. Worth remembering if retrieval ever disappoints;
not worth building first.

**2b. The KV-cache mechanism described does not exist.** The plan says to
*"offload older context layers to system RAM while keeping the active scene
context pinned in the 16 GB of VRAM."* Verified against llama-cpp-python
0.3.35: the control is **`offload_kqv: bool`** — one boolean for the whole
cache. There is no per-token-range or "older context" granularity; the cache
is contiguous per layer and it is all in VRAM or all in RAM. Someone would
spend a day hunting for a flag that was never there.

What actually exists and does the job: `n_keep` pins the head of the context,
context shifting discards from the middle, and an **assembler that packs to
the budget it actually has** — §4b, which replaces both this bullet and the
plan's rolling-summarisation bullet. Summarisation survives as one BAND in
that assembler rather than as the headline mechanism: the compression fallback
for what full prior text could not carry, not the first answer.

**2c. Git line-diffs are wrong for prose.** A paragraph is one line, so
changing one word renders as a whole-paragraph rewrite and the diff is
useless — which is the one thing a version feature exists to provide. The fix
is **sentence-level diffing**: split to sentences, diff those, rejoin.
(`vector_store.chunk_text` already splits prose on sentence boundaries; the
same boundary logic serves here.)

And the plan's *"invisibly to the user"* is the wrong instinct. Hidden version
control is a data-loss trap: when it goes wrong the author has no model of
what happened and no vocabulary to ask about it. **Make it visible and name
versions in the author's own words** — "the version where she leaves", "draft
for legal review" — not `a3f91c2`.

**2d. Prompt-swapping is not isolation.** The plan isolates personas by
swapping system prompts against one loaded model. ATK learned otherwise
building Athena: isolation is architectural, and a shared conversation and KV
cache leak between voices whatever the system prompt says. It matters here
because the whole point of a second opinion is that it is *second*. Reuse the
Thinking Workshop's isolation, which already solves this.

### 3. The workspace

**`Writing Workshop`**, its own sidebar position, placed **third — directly
after the Analysis Suite** so it sits inside the nine entries the rail shows
before scrolling. See §9.1 for why this is a workspace and not a sub-tab, and
for the wider point about `WORKSPACES` order that falls out of it.

Six sub-tabs, in the order the work happens:

| Tab | What it is |
|---|---|
| **Manuscript** | The editor and the structure tree. Files on disk, never a database. |
| **Codex** | The story bible / terminology register. Claims with sources. |
| **Continuity** | Contradictions, dropped threads, chronology, the Red Thread. |
| **Craft** | The measurements. No model required. |
| **The Room** | Critics and rewrites, non-destructively. |
| **Versions** | Named drafts and sentence-level diffs. |

Everything is `.md` on disk in a project folder, exactly as the original says
— that instinct is right and is worth restating: **the manuscript is never
locked inside ATK.** A tool that holds an author's book hostage in a SQLite
blob is one they cannot leave, and one they will not trust with the book.

### Phase 0 — the shell, and reading what is there

The editor widget, the structure tree (headings → an outline that is also
navigation), and ingest. Reuse `chunk_text`, `SafeStore`, and the project
model that already exists in `projects.py`.

One decision that pays for itself: **the outline is derived, never stored.**
Headings in the file are the structure. Nothing to get out of sync, and the
author can reorganise in any editor they like and ATK follows.

### Phase 1 — Craft: everything measurable, with no model loaded

The phase that makes the tool trustworthy, and the one the original plan does
not have at all. All of it is arithmetic over the text: fast, repeatable,
offline, and **incapable of inventing a finding**.

**Shared (fiction and technical):**
- Sentence- and paragraph-length distributions, per section and over the whole
  document — the shape, not just the mean; rhythm lives in the variance.
- **Echo detection**: a distinctive word reused within N words. The single
  highest-value cheap check there is, and invisible to the author who wrote
  both instances an hour apart.
- Readability (Flesch–Kincaid and friends) per section, with the caveat that
  it is a proxy and stated as one.
- Adverb and filter-word density (`felt`, `saw`, `realised`, `noticed`,
  `began to`) — the standard craft flags, counted rather than opined about.
- Passive-voice rate.
- Opening-word variety: how many consecutive sentences start `The`, `He`, `It`.

**Technical documents:**
- **Terminology drift** — the same concept under three names. The defect that
  makes a manual untrustworthy, and pure measurement: cluster the noun phrases,
  show the clusters with more than one surface form.
- **Undefined-term use** — a term used before the glossary defines it, or
  never defined at all.
- **Acronym first-use expansion** — every acronym expanded on first appearance,
  and only the first.
- **Cross-reference integrity** — does §4.2 exist; does Figure 7 exist; is
  anything referenced that was deleted. Deterministic, and it is the check
  that breaks silently on every edit pass.
- **Step-numbering integrity** in procedures — gaps, duplicates, restarts.
- **Sentence length inside numbered steps.** A 40-word instruction is an
  instruction somebody will get wrong at 3am. Flag long steps specifically,
  not long sentences generally.
- **Normative language register** — `shall` / `should` / `may` used
  consistently, because in a specification those are not stylistic choices.
- **Unit and number consistency** — the same quantity given two values
  anywhere in the document. This one catches the torque-spec class of defect
  before any model is involved.

**Fiction:**
- **Pacing curve** — scene and chapter lengths over the document, drawn. A
  novel's shape is visible in it and nowhere else.
- **Dialogue-to-narration ratio**, per chapter.
- **POV drift** — pronoun and name distribution per scene, flagging a scene
  that changes whose head it is in without a break.
- **Character presence over time** — who is on the page, chapter by chapter.
  Somebody vanishing for eleven chapters is usually a mistake and always
  worth seeing.
- **Dialogue tag habits** — `said` versus the ninety alternatives.


### 4b. THE CONTEXT ARCHITECTURE — written for the hardware, not for 2048 tokens

Bill, 2026-08-28: *"I designed that in an era of very small context windows,
but we're no longer in that era… construct the most flexible and capable
solution possible."*

Right, and the interesting part is what "no longer in that era" actually means
on a 16 GB card. **Measured against his own models** (`vram.read_gguf_metadata`
+ `kv_cache_mb`, 2026-08-28, 16 GB card, 1 GB headroom):

| Model | file | declares | **fits** |
|---|---|---|---|
| DeepSeek-R1-Distill-8B Q4_K_M | 4.58 GB | 131k | **85,337** |
| Qwen3.8-9B Q4 | 4.82 GB | 262k | **83,372** |
| Qwythos-9B *(“1M” in the name)* | 5.79 GB | 1,049k | **75,448** |
| DeepSeek-V4-Pro-9B Q5_K_M | 6.19 GB | 262k | **70,013** |
| Parable-Qwen3-8B Q6_K | 6.26 GB | 41k | **63,613** |
| Ministral-3-14B Q4_K_M | 7.67 GB | 262k | **48,016** |
| Magistral-Small-24B Q4_K_M | 13.35 GB | 41k | **10,813** |
| Slimaki-24B / Devstral-24B | 13.35 GB | 131k / 393k | **~10,800** |
| Muse-Glimmer-30B Q4_K_M | 15.77 GB | 131k | **0** |
| Qwen3.6-27B Q4_K_L | 17.63 GB | 262k | **0** (will not load) |

Two things fall out, and they shape everything below.

**The declared number is not the number.** Qwythos says 1M in its filename and
gets 75k. The gap is 10–100× and it is invisible until something fails.

**Context is a BUDGET THAT VARIES BY 8× DEPENDING ON WHICH MODEL IS LOADED.**
So the flexible design is not "assume big context" and it is not "assume
small". It is a system that **adapts to whatever budget it has and says what
it did.** That single idea is the architecture.

*(A bug found while measuring, and **FIXED 2026-08-28**. `kv_cache_mb` was
over-estimating hybrid Mamba/attention models by **52×** — Nemotron3-Nano-4B
was reported at 840 MB per 1k tokens against a real 16, which at an 8k context
reserved 6.5 GB of a 16 GB card for a cache that was never going to exist. It
erred safe, so it never caused an OOM; it cost speed silently, through
`plan_gpu_layers` spilling layers to the CPU to make room.*

*The root cause was one line lower than it looked. `nemotron_h` writes
`attention.head_count_kv` as **one entry per layer** — 42 entries, only four of
them non-zero — and `gguf_meta._read_value` was skipping every array unread,
on the reasoning that only scalar config keys mattered. That was true until a
hybrid landed in the models folder. The header carried the answer the whole
time and the parser was discarding it, so `kv_cache_mb` could not tell "this
model has no per-layer detail" apart from "we did not read it".*

*Fixed in both places: `gguf_meta` now keeps numeric arrays up to 4096 entries
and still skips the tokenizer-sized ones; `kv_cache_mb` **sums over layers**
instead of multiplying by `block_count`, and adds the constant recurrent state
the Mamba layers hold (~81 MB, and it does not grow with context). Every
non-hybrid model in the folder reports exactly what it did before — Magistral
160 MB/1k, Glimmer 52 — and `test_reasoning.py` now pins the hybrid case at
107 checks.)*

#### What 64 GB of RAM changes — and what it does not

Bill, same day: *"I don't mind offloading and I have 64 GB system RAM. If that
helps."* It does, and not in the way the offer implies.

**First, the mechanism, verified against llama.cpp source rather than assumed.**
`src/llama-kv-cache.cpp` chooses the cache buffer PER LAYER:

```cpp
ggml_backend_buffer_type_t buft = ggml_backend_cpu_buffer_type();
if (offload) {
    auto * dev = model.dev_layer(il);
    buft = ggml_backend_dev_buffer_type(dev);
}
```

and `src/llama-model.cpp` assigns the first `(n_layer - n_gpu_layers)` layers to
the CPU device. **A layer spilled to RAM takes its cache with it.** So spilling
buys VRAM twice over — the layer's weights *and* the layer's slice of the cache.
That is why the numbers move as far as they do.

**The measurement.** Same 16 GB card, same 1 GB headroom, but allowing a quarter
of the layers to sit in RAM:

| Model | all on card | **≥75% on card** | costs |
|---|---|---|---|
| **Muse-Glimmer-30B** | **0** *(will not load)* | **91,253** | 5.3 GB |
| **Qwen3.6-27B** | **0** *(will not load)* | **10,229** | 5.2 GB |
| **Magistral-Small-24B** | 10,813 | **40,960** *(its declared max)* | 4.7 GB |
| Slimaki-24B / Devstral-24B | 10,813 | **45,718** | 5.3 GB |
| Ministral-3-14B | 48,016 | 82,011 | 5.2 GB |
| DeepSeek-R1-8B | 85,337 | 127,435 | 5.1 GB |
| Qwythos-9B | 75,448 | 117,845 | 5.2 GB |
| Parable-Qwen3-8B | 40,960 | 40,960 *(already at its max)* | — |

**Read the third column.** Every row costs about **five gigabytes**. Not fifty.
At a fixed 25% spill the RAM bill is dominated by a quarter of the model
weights, and his largest model is 17.6 GB. So the honest answer to *"I have
64 GB, does that help?"* is: **the 64 GB was never the constraint — 8 would
have done.** What actually helps is the *willingness to offload*, which is a
different thing he also offered and which costs speed, not memory.

Push further and it keeps going — Glimmer reaches its full 131,072 at 67% on
card, Devstral reaches 351,550 at 22% — but 22% on the card is a model running
mostly on the CPU, and the RAM bill finally does bite (52 GB). The ≥75% column
is the one to design against.

**Three things this changes.**

**1. Glimmer stops being a dead entry.** It is the best prose model in the
folder and the table said `0`. At 75% on card it gets 91k — more than the
drafting stage will ever need. The routing table below can name it.

**2. The routing table gains a third axis: read-heavy vs write-heavy.** It
currently routes on context need and capability. Offloading adds a dimension,
because prefill and generation degrade *completely differently* when layers sit
in RAM. Generation is memory-bandwidth-bound and pays the penalty on every
single token; prefill is compute-bound, batched, and paid once — and with the
stable-first ordering above, often not paid at all. So:

| Pass | Shape | Offload? |
|---|---|---|
| Claim extraction | reads 4k, writes ~200 | **freely** — prefill-dominated |
| Summarise a section | reads 4k, writes ~150 | **freely** |
| Continuity sweep | reads 75k, writes ~500 | **freely** — the extreme case |
| Draft a section | reads 8k, writes ~2000 | **no** — the operator is watching |

Every *map* pass in the map-reduce design is read-heavy. They are already batch
jobs through `render_queue.py`. **The whole map phase can run on a heavily
offloaded model and nobody waits** — the same argument that put chapter
narration in the render queue rather than in the editor.

*The one number here that is NOT measured is the speed penalty itself.* The
argument is from bandwidth ratios, not from Bill's hardware. It should be timed
before the routing defaults are set, and that is a ten-minute job once the
Workshop can run a pass at all.

**3. The Budget Meter gains a second line — the price, not just the ceiling.**
Context used to be a hard wall; now it is a purchase. The meter has to say what
the operator is spending:

> **Magistral-Small-24B · 40,960 tokens usable · 28 of 40 layers on the card.**
> 6.1 GB in system RAM. Drafting will be slower than at 10,813.
> *Ask for 8k instead and it goes fully on the card.*

Without that line the operator raises the context, everything gets mysteriously
slower, and nothing connects the two.

*(Found while doing this, and **FIXED**: `plan_gpu_layers` could not have
produced any of the table above. It subtracted the **whole** cache from the
VRAM budget before working out the split — wrong, because the spilled layers'
cache is spilled too, and circular, because the charge depends on the split it
is being used to compute. It reserved card memory for a cache that would live
in RAM and then under-offloaded to pay for it: Magistral at 40,960 planned
**22** of 40 layers on the card when **28** fit, Glimmer at 131k planned 23 of
52 when 31 fit. Both errors cost speed in exactly the situation where the
operator had asked for more context. Now solved directly — walk the layer count
down and take the first split whose weights and cache both fit — which is also
exact for hybrids, where per-layer cache cost is not uniform. `LayerPlan` gained
a `host_mb` field and the reason line now names the RAM bill, because once
spilling is a choice rather than a failure the operator is spending a second
resource and should see it. 15 new checks in `test_reasoning.py`, 122 total.)*

#### The Context Assembler — a knapsack, not a template

The original plan (and every plan of that era) specified a fixed prompt
string: *summary + RAG + previous 1000 words + request*. Replace it with an
assembler that takes **candidates** and a **budget** and packs by
**value per token**, because that is what the problem actually is.

Each candidate carries its content, its token cost, a priority band, and *the
reason it is there* — the reason being what lets the manifest below be
written.

| Band | What | Typical cost | Why it is priced this way |
|---|---|---|---|
| 0 · Invariant | style card, document-type rules, the section's own brief | ~400 | Applies to every request. If band 0 does not fit, **refuse and say so** rather than dropping the thing that defines the work. |
| 1 · Immediate | the section being written, and its two neighbours | 3–6k | You cannot write a section without it. |
| 2 · Governing claims | Codex claims that constrain THIS section, retrieved | ~50 each | The highest value-per-token in the system: twenty claims is a thousand tokens and it is the difference between consistent and not. |
| 3 · The spine | the complete outline | ~800 for a 40-section manual | Absurdly cheap, globally useful. It is what stops section 31 restating section 7. |
| 4 · Prior text | as much real prose as fits, nearest-first | 50k+ | Real value, low marginal value beyond the neighbours. |
| 5 · Summaries | one paragraph per completed section | ~150 × n | The compression fallback for everything band 4 could not take. |

Bands 0–3 total **under 8k tokens** for a substantial manual. That fits in
*every* model in the table above, including Magistral at 10,813. Bands 4 and 5
are where a big-context model earns its keep. **This is why the design works
at both ends of an 8× range instead of picking one.**

#### The ordering rule that only matters now: keep the prefix stable

`Llama.generate()` reuses the KV cache for the longest prefix shared with the
**previous call** — verified in llama-cpp-python 0.3.35, and it needs no
explicit cache to do it. In a 2048-token world that saved nothing worth
naming. At 10k tokens on a 24B it is the difference between a seconds-long
prefill on every request and none at all.

So assembled context is emitted **stable-first, volatile-last**:

```
[style card] [document rules] [outline] [prior text / summaries]   ← stable across a session
[claims retrieved for THIS section] [the section] [the request]    ← changes every call
```

This resolves a conflict rather than ignoring it. Cache efficiency wants the
stable material first; **long-context attention degradation** ("lost in the
middle") wants the most decision-relevant material *last*, nearest the
question. Those pull in opposite directions only if you assume the important
material is also the stable material — and it is not. The bulk (outline, prior
text) is stable and general; the critical part (the claims governing this
exact section, the request) is volatile and specific. Stable-first and
important-last are the same ordering.

#### Model routing — the capability the old era could not have

The table says the operator faces a trade: **a 24B with one chapter of
context, or a 9B with most of a book.** That is only a dilemma if one model
has to do everything. It does not — ATK already swaps models mid-job for
CyberWolf's ensemble (`ATKModelSwap`), and the whole batch takes one ticket in
the shared AI queue so nothing interleaves against a half-swapped model.

So the stages get routed by what they actually need:

| Stage | Needs | Wants | Sensible route |
|---|---|---|---|
| Outline / scaffold | reasoning; input is a brief, not a manuscript | quality | **24B @ 10k** — the small window is irrelevant here |
| Draft a section | prose quality + local context | both | **14B @ 48k** |
| Continuity sweep | the whole document in view; judgement is comparison, not style | context | **9B @ 75k** |
| Claim extraction | structured output, short | speed | **4–8B**, grammar-constrained |
| Style scoring, craft metrics | — | — | **no model at all** |

An operator who never touches this gets one model for everything and it works.
An operator who configures a route gets a 24B writing prose and a 9B holding
the whole manuscript for the continuity pass — on the same 16 GB card, in one
queued job. **That is the "most capable" answer, and it exists because ATK
already built the swap for something else.**

#### The document never has to fit

The framing "a 200-page manual does not fit in any model you own" is true and
was the wrong thing to worry about. Whole-document work is **map-reduce**, not
one enormous prompt:

- **Map:** extract claims / measure / summarise **per section**, each pass
  needing only that section plus band 0. Works at 10k as well as at 75k.
- **Reduce:** compare the claims against each other. That is an **indexed
  lookup over a table**, not an inference call.

A 40-section manual is 40 small passes and a join. It is also exactly the
shape `render_queue.py` already has — queue it, walk away, come back to a
continuity report. The context window stops being a ceiling on document size
and becomes a ceiling on *how much of one pass* is visible at once, which is a
much lower bar.

#### Structure by grammar, not by parsing

Bill's own 2023-era `processor.py` parsed the model's markdown with
`line.startswith('## ')`, and a model that wrote `##Intro` produced **zero
sections and an empty document, silently** (measured). The modern answer is
not a better parser — it is **not needing one**. ATK has GBNF grammar support
and `extract_json`; an outline generated under a JSON grammar *cannot* come
back unparseable, so the entire failure class disappears.

Keep his instincts, which were right: structure before content, said twice;
deterministic sampling for the outline; and *"don't repeat what is already
stated"*. Replace the 500-character tail with bands 3 and 5 — the outline plus
the summaries — which is what that tail was a 2048-token approximation of.

#### The Budget Meter — make the invisible constraint visible

Everything above is a policy the author cannot see, and an invisible policy is
one they cannot trust or steer. So the Workshop states it, on the page, from
measured numbers rather than a guess:

> **Magistral-Small-24B · 10,813 tokens usable.**
> Carrying: style card, outline (38 sections), 22 governing claims, §4.2 and
> its neighbours. Summarised: 31 sections. Out of view: nothing.
> *Load Qwythos-9B for 75,448 and the whole manuscript fits.*

Three reasons this earns its place, and the third is the real one:

1. It turns "the AI missed something obvious" into "that section was not in
   view", which is a fixable complaint rather than a mysterious one.
2. It makes the model-versus-context trade a **choice** instead of an
   accident — and, with routing above, often a false dilemma.
3. **It is measurement, not generation** — the thesis of this whole section.
   ATK already has every piece: `read_gguf_metadata`, `kv_cache_mb`,
   `query_gpu`. The table at the top of this section was one script.

### Phase 2 — the Codex, as an evidence ledger

The original calls this the Story Codex and treats it as RAG over notes.
That is half of it. The other half is the idea ATK already owns:

**A story bible IS an evidence ledger.** O.W.L. records observations with the
passage they came from, tracks what superseded what, and answers *"what
decisions are standing on something that turned out to be wrong."* Rename the
nouns and that is a continuity system:

| O.W.L. | Writing Workshop |
|---|---|
| observation | a claim about the world of the document |
| source_ref | chapter and paragraph it was asserted in |
| supersession | the fact changed — the sword became steel |
| **reconsider** | **what did I write that depended on the old fact?** |

That last row is the feature no writing tool has and every writer wants. Not
"find mentions of the sword" — *"you changed the sword to steel in chapter 17;
here are four passages that describe it as bronze, and one that turns on the
sound it makes when it is struck."*

**Claims are typed, because different types are checkable differently:**
- **attribute** — "the sword is bronze", "the housing is aluminium"
- **relationship** — "Mira is Aleksandr's sister"
- **temporal** — "the wedding is on Wednesday", "step 4 takes 20 minutes"
- **numeric** — "40 Nm", "three days' ride", "12 volts"

The numeric case is deterministic and the most valuable one in a manual: two
different values for the same named quantity is a defect, full stop, and needs
no model to find.

**Extraction is proposed, never asserted.** ATK's rule about never presenting a
guess as a fact applies with force here: a Codex that silently fills itself
with a model's readings of the text becomes a bible the author never wrote and
cannot trust. Every auto-extracted claim arrives as a **proposal** carrying its
passage, and stays proposed until accepted. The original plan's instinct here
is right (*"New entity detected … Create a lore card?"*) and should be the rule
for everything, not just new names.

### Phase 3 — Continuity: the part worth building the rest for

**Contradiction detection.** For each claim, retrieve the other claims about
the same subject and compare. Numeric and temporal conflicts are deterministic.
Attribute conflicts need the model, so they are reported as *candidates* with
both passages quoted side by side — the author adjudicates, the tool never
"fixes" anything.

**The Red Thread, done properly.** The original describes semantic search with
a timeline view — which is a search box. The useful version tracks a thread's
**state**: where it is introduced, where it is developed, where it is resolved,
and where it goes quiet. Out of that falls the check nobody offers:

> **Dropped-thread detection.** An entity introduced with emphasis, mentioned
> in three chapters, and then absent for the remaining twelve with no
> resolution. Chekhov's gun, found by arithmetic.

In a manual the same measurement finds the section that references a subsystem
the document never explains again — the reader is left holding it.

**Chronology.** ATK already builds temporal edges with date and time on them
(`atk/core/comms.py`, built 2026-08-28 for the comms tab). A narrative
chronology is the same shape: events with times and participants. It answers
"chapter 12 happens on Tuesday but chapter 9 put the wedding on Wednesday",
and in a manual, "step 7 says wait 20 minutes; the summary says 15."

**Name drift.** "Aleksandr / Alexander / Alex / Sasha" is the fiction version
of terminology drift, and O3's entity de-duplication is already scoped for it.
Same machine, opt-in, proposes and never merges.

### Phase 4 — The Room: assistance, last and least

Only now, and deliberately non-destructive: **the model never writes into the
manuscript.** Output goes to a diff surface where the author accepts, rejects
or splices, and the accepted text is *typed by the author's decision*, not
pasted by the tool.

Reuse the Thinking Workshop's isolation rather than swapping system prompts.
A useful default cast:

- **The Line Editor** — syntax, active voice, rhythm. Returns only revised text.
- **The Continuity Reader** — the Codex in context, checking against the bible.
- **The Expander** — beats to prose, with the relevant Codex entries retrieved.
- **The Adversarial Reader** — the one worth adding. For a manual: *the tired
  technician at 3am who will misread this step.* For a novel: *the reader
  skimming on a train who has forgotten who Mira is.* Both find real defects,
  and neither is a stylist.

The MoE ladder already built (`personas.MOE_LADDER`) gives the depth dial for
the harder asks; the Thinking Workshop gives the whole-team pass.

### 4. THE STYLE FINGERPRINT — the addition I would argue hardest for

Every AI writing tool has the same unadmitted defect: **use it long enough and
the prose converges on the model's voice.** Not through any single bad
suggestion — each one looks like an improvement — but cumulatively, because
the model has a house style and every accepted edit moves one sentence toward
it. The author ends up with a manuscript that reads competent and anonymous,
and cannot point at where it happened.

This matters more for a technical manual than for a novel, not less: an
organisation's documentation has a house voice, a register, and conventions
that exist for reasons, and a model flattens all three while appearing to
help.

The defence is measurement, and it is arithmetic:

**Build a fingerprint from the author's own text** — sentence-length
distribution and its variance, paragraph length, comma density, semicolon and
em-dash habits, subordination depth, vocabulary rarity profile (share of words
outside the common 5,000), type–token ratio, adverb rate, dialogue-tag
preferences, how often a sentence opens with an article, simile markers.
Fit it on writing the author has already done and accepted.

**Then score every suggestion against it before it is offered**, and show the
drift:

> *This rewrite is cleaner. It is also 40% shorter per sentence than your
> baseline, drops two of the three subordinate clauses, and replaces one
> word you use often with one you have never used. Accept it as a
> simplification, not as your voice.*

Three things follow, and they are the reason to build it:

1. **The author can see the drift.** Nothing else in the category offers this.
2. **It works per-project.** A technical manual and a novel have different
   fingerprints, and so do two novels; the baseline is the document's own.
3. **It gives "house style" a definition that can be enforced** rather than
   described in a style guide nobody reads — which is the technical-writing
   half of the same feature.

The fingerprint is also the honest answer to *"can it write like me?"*: it
cannot, and it should say so, but it can tell you when it is not.

### 5. Smaller additions the original does not have

- **The blank page.** The whole plan assumes text exists. Nothing helps start:
  beat sheets, an outline expanded into a scene list, the Thinking Workshop
  used as a writers' room before a word is written. For a manual: an audience
  and task analysis that produces the structure.
- **Export that respects the destination.** `reports.markdown_to_docx` already
  exists. Add manuscript format (Shunn) for fiction submission, and for
  technical work a numbered-section .docx with a table of contents — the
  format a manual actually ships in.
- **Reading-order proofing with the voices ATK already clones.** Read-aloud
  finds clunky dialogue and unspeakable instructions better than any metric.
  See the TTS note below — this is a real trade-off, not free.
- **Research crossover, which only ATK can offer.** A historical novelist or a
  documentation author working from source material can use the extraction,
  the map and the profiles that already exist. A novel's setting on the
  Geospatial canvas is not a gimmick; it is the same question as an analyst's.
- **The songwriter, already built.** A character who sings gets real lyrics,
  in their established voice type and — since 2026-08-28 — in their culture's
  idiom and language.
- **Session ritual.** Word-count targets, a timer, a streak. Small, slightly
  embarrassing, and the feature working writers actually open the app for.

### 6. On Piper — ~~the one original recommendation to keep as-is~~

> **SUPERSEDED 2026-08-29. F5-TTS was REMOVED from ATK entirely** —
> Bill: *"let's go with piper only for now, get rid of the old one."*
> There is no trade-off left to weigh: Piper is the only engine, it is
> CPU-only, near real time, and about 63 MB. The paragraph below is
> kept because it records what the constraint USED to be, not because
> any of it still applies.


ATK has F5-TTS, so "we already have TTS" is the obvious response and it is
wrong. F5-TTS is a diffusion model: excellent for a cloned character voice,
far too slow to read a 6,000-word chapter aloud while the author follows along.
Piper is near-real-time on CPU and costs no VRAM.

They are for different jobs and both are worth having: **F5-TTS for a
character's voice, Piper for proofreading at length.** The original plan was
right about this and the reflex to dismiss it would have been wrong.

### 7. What NOT to build

- **No ChromaDB, no FAISS.** `SafeStore` is there and works.
- **No 8B embedder.** See §2a.
- **No hidden repository.** See §2c.
- **No autocomplete or ghost text.** It is the highest-slop-risk feature in the
  category: it trains the author to accept the model's next word thousands of
  times a session, below the level where any of them is a decision. Everything
  else here is opt-in per suggestion; ghost text is opt-out per keystroke.
- **Nothing writes into the manuscript but the author.** Not the extractor, not
  the Codex, not a persona, not a "fix all". The moment the tool can edit the
  book without a human keystroke, every other guarantee here is a promise
  rather than a property.

### 8. Suggested order, and why

| # | Block | Needs a model? | Why here |
|---|---|---|---|
| 1 | Shell, structure tree, ingest | no | Nothing works without it, and it is small — most of it is `chunk_text` and `projects.py`. |
| 2 | **Craft measurements** | **no** | Real value on day one, and it is the part that cannot lie. Ships before any VRAM question is asked. |
| 2b | **Context assembler + budget meter** | **no** | §4b. Arithmetic over token counts and a GGUF header — and everything after it depends on the budget being known rather than assumed. |
| 3 | Codex as an evidence ledger | partly | O.W.L. reuse. Deterministic claims first, model-extracted claims as proposals. |
| 4 | **Continuity + Red Thread + chronology** | partly | The reason to build the rest. Numeric and temporal checks are deterministic; attribute conflicts are candidates. |
| 5 | Style fingerprint | no | Arithmetic, and it must exist before Phase 6 or the drift is unmeasured. |
| 6 | The Room, diff surface | yes | Commodity, and the riskiest to voice — so it arrives with the fingerprint already watching it. |
| 7 | Versions, export, read-aloud | no | Finishing. Sentence-level diffs, Shunn/`.docx`, batched read-aloud through `render_queue.py`. |

Blocks 1, 2, 2b and 5 need **no inference at all**, which means a usable
writing tool exists before the first model is loaded — on a laptop on a plane, with
the GPU cold. That is worth having on its own and it is the strongest argument
for this ordering.

### 9. Decisions — ANSWERED by Bill, 2026-08-28

1. **ITS OWN WORKSPACE** — Bill first said sub-tab, then handed the call
   back: *"if you feel its own tab makes sense more, make the creative call,
   I trust you."* Taking it. Own workspace, and the reasoning matters more
   than the verdict because it is the kind of decision that is expensive to
   reverse once people have muscle memory.

   **The argument that decides it: this workspace has six sub-tabs of its
   own.** Manuscript · Codex · Continuity · Craft · The Room · Versions.
   Putting those inside a tenth sub-tab of the Analysis Suite is two levels
   of tab bar — the operator picks Analysis Suite, then Writing Workshop,
   then Continuity, and the second row moves under them each time they
   switch. The Music Workshop already nests four inner tabs that way and it
   is fine there for a specific reason: it is an occasional easter egg, and
   Bill placed it with *"it doesn't need to be the sidebar."* A place an
   author spends four hours in is not that.

   The three supporting reasons:

   - **The Analysis Suite's tabs are utilities; this is a place.** Translate
     a document, OCR a scan, transcribe audio, check an image — all
     visit-and-leave. A manuscript is somewhere you stay.
   - **The objection to growing the rail is gone, and gone because of work
     done today.** §18 was "the rail runs out of screen at 1080p." It scrolls
     now. Deciding against a workspace on a constraint that was lifted this
     morning would be reasoning from a stale fact — which this session has
     spent all day removing from elsewhere in this file.
   - **It is core work for this toolkit, not a diversion.** Analysts write
     reports, briefs and manuals constantly. This is closer to ATK's purpose
     than several things that already hold a rail position.

   **The cost, stated plainly:** a fourteenth rail entry, and the rail shows
   nine before it scrolls. A place you live in must not require a scroll to
   reach — so **position it immediately after the Analysis Suite** (third),
   inside the default visible set.

   **And the observation that falls out of it, which is worth more than this
   decision:** now that the rail scrolls, **the order of `WORKSPACES` is a
   design variable rather than the order things happened to be built.** The
   first nine entries are the always-visible set; everything after them costs
   a gesture. That list has never been curated — it is accretion order — and
   it should be reviewed once, deliberately, against what an operator reaches
   for most. Cheap to do and nobody has done it.

   **Not a prerequisite any more, but still worth doing:** `BasePanel`'s
   `TopBar` is `setFixedHeight(42)` with a plain `QHBoxLayout` and no
   scrolling, and the Analysis Suite already sits at nine sub-tabs and 146
   characters of label. That fits at 1920 px and is tight at 1600, and Qt's
   answer to not fitting is the silent squeeze that clipped the Setup page on
   2026-08-01 and the sidebar on 2026-08-28. Keeping the Writing Workshop out
   of that bar removes the immediate risk; applying `_SidebarScroll`'s
   treatment to `_build_tab_bar` would remove it everywhere, for one small
   change.

2. **One workspace, both document types.** As recommended: a project-level
   document type selects which Craft checks run and which exports appear. The
   spine is identical for a manual and a novel, and splitting it doubles the
   UI for no gain.

3. **O.W.L. — no fallback store.** Bill: *"use owl."* Simpler than the
   both-homes posture recommended above, and defensible: `install.bat` clones
   and installs OWL unconditionally, and `subsystems.ledger` has defaulted ON
   since 2026-08-14 precisely because *"OWL isn't optional from an
   installation perspective."* Building a second claims store against the
   possibility of OWL being absent would be building for a state ATK does not
   ship. The Codex degrades to a plain list when the ledger is off, the same
   way every other O.W.L. surface does.

4. **The fingerprint is attached and quiet.** As recommended: a number beside
   the suggestion, not a dialog. The author can look at it or not.

5. ~~**NO PIPER — use the audio stack ATK already has.**~~
   **REVERSED BY EVENTS, 2026-08-29, and what was built follows the
   new position.** This decision was correct on the facts of the day:
   ATK's audio stack was F5-TTS, a diffusion model, and a 6,000-word
   chapter was minutes of synthesis. Then F5-TTS was removed and
   Piper became the only engine — so "use the audio stack ATK already
   has" now MEANS Piper, and the constraint the decision was built to
   accommodate no longer exists.

   What `writing_workshop/readaloud.py` actually does: **short
   passages on demand** (interactive again, because Piper is near real
   time on the CPU) **and chapters as a batch** through the render
   queue — the second kept not because synthesis is slow but because
   listening away from the manuscript is how proofreading by ear works.
   And a character is read in the voice ATK has ESTABLISHED for them:
   `assign_voices` returns `needs_voice` naming anyone without one
   rather than picking.

   *Original reasoning, kept:*
 Bill: *"lets just use
   our audio dependencies that we have in atk already."* This overrules §6,
   and the consequence is real, so it is stated rather than glossed:

   **F5-TTS cannot read a chapter aloud interactively.** It is a diffusion
   model; a 6,000-word chapter is minutes of synthesis, not a play button.
   So read-aloud is redesigned around what ATK has rather than pretending the
   constraint is absent:

   - **Short passages, on demand.** A paragraph, a line of dialogue, one
     numbered step. This is the high-value case anyway — an author proofs the
     sentence they are unsure of, not the whole chapter — and F5-TTS is good
     at it, in the character's own cloned voice.
   - **Chapters as a BATCH, through the render queue.** `render_queue.py`
     already exists (built for music, 2026-08-28) and its shape fits exactly:
     queue the chapters, walk away, come back to audio files and listen on
     headphones away from the screen. A wait that was unacceptable
     interactively is unremarkable as a background job, and listening away
     from the manuscript is how proofreading by ear actually works.

   This is a better answer than Piper would have been for the character-voice
   case, and a worse one for reading a whole draft at your desk. Recorded so
   the trade-off is visible if it ever bites.

### 9b. One standing rule this workspace leans on

**Every embedder in ATK runs on the CPU** — Bill, 2026-08-28: *"the embedding
models should all use cpu."* Enforced the same day, in `embed_engine.load`
(clamps and says so), `ledger._build_embedder` (clamps), and
`vector_store.SentenceTransformerEmbedder` (`device="cpu"` — it was the one
embedder that still took CUDA, because sentence-transformers asks torch for
the best device and it is the FALLBACK path nobody chooses deliberately).

It matters here more than anywhere else in ATK, because the Red Thread embeds
**continuously in the background while the author is writing**. An embedder on
the card would compete with the writing model at precisely the moment the
author is waiting on it, every time — which is the worst possible schedule for
that contention.

### 10. What this reuses, so nothing is built twice

`chunk_text` · `SafeStore` · `embed_engine` · `projects.py` · `extract.py` and
Pass-0 triage · the categorise-Other pass · `ledger.py` and O.W.L.
reconsider · `comms.py` temporal edges · `graph_layout` · `personas.py` and
`MOE_LADDER` · `workshop.py` isolation · `conversation.py` compression ·
`vram.py` planning · `spellcheck.py` · `reports.markdown_to_docx` ·
`cognitive_library` characters · `voices.py` and F5-TTS · `render_queue.py`
(the same shape serves a batch of chapter analyses) · `detach.py`.

The genuinely new code is the editor widget, the craft metrics, the claims
model, the fingerprint, the diff surface, and versioning. That is a much
smaller build than the original plan implies, and a much better tool.
