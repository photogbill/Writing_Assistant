# Writing Workshop — review, 2026-09-05

> **ALL OF IT IS BUILT, 2026-09-05.** Bill: *"lets fix them all… if you
> find anything else that should be improved or fixed while you fix the
> others, go ahead."* Every item below is done, plus four things found
> while doing them (listed at the end). The suite went from 169 checks to
> 228, ruff from 57 findings to zero, and the craft pass over an
> 81,000-word document from *not finishing in five minutes* to **3.4
> seconds**.
>
> Each heading carries a **✅** and a note on what it became. The reasoning
> underneath is left as written — it is why the change looks the way it
> does.
>
> One idea in the original draft was **withdrawn** rather than built: a
> per-check time budget. See M1.

*Ideas only, no code changed. Read against the repo as it stands on
2026-09-05 (169 tests, green) and against ATK's side of the boundary
(`atk/core/writing.py`, `writing_host.py`, `atk/ui/writing_panel.py`).*

Three things measured on real documents, then flexibility, then results.
The measured ones come first because two of them are the reason the rest
of the list matters: **the workshop currently cannot finish a craft pass
on a document the size it was designed for**, and that is not a judgement
call.

Everything below holds the four rules. Nothing here asks the model to do
more, nothing writes into a manuscript, and nothing turns a proposal into
an assertion.

---

## Measured

### M1. ✅ The sentence splitter was O(n²) — fixed, and 40× faster

> **Done.** `_is_boundary` scans forward instead of slicing the tail; `Manuscript` caches sentence spans, paragraphs, section lookups and `find()` results. `T.sentences` over 610 KB: 2.82 s → **0.066 s**, byte for byte the same 4,407 spans. Full craft on that document: **>300 s → 3.4 s**, all checks completing. Three ratchets in `tests/test_performance.py`, two of them structural — an AST check that these functions never slice the tail, and a counter proving a file is split into sentences ONCE however many quotes are taken.
>
> **The time-budget idea in this section is withdrawn**, on Bill's instruction: he offloads to the CPU by choice, nothing is ever dropped for taking too long, and a check abandoned on a timer is a silent gap in a report whose fourth rule is that it says what it did not do. What replaced it is `events` on `craft.run` — progress per check — and cancellation, which is the operator's decision.

`textio._is_boundary` (line 439) ends with:

```
rest = text[end:]
if not rest.strip():
```

`text[end:]` copies the whole remainder of the file, and `.strip()` scans
it — once for **every** `.!?…` in the document. On a 610 KB file that is
~64,000 slice-and-scan passes over an average 300 KB tail.

Measured on `ATK/FUTURE_PLANS.md` (81,521 words, 293 sections, 610,468
characters of prose after masking):

| prose | `T.sentences` | spans |
|---|---|---|
| 76,308 chars | 0.03 s | 547 |
| 152,617 chars | 0.09 s | 1,143 |
| 305,234 chars | 0.52 s | 2,303 |
| 610,468 chars | **2.82 s** | 4,407 |

Each doubling costs 4–5×. Textbook quadratic.

`Manuscript.quote()` then makes it worse: it calls `T.sentences()` over
the **entire file** on every call, uncached, to find the one sentence a
span sits in. A cProfile of the `acronyms` check alone:

```
13 calls to document.quote()      39.83 s of a 40 s run
  textio.sentences                39.83 s
    textio._is_boundary           18.49 s  (64,124 calls)
    str.strip                     16.18 s  (128,546 calls)
```

Thirteen evidence quotes, forty seconds.

End to end: `craft.run(doc, "technical")` on that document **had not
finished after five minutes**. Run individually with an 18 s cap, five
checks blew through it — `echo`, `stock_phrases`, `terminology`,
`acronyms`, `xrefs` — while the other ten finished in under a second
each.

**Proven fix, tried in a scratch copy, not in this repo.** Two changes,
neither of which alters behaviour:

1. In `_is_boundary`, replace the tail slice with a forward scan from
   `end` over whitespace only, and match `_M` with a position argument
   instead of against a fresh string. No allocation, no full-tail scan.
2. Memoise sentence spans per text. A `Manuscript` is immutable once
   loaded — `Project.manuscript()` re-reads from disk every time on
   purpose — so a cache keyed on the text is safe by construction.

Result on the same document:

* `T.sentences`: 2.73 s → **0.14 s**, and `a == b` on the span lists —
  byte-identical, all 4,407.
* full `craft(technical)`: **>300 s → 6.1 s**, all 15 checks completing,
  `skipped` empty.

Two secondary points fall out of this and are worth their own attention:

* **A skipped check is a footnote and should be a banner.** A check
  that raises is recorded in `report.skipped` and the pass continues —
  the right design, and the module says why. But an empty findings list
  from `echo` is indistinguishable from a clean manuscript, and the only
  thing separating them is one line under the report. The module's own
  docstring names that as the worst outcome it has; the UI should treat
  it that way. (In the run above the skips were induced by my own 18 s
  cap for measurement — with no cap the checks do not skip, they simply
  never finish.)
* **`craft.run()` has no progress channel.** `continuity.map_sections`
  emits per section; `craft.run` takes `cancel` and no `events` at all.
  A pass that says nothing for two minutes is indistinguishable from a
  hang — the failure ATK has shipped before and the one `ports.Events`
  exists to prevent. Emit per check and per section, and a long wait
  becomes a wait rather than a mystery.

  **Ruled 2026-09-05, and it corrects an earlier draft of this file:
  nothing is ever dropped for taking too long.** Bill offloads to the CPU
  by choice and is willing to wait, so a time budget that skipped a check
  would be the tool making a decision that is his — and a skipped check
  is a silent degradation, which is exactly what rule 3 forbids. The
  answer to a slow pass is progress plus a cancel button the operator
  presses, never a deadline the tool enforces. (The O(n²) fix above is
  unaffected by this: it is not "fast enough to meet a deadline", it is
  the same output for a twentieth of the work. And it is what makes the
  difference between a CPU-offloaded pass being slow and being
  unfinishable.)

### M2. ✅ The registry can no longer be observed empty

> **Done.** `_load()` runs on every read — `checks_for()`, and a new `registry()` — so the dict is never handed out empty. ATK's dropdown asks through it and filters by the project's doctype profile. Proven from outside by `workshop checks`, which lists 24 checks in a process that has never run a pass.

Registration happens on import, and the imports happen **inside**
`craft.run()`:

```
>>> from writing_workshop.craft import REGISTRY, checks_for
>>> len(REGISTRY),  len(checks_for('technical'))
(0, 0)
>>> # after one run(...)
(20, 15)
```

`atk/ui/writing_panel.py:849` builds the per-check dropdown in
`on_project_changed`, from `CRAFT_CHECKS`. On the first project opened in
a session that runs before any craft pass — so the dropdown offers
**"every check" and nothing else**. It fills after a run, but
`on_project_changed` does not fire again, so the filter stays dead until
the operator switches projects.

Same family as the `PAGE_LABELS` bug on 2026-08-30: built, wired,
unreachable, nothing fails. The fix is to make the empty state
unobservable — have `checks_for()` (and any accessor for the registry) do
the import itself, exactly as `run()` does. A module-level import would
also work but costs the "import `craft` for its registry alone" property
the comment is protecting.

### M3. ✅ 916 findings became 370, and then a dozen

> **Done.** A per-check cap that states what it did not list (the check still runs in full; `max_findings: 0` turns it off), plus `findings.py` — a content key per finding, a dismissal list, and the delta against the last run. `--new` after an afternoon's work shows only what appeared.

Same document, after the M1 fix so everything actually runs:

```
craft(technical)  6.1 s  916 findings
  echo           warn   409     xrefs        defect  28
  acronyms       warn   333     long_steps   warn    18
  filter_words   warn    36     long_steps   defect  12
  terminology    warn    34     openers      warn    11
  stock_phrases  note    15     units       defect/warn/note 12
```

Caveat, stated plainly: FUTURE_PLANS.md is a design document, not a
manual, so some of that is genre mismatch — 333 unexpanded acronyms in a
document written for readers who know what GGUF and KV mean is the check
being literal, not wrong. The performance numbers above are
genre-independent; this one is a shape, not a verdict.

The shape is the problem anyway. There is no per-check cap, no
dismissal, no delta between runs, and `Finding` carries no identity that
survives an edit — so nothing *could* be dismissed even if a panel wanted
to offer it. R1 and R2 below are the answer, and they are the difference
between the second run being useful and being the first run again.

---

## Flexibility

### F1. ✅ Language is declared, and a check that cannot speak it says so

> **Done.** `Project.language`, `Registered.languages`, and `run()` skips with a reason: *"its arithmetic is en-only and this project is written in de"*. Eight checks are marked `ANY_LANGUAGE` because they count structure rather than consulting a word list.

`COMMON`, `syllables()`, `FILTER_WORDS`, `SUBORDINATORS`, the `-ly`
adverb rule, `BE`/`IRREGULAR` participles, weekday and month names,
`NICKNAMES`, Flesch–Kincaid and Gunning fog — every one of them is
English, and nothing in the package records what language a project is
in or refuses when it does not know.

Point a Spanish or German manuscript at it and **every check runs and
every answer is confident nonsense**: no word is in `COMMON`, so `rarity`
is ~1.0 and `echo` fires on ordinary vocabulary; the passive rate is 0
because no `BE` verb matches; readability is a formula fitted to English
syllable counts. That is rule 3 inverted — silent total degradation in
the one place it cannot be seen from the output.

The cheap, honest version is not per-language tables. It is:

* `Project.language`, defaulting to `"en"`.
* A `languages` field on `Registered`, defaulting to `("en",)`.
* `run()` skipping the rest with a stated reason: *"12 of 20 checks are
  English-only and did not run."*

That costs an afternoon and converts a silent lie into a stated
limitation. Per-language word lists then become a purely additive
contribution rather than a prerequisite. It is also the hook that lets a
libretto with idiom in another language get measured honestly instead of
noisily — which matters more here than in most projects.

### F2. ✅ Three types built in, and any number declared

> **Done.** `doctypes.py` — a profile is a base, `add`/`drop`, options and exports, from `.workshop/doctypes.json` or a `house.json`. **Lyrics ships as the third built-in type**, with three checks that earn it: syllables per line against the section's own median, a refrain compared line-for-line between tagged occurrences, and rhyme-scheme drift (spelling-based, and every finding says so). It caught a drifted chorus on the first run — and rejected the two verses, which was its first false positive and is now a structural rule rather than a list of section names.

`DOC_TYPES = (TECHNICAL, FICTION)`; `Project._apply` coerces anything
else back to technical. Decision 2 was right — the spine really is
identical for a manual and a novel, and splitting the workspace would
have doubled the UI for nothing. But the type is now a bare string in a
tuple, and the near neighbours are real:

* **screenplay / stage** — sluglines, character cues, page-per-minute,
  and a format as unforgiving as Shunn;
* **academic / report** — citation integrity, figure and table
  numbering (half-built already in `xrefs`);
* **lyrics / libretto** — where the measurements that matter are lines
  and syllables per section, rhyme-scheme drift, and stress pattern. The
  primitive (`textio.syllables`) already exists and nothing uses it for
  this.

Suggested shape: a document type becomes a small declarative **profile**
— which checks apply, which exports appear, which thresholds, which
personas — loaded from `.workshop/` with the built-in two as defaults.
F3 and F5 then fall out of the same mechanism instead of being three
separate features.

### F3. ✅ Thresholds arrive, from the house and then the project

> **Done.** `Project.craft_options()`, passed by the CLI and by ATK.

`Ctx.opt()` reads an `options` dict. `craft.run()` accepts `options=`.
`Project.settings` exists. **Nothing connects them.** Neither
`cli.cmd_craft` nor `atk/ui/writing_panel.py:862` passes `options`, so
`echo_window`, `echo_vocabulary_floor`, `target_grade`, `opener_run`,
`phrase_min`, `step_words_warn`, `step_words_defect` and
`absence_chapters` are reachable in code and unreachable in practice.

This is the difference between *"the echo check is too noisy for this
book"* being a complaint and being a setting.

### F4. ✅ `house.json` above the shelf

> **Done.** `Project.House`, found up to four directories up. Style card, rules, terms, glossary titles and craft settings are INHERITED rather than copied in, so changing the house file moves every project under it.

Style card, document rules, terms, glossary titles and cast are all
per-project. An author with twelve manuals under one house style keeps
twelve copies that drift apart — which is the exact defect
`terminology` exists to find, one level up. A `house.json` beside the
projects that each one inherits from and may override turns "the style
guide nobody reads" into something enforced across a shelf rather than a
folder. Small, and it is the technical-writing half of the fingerprint's
argument.

### F5. ✅ `.workshop/rules.json`

> **Done.** `rules.py` plus a craft check. Phrase or pattern, a severity, a scope (`prose` / `raw` / `headings` / `steps`), a file glob. A rule that will not compile reports ITSELF as a defect rather than going quiet. `workshop rules PATH --init` writes a starter file.

Every craft check is a Python function inside the package. There is no
way for an author to add *"never write 'simply'"*, *"use 'select', not
'click'"*, *"no first person in a procedure"*, *"every warning opens with
the hazard"* without editing the engine.

A declarative rule file in `.workshop/` — pattern, message, severity,
optional scope (this section type, these files, prose only) — is pure
arithmetic, cannot hallucinate, needs no model, and fits the thesis
exactly. It is probably the highest value-to-code ratio on this list. It
is also the natural home for the acronym allow-list M3 needs, and for the
"these are our terms of art" list that `definitions` and `units` already
depend on.

### F6. ✅ `.docx`, read-only, standard library

> **Done.** `formats.py` — `zipfile` + `xml.etree`, no dependency. Headings, numbered and bulleted lists (including numbering that lives on the STYLE, which is how several generators write it), tables, paragraphs. Verified against a real Word file: it found a 40 Nm/45 Nm contradiction across two sections. The file is marked `derived`, `clickable` is false, `Manuscript.notes()` says the offsets are not positions in the author's file, and `steps` skips it — Word stores no list numbers, so any gap found there would be one this package invented.

`.md`, `.markdown`, `.txt`. Most 200-page manuals live in `.docx`, and
ATK already knows how to read one without destroying it
(`atk/core/documents.py`, byte-span splicing).

A **read-only** measurement path for `.docx` — the workshop measures and
never writes, findings anchored to paragraph index rather than character
offset — would let the workshop earn its keep on documents nobody is
going to convert first. This is the one idea here that costs real design
work, and the read-only constraint is what keeps it from breaking "the
manuscript is never locked inside the tool": it stays *outside* the tool
entirely.

### F7. ✅ Said plainly, in both places

> **Done.** The README now says what `adapters/atk/` is — a reference host, not the shipped adapter — and both files carry a banner saying ATK does not read them and a fix made there reaches nobody. Nothing was deleted: as a worked example of the ports it still earns its place, and deleting 55 KB of working code to correct a sentence is the wrong trade.

`adapters/atk/writing_panel.py` is 1,415 lines and six pages. ATK ships
`atk/ui/writing_panel.py` at 4,569 lines and nine pages — Storyline,
Draft and Author Styles all arrived after this copy was taken — and ATK
never reads `adapters/` at all.

The README still describes `adapters/atk/` as "the only code that imports
`atk.*`" and as the thing the boundary test protects. The boundary test
is fine; the sentence is now false, and there are two copies of one file
with the dead one documented. Either make it the real adapter (ATK
imports it) or delete it and let the README say the adapter lives in ATK.
The middle state is where a later reader loses an afternoon.

---

## Results

### R1. ✅ Findings have identity, and dismissals stick

> **Done.** The key is check + subject + normalised title + first quoted line, and deliberately **no offset** — a paragraph that moves is the same finding, a sentence that is rewritten is a new one. `workshop dismiss`, `--list`, `--restore`; in ATK, "I know about this ▸" with a reason, and "Show dismissed" to review.

`Finding` carries `check`, `severity`, `title`, `span`, `evidence` —
nothing that survives the paragraph moving. Give it a **content key**:
check name + normalised subject + the quoted evidence, deliberately
**not** the offset. Then keep a dismissal list in `.workshop/`.

Three sentences in a row opening with "The" get dismissed once as
deliberate anaphora and do not come back. Without it, the 916 findings
above are 916 findings again next Tuesday, and the one the author needed
is buried under the ones they already decided about.

Deliberately **not**: auto-dismissal, a confidence threshold, or a "fix
all". A dismissal is an author's decision, recorded with a date and a
reason, governed by exactly the rule that governs claim acceptance.

### R2. ✅ `--new`, and "New since last run" in ATK

> **Done.** `--remember` stores keys and titles only; craft stays stateless. A first run never calls anything new, because that would be a lie the operator learns to ignore the delta over.

Craft is stateless on purpose and should stay that way. But storing the
last run's finding keys costs nothing and buys the single most useful
view a repeat-run tool has: **what appeared since last time, and what
went away.**

An author who has spent an afternoon in chapter nine wants twelve new
findings, not nine hundred. The same machinery answers *"what changed
since the version named 'draft for legal review'"*, which is the versions
feature and the craft feature finally meeting — right now they share a
project and nothing else.

### R3. ✅ The book, against a draft you name

> **Done.** `drift.py` fits the baseline on a named version and scores the current manuscript per chapter, with a first-half/second-half line because a rising trend is the shape a convergence has. `workshop drift --since`, and "Style drift since this version ▸" on ATK's Versions page. Verified: a chapter rewritten flat scored 4.99 and named why — flatter on variety in sentence length, flatter on subordinate clauses, more repetitive on vocabulary variety.

The fingerprint is the best idea in this package and it is aimed at half
the problem. `Room.attach_drift` scores a suggestion **before it is
offered**. Nothing ever scores **the book against its own past**.

You already have named versions on disk. Fit the fingerprint on version 1
— or on whichever version the author names as *"before I started using
the Room"* — and score the current manuscript against it, per chapter.

That is the direct, arithmetic answer to the question the module's own
docstring poses: *use it long enough and the prose converges on the
model's voice*. At present the package can only ask that one sentence at
a time, which is precisely the level at which the drift is invisible —
"each one looks like an improvement" is the docstring's own words.

If chapters 1–8 sit at z ≈ 0 and chapters 9–17 sit at 1.8, that is a fact
about the book, produced by arithmetic, and nothing else in the category
can produce it. It is the strongest single capability on this list and it
needs no new machinery — versions, fingerprint and chapters all exist.

### R4. ✅ The Room's prose is recorded, outside the manuscript

> **Done.** `influence.py`. What is stored is the accepted TEXT, not a span, and it is re-located when needed — so a passage the author has since rewritten past recognition stops counting as the model's, which is right. ATK records it on accept and leaves it out when fitting.

`fit()`'s docstring says *"'Accepted' is load-bearing… fitting on a draft
that already contains the model's rewrites bakes the drift into the
baseline, and the tool then reports that everything matches beautifully —
the exact failure it exists to prevent."*

Nothing tracks it. `from_manuscript()` fits on whatever is on disk.

`Suggestion` already carries a `target` span. When the author accepts
one, record that span in `.workshop/` — never in the manuscript, the rule
holds — as model-influenced. Then the baseline can be fitted on
author-typed prose only, and R3's measurement stops being self-defeating.
Small change; it is the difference between the fingerprint being a real
defence and being a well-argued one.

### R5. ✅ Called twice, for the two things it is for

> **Done.** `codex/select.py` — `governing(doc, section, claims, retriever=…)` takes the claims a passage NAMES, then uses retrieval over the claims' own quoted passages for the ones it is about without naming. And `context.build(retriever=…)` orders band 4 by RELEVANCE rather than by distance, which is what an embedder is for: the section that matters to chapter 31 is often chapter 7.

`ports.Retriever` ships a genuine BM25 index. ATK builds an
`ATKRetriever` over `SafeStore` and hands it to the `Host`
(`writing_host.py:429`). **Nothing under `writing_workshop/**` ever calls
`host.retriever`** — grep returns only `ports.py`.

Band 2 of the assembler is documented as *"Codex claims that constrain
THIS section, retrieved"* and described as the highest value-per-token in
the system. In practice `context.build(claims=…)` takes whatever list its
caller passes, and there is no function anywhere that selects the claims
governing a section.

A `codex.governing(doc, section, store, retriever)` — claims whose
subject is mentioned in the section, plus retrieval over the claim
quotes, capped and priced — is a small function, and it is the one that
makes band 2 mean what §4b says it means. Until it exists, the band is a
parameter.

(The `Ledger` port is the same shape — never called from the core — but
that one is defensible: the adapter mirrors on accept and the core should
not know O.W.L. exists. Worth a line in `ports.py` saying so, since the
two ports currently look identical and only one of them is finished.)

### R6. ✅ The cast is read from the document

> **Done.** `cast.py`, shared by the craft checks and the Codex. `codex.subjects_for()` is public so a host can show which names it used — a Codex filled from names nobody can see would be the thing every other proposal in this package avoids.

`codex.deterministic()` runs `attribute_claims` only when handed
`subjects`, and the CLI passes `project.cast or None`. An author who has
not typed a cast list gets **zero** attribute claims — so contradiction
detection has nothing to compare and the Continuity page is emptiest on
the document type that needs it most. Measured: 0 claims on a 155,000-word
fiction manuscript with no cast list.

`craft.shared.detect_cast()` already finds the cast by arithmetic — and
does it well, including the mid-sentence test that keeps "Meanwhile" out
— and `codex` never calls it. Propose the detected cast as the default
subject list (proposed, per rule 2; the author confirms), and the fiction
half of the Codex fills itself honestly on first run instead of waiting
for a list nobody types.

### R7. ✅ Conflicts read as a timeline

> **Done.** *"In reading order: “bronze” §1–§3, then “steel” from §17."* Earlier side always first, and `sequential` says whether one value gives way to the other or the two interleave — the shape of a change against the shape of a mistake, with no opinion about which.
>
> **And the defect this uncovered.** Conflicts were reported per pair of CLAIMS, so forty mentions of bronze against twelve of steel produced 480 identical findings — measured at **5,821** on one manuscript. Now one per pair of distinct VALUES, carrying the mention counts: 5,821 → 19.

`contradictions.find` groups by `subject|predicate` across the whole
document and reports every disagreeing pair. In a forty-chapter novel a
character who cuts their hair in chapter 20 is a permanent WARN, and the
only remedy is supersession — which is a manual act about a fact that
changed *for the author*, not one that changed *in the story*.

The claims already carry `section_id`, and sections already carry
`order`. Report a conflict **with its reading order**: *"bronze through
§3–§16, steel from §17."* That turns a contradiction into a one-line
timeline and lets the author see in a glance whether it is an error or a
plot point. Same arithmetic, one extra column, and it is what makes the
check survive a long book rather than being switched off around
chapter 25.

### R8. ✅ All of them

> **Done.** Caps on `echo`, `acronyms` and every other check; `chronology.summarise` and `transitions` beside the raw 3,922-item list, plus `out_of_order` for dates; a project acronym allow-list via the rule pack; `section_at` and `paragraphs` and `find` all cached or bisected; `size` and `age` joining material and colour, which is affordable now that a finding can be dismissed once; and `fingerprint.by_group` / `by_speaker` for per-section-kind and per-character baselines.

* **Cap findings per check.** `echo` produced 409 and `acronyms` 333 on
  one real document. `stock_phrases` is worse in principle: it emits one
  `Finding` per repeated 4-gram *and* a `repeated_phrases` metric holding
  the top 20, so the findings are already redundant with the metric. (On
  synthetic text it produced 1,343 of 1,421 findings — that number is an
  artefact of a small vocabulary and is not evidence about real
  manuscripts, but the absence of any cap is.) "…and 400 more, see the
  metric" is more useful than 400 rows.
* **`chronology.timeline()` returned 3,922 moments** on a 155,000-word
  manuscript. A timeline nobody can read is a search result.
  `weekday_runs` is already the right idea — report *transitions*, and
  extend it to dates and durations.
* **`acronyms` has a hardcoded 20-item `_ACRONYM_SKIP`** and no
  project-level allow-list. That is the 333.
* **`Manuscript.section_at()` is a linear scan** over every section,
  called once per hit; `paragraphs()` is recomputed on every call, and
  `reconsider._paragraph_at` calls it per hit. Both become bisect
  lookups once the sentence spans are cached (M1).
* **`_ADJ_PREDICATE` covers material and colour.** Deliberate, and the
  argument for keeping it narrow is right. But *size* and *age* are the
  next two places continuity errors actually live, and both are as closed
  a list as the first two.
* **`fingerprint` is one baseline per project.** A manual's procedures
  and its prose have legitimately different shapes, and so do two
  characters' dialogue. Per-section-kind and per-speaker baselines are
  the same code with a different grouping key.

---

## Order I would take them in

1. **M1** — the splitter. It is the difference between the workshop
   working on its target document and not, the fix is behaviour-
   preserving, and it is proven.
2. **M2** — the dead check dropdown. One line, and the feature currently
   exists for nobody.
3. **F3** — wire `Project.settings` into `craft.run(options=…)`. One
   line, eight thresholds.
4. **R1 + R2** — finding identity and the delta. This is what turns 916
   findings into twelve.
5. **R3** — the manuscript's own drift across versions. The highest-value
   new capability here, entirely arithmetic, and every piece it needs
   already exists.

**F1** (declare the language) belongs in that list too, and I have put it
below the five only because nothing today is written in another language.
The day something is, it is the most important item on the page.

Everything else is a decision rather than a fix, and can wait for one.


---

## ✚ Found while fixing the above

1. **Conflicts were reported per claim pair, not per value pair** —
   5,821 findings on one manuscript, all saying the same sentence. See R7.
2. **`craft.run` had no progress channel at all**, while
   `continuity.map_sections` had one — and craft is the pass most likely
   to take two minutes.
3. **`--type` did not reach the profile** in the new CLI: `--type lyrics`
   on a project saved as technical ran the sixteen technical checks and
   printed them under the lyrics heading. A report about the wrong
   document.
4. **The repo was at 57 ruff findings, not zero**, including a duplicate
   set member and two loop variables nothing used. Now zero, with the one
   deliberate exception carrying a `noqa` and the reason.

## Where it ended up

| | before | after |
|---|---|---|
| craft over 81,521 words | did not finish in 5 min | **3.4 s** |
| `T.sentences` over 610 KB | 2.82 s | **0.066 s**, identical output |
| findings on that document | 916 | 370, with a delta and dismissals |
| continuity conflicts, 155k-word novel | 5,821 | **19** |
| engine tests | 169 | **228** |
| ruff | 57 findings | **0** |
| document types | 2 | 3 built in, any number declared |
| input formats | `.md` `.txt` | `+ .docx`, read-only |

Neither guarantee moved. Nothing under `writing_workshop/**` imports
`atk.*`, Qt or any third-party package; the only module that writes
anything outside a named draft is `state.py`, writing `.workshop/`; and
nothing writes into the manuscript but the author.
