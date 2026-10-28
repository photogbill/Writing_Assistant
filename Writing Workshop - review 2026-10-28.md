# Writing Workshop — review, 2026-10-28

> Bill asked: *"look over the writing assistant and tell me if we have
> anything left to build, and also comprehensively go through it and suggest
> improvements."*
>
> Scope: the engine (`D:\Analyst_Toolkit\Writing Assistant`, ~11,000 lines +
> 3,000 of tests) and ATK's side of it (`atk/core/writing*.py`,
> `atk/ui/writing_panel.py`, `storyline.py`, `drafting.py`,
> `continuation.py`, `authors.py`, `editable.py`, `prose.py`, `jsonish.py`,
> ~17,000 lines). **No code was changed.** This file is the only thing
> written.
>
> **How it was checked.** Four independent review passes plus my own, each
> required to reproduce a defect before reporting it. I then re-ran or
> re-read the most serious findings myself; those are marked **(re-run)**.
> The rest are marked **(reviewer)**: reproduced by one pass, not
> repeated by me. Nothing here has run on Windows, and no Qt page was built
> for this review.
>
> **Baseline.** Engine suite: 257/257 under `unittest`, both on your machine
> (Python 3.10, 18 s) and in the container. A 151,000-word, 30-chapter
> synthetic novel ran craft in 5.8 s and continuity in 3.5 s, so speed is
> fine.
>
> Each heading has an ID so a later build can mark it ✅ in place, the way
> the 2026-09-05 review was.

> **BUILD, 2026-10-28 (same day).** Bill: *"Please go ahead and fix it."*
> Scope as agreed: every Part 2 defect (D1–D31), the repository hygiene
> list, and the two Part 1 items tangled up with the bugs (L1, L8). New
> features (L2–L7, L9–L12) and Part 3 were NOT built, except where an
> improvement is the fix itself (the project lock is I7's first half; the
> budgeted brief is I3; keying numbers by object is I4's first half).
> Each item below carries a ✅ line saying what was done. **Nothing was
> committed.** Engine 1.2.0 → **1.3.0**, and ATK now requires 1.3.0.
>
> Tests: engine **350/350** under both `unittest` and `pytest` (pytest
> collected none before); ATK's writing tests **565 passed**, including
> 14 new offscreen Qt tests (`tests/test_writing_safety.py`) that build the
> real Manuscript page against a real project on disk, and 30 in
> `tests/test_drafting_review_fixes.py`. Every new test that pins a defect
> was run against the old code first and failed there. Still not run on
> Windows.
>
> **Then an independent check of the fixes**, by a reviewer that had not
> written them, found ten more bugs — eight introduced or left by this
> build — and all ten are fixed and tested:
> * UTF-16 chapters lost their CRLF and big-endian byte order on Save.
> * A file Save had converted to UTF-8 went back to cp1252 on the next Save.
> * Qt turns a no-break space into a space, so any chapter containing one
>   was "unsaved" untouched, and Save rewrote them all.
> * °C and °F were compared as one unit.
> * "Tighten the 4 bolts to 40 Nm" read as a 4–40 Nm range.
> * Dismissals replayed old changes on a later save.
> * Valid JSON with curly quotes inside a value was refused.
> * Shunn dropped prose written straight under the book's title heading.
> * `<I love you>` and TeX ``quotes'' were masked as markup.
> * Rewrite-selection refused wrongly in a file with emoji.
>
> It also raised several plausible issues, which are fixed too:
> * The sweep now still sees a passage that keeps a superseded value.
> * Codex `revise` is guarded against a claim decided mid-edit.
> * A failed commit rolls back.
> * Versions survive a row missing a field, report a missing index, and
>   never list a save that died mid-copy.
> * A failed Save leaves no temporary file behind.
> * Side files with a BOM are read.
> * Thinking sidecars are written atomically.
> * An outline with no file bindings yet no longer binds a chapter to its
>   predecessor's file by number.
>
> **Two corrections to this review.** L11's session ritual is not
> "never started": the engine has it (`Project.targets`,
> `Project.record_words`); only the ATK door is missing. And D30 was wrong
> about `drafting.py` — it did log, through its own `_log()`.

> **SECOND BUILD, 2026-10-28 (afternoon).** Bill: *"Let's build them
> all."* Scope: everything on the "what's next" list — I1, I2, I4, the rest
> of I7, I10–I13 and L2–L7, L9–L12. NOT built: I3's remaining half, I5, I6
> beyond L8, I8, I9, I14. Each item carries a ✅ line. **Nothing was
> committed.** Engine 1.3.0 → **1.4.0**, and ATK now requires 1.4.0.
>
> Tests: engine **368/368**; ATK **617 passed**, including
> `tests/test_writing_features.py` (offscreen Qt pages against a real
> project on disk) and `tests/test_structured_calls.py`. The GBNF grammars
> were compiled with llama-cpp-python 0.3.16 in the container. Not run on
> Windows, and no grammar has been run against a real model yet.
>
> Found while building, and fixed:
> * "I Will Email You" was read as section "I" (any title starting with a
>   capital letter and a space).
> * A Suno tag longer than 40 characters was read as a sung line.
> * `[Verse 2: Valkyrie, cold Heldentenor]` was a different section from
>   `[Verse 1]`, so repeats were never compared.
> * Read-aloud merged paragraphs into one passage and gave the whole
>   exchange to the first speaker.
> * A place written "the lighthouse" counted as named in any chapter with
>   the word "the"; "Harbour Street" in any with "street". Places now need
>   their whole name (article dropped), in the Draft check too.
>
> **Then an independent check of this build** (a reviewer that had not
> written it, required to reproduce what it reported) found fifteen
> problems. All are fixed and have tests:
> * "Record voice type…" over a Storyline that could not be read (bad
>   JSON, a sync tool holding the file) saved a one-character outline over
>   the whole plan. It now refuses, and `storyline.json` is written
>   atomically.
> * Autosave wrote the SAVED concept over the unsaved one a crash had left.
>   Filling the box no longer counts as typing, and an unsaved text that is
>   not put back is moved to a name of its own first.
> * Spec sheet → Rename on a "(not named)" row threw the quantity away
>   ("torque" became the component and vanished).
> * Read aloud read only the text above a chapter's first sub-heading;
>   skipped lines that failed to speak and still said "done"; and would
>   not join voices at 16 and 22.05 kHz (a mixed Piper cast). It now reads
>   the whole chapter, converts formats, and refuses a chapter with a
>   missing line or a voice the author did not choose.
> * Model per stage decided whether to swap before taking the AI queue, so
>   two routed jobs could run on the wrong model. It now decides inside
>   the hold, refuses when Setup records no model to put back, swaps the
>   local core only, and a model that could not be put back is the last
>   line on the page, not covered by "Done."
> * Cancel did nothing for three Draft jobs, and after a read-aloud batch
>   did nothing for The Room.
> * The Room could hand a passage into a Word file's read-only buffer.
> * Lyric alignment compared verses across different songs in one file.
> * `[Chorus x2]`, `[Verse II]` and a character called Bridget were
>   "misspelt tags"; "over a heavy bass drop" was a voice-lock defect.
> * The numbered `.docx` made code comments into headings.
> * A checkbox was read on a worker thread; a lone speaker showed as
>   "nearest voice at 0.0"; the outline report read chapters in list
>   order; dictation during another job lost the recording's path.
>
> One behaviour to know: a stage with a model routed to it holds ATK's AI
> line for its whole job (a priority ticket still steps in), so a routed
> whole-book run keeps other AI work waiting.

---

## The short version

**The build plan is finished.** Every block in the plan's §8 order exists.
What is left to build is mostly **doors**: features the engine already has
that the ATK workspace never connects to (lyrics above all), plus four
items the plan named that were never started.

**The bigger news is defects, and several are serious.** Six of them
quietly break features you would assume work:

1. **The Codex cannot be used from a background job** (D1). In ATK,
   Continuity → Sweep fails with its default setting, Codex → "Read what
   can be read" and "Ask the model" fail, and the Draft page drafts chapters
   *without your accepted facts* and says nothing.
2. **Save on a `.docx` replaces the Word file with plain text** (D2).
3. **The model's thinking sidecars, `outline.md` and your exports are read
   back in as chapters of the book** (D3). They are measured, mined for
   claims, exported in the Shunn manuscript, and can be drafted into.
4. **The thinking-stripper can delete real prose** (D4). One line of
   dialogue such as *"Nobody touches this scene until forensics gets
   here"* sent 70% of a clean scene to the sidecar.
5. **The numeric check, the headline feature for manuals, reports every
   different spec as a contradiction** (D8). Wheel nuts at 110 Nm against
   spark plugs at 25 Nm is a "certain" defect; a 3.3 V logic supply against
   a 12 V main supply is a defect.
6. **The style-drift score calls two thirds of your own writing "not you"**
   (D10).

Suggested order is at the end. The first five items are small changes with
large effects.

---

## Part 1 — What is left to build

### Built, tested, and unreachable from ATK

✅ **L1 — built.** The picker lists `project.doctypes()` (built-ins, house and project types, Lyrics included); The Room resolves personas and `is_fiction` through `profile().base`; two lyric personas were added (a line editor for sung lines, and **The Singer** as the adversary).

**L1. Lyrics, and any declared document type, cannot be chosen in ATK.**
`writing_panel.py:1418` offers "Technical document" and "Fiction" only. The
engine has had `LYRICS` built in since 1.1.0 (`craft/lyrics.py`: syllables
per line, refrains compared between tagged stanzas, rhyme-scheme drift), and
the Settings dialog can *create* document types that the project then cannot
use. Two knock-on gaps:
* The Room shows an **empty persona list** for lyrics or any declared type,
  with no explanation. `personas.for_document` matches the raw key, not the
  profile's `base` (re-run).
* `Project.is_fiction` is `document_type == "fiction"`, so a declared
  fiction-based type ("novella") is shown as a technical document, and the
  Storyline page treats it as non-fiction.

Fix: list `project.doctypes()` in the picker, resolve personas and
`is_fiction` through `profile().base`, and add lyric personas (see I12).
**For The Turing Accords this is the single most useful door to open.**

✅ **L2 — built.** The Room → "Read chapters aloud…": pick chapters, a narrator voice, and a voice per speaker; each speaker's voice type on record is shown beside them, and anyone without a voice is named before anything runs (they fall back to the narrator, said so). Each chapter, sub-sections included, goes through the render queue line by line and is joined into one WAV under the project's `audio\\` folder (voices at different sample rates are converted). A chapter with a line that could not be spoken, or a voice Piper replaced with its default, is refused and named, never joined with a hole in it. A paragraph now always ends a passage.

**L2. Chapter read-aloud as a batch was never connected.**
`readaloud.chapter_jobs` / `render_job` have no caller. The design
decision was *"chapters as a batch through render_queue — queue, walk away,
listen on headphones."* Today The Room reads at most 2,000 characters, in
one voice, and never calls `assign_voices`, so the per-character voices and
the voice-type rule never apply.

✅ **L3 — built.** Manuscript → "What would fit?" reads the model headers in your folders (on demand, never at start-up) and adds *"Load X for N tokens — and the whole manuscript fits"* under the meter.

**L3. The Budget Meter's third line.** `writing_host.alternatives()`
(*"Load Qwythos-9B for 75,448 and the whole manuscript fits"*) is written
and never called. One button beside the meter.

✅ **L4 — built.** Author Styles → "New from text…" fits a profile from sample files you choose, through `authors.fit_profile`.

**L4. Fitting an author profile straight from text.** `authors.fit_profile`
still has no caller, as on the 2026-09-10 inventory. Author Styles can fit
only from the open manuscript's fingerprint.

✅ **L5 — built.** Craft → "Does everybody sound the same?" — `fingerprint.speaker_report`: each speaker's nearest other voice, pairs closer than 1.0, and who has too little dialogue to measure. Only the words inside quotes are measured now. `by_group` and `chronology.durations` still have no caller.

**L5. "Does everybody in this book sound the same?"**
`fingerprint.by_speaker` (a fingerprint per character from their dialogue)
is reachable from the CLI (`workshop fingerprint --speakers`) but not from
ATK. `by_group` (separate baselines for procedures vs explanation) has no
caller anywhere.

✅ **L6 — built.** The Room and Versions mark the changed words inside a one-for-one replaced sentence (`diff.inline`); everything shown is escaped.

**L6. Word-level highlighting inside a changed sentence.** `diff.inline`
exists and nothing uses it. The Room and Versions show whole sentences.
`chronology.durations` is likewise uncalled.

✅ **L7 — built.** Versions → Export offers "Shunn manuscript format (.docx)" (Courier New 12 pt, double-spaced, 1" margins, contact block, *about N words*, running header with a PAGE field from page 2, a page per chapter, centred `#`, THE END) and "Numbered + contents (.docx)" (Word headings, real tables, code blocks kept as code, and a TOC field — Word fills it on "Update field"). Needs python-docx; without it the page says so.

**L7. `.docx` export is one step short.** Versions → Export writes `.md`
only, and the status line tells you to put it through ATK's report exporter
yourself. `reports.markdown_to_docx` exists, so offer "Shunn (.docx)" and
"Numbered + contents (.docx)" directly. (Fix D11 first.)

✅ **L8 — built.** `WorkshopState.cast()` is the project's cast, or the Storyline's characters when the project has none. Craft, Codex extraction, Continuity, The Room and the Draft page's ports all read it. (Threads and places → `terms` was not done.)

**L8. The Storyline's cast never reaches the checks.** Nothing ever writes
`project.cast`, yet Continuity, Craft, Codex extraction and The Room all
read it (`writing_panel.py:1750, 2072, 2412-2416, 2705, 5100-5107`). So a
novel whose characters are fully defined on the Storyline page is checked
as if it had no cast, and falls back to name-guessing, which has its own
defects (D12). Storyline threads and places could feed `terms` and thread
tracking the same way.

### Planned, never started

✅ **L9 — built.** Storyline → "Models per stage…": a model for Storyline passes, drafting, reading claims and The Room. A routed job holds the AI queue for the whole job, decides inside it whether to swap, and puts yours back with Setup's exact settings (unless you untick that) — and always when the stage's model fails to load. Refused when Setup records no model to put back. Never with the online core. Author Styles rewrites and Continuity are not routed.

**L9. Model routing per stage** (plan §4b): outline on a 24B, continuity on a
9B with the whole book in view, extraction on a small grammar-constrained
model. Nothing in the workspace routes; one model does everything.

✅ **L10 — built.** ATK's spellcheck is attached to the editor (your personal dictionary as before; the cast and terms are taught to it in memory on each refresh, nothing written). "Dictate" records through `VoiceRecorder` into ATK's temp folder, transcribes with Whisper using the cast as the prompt, and inserts at the cursor.

**L10. Spell-check and dictation in the Manuscript editor.** The plan's
audit counted both as already in ATK (`ui/spellcheck.py`, `VoiceRecorder` +
Whisper). Neither is used by `writing_panel.py`.

✏️ **L11 — correction.** The engine has it — `Project.targets` and `Project.record_words`. What is missing is only the ATK door. Not built.

✅ **L11 — built.** A session bar under the editor: today's words against the daily target, the streak, and a timer with a session target ("Targets…"). The day starts from the manuscript's count when you first open it that day; words are recorded through `Project.record_words`.

**L11. Session ritual** (plan §5): word-count target, a timer, a streak.

✅ **L12 — built.** Storyline → "Places → map". Only a place's new "Where (real world)" field is placed — `lat, lon` as given, else ATK's offline gazetteer, else a single exact-name hit in the imported extract. The place NAME is never geocoded. Everything else goes to the map's unplaced rail with the reason. Nothing reaches the network.

**L12. Research crossover** (plan §5): a novel's places on the Geospatial
canvas.

---

## Part 2 — Defects

### Tier 1 — data loss, or a feature silently not working

✅ **D1 — fixed.** One shared connection opened with `check_same_thread=False` behind an `RLock`; transactions nest by depth and commit once at the outside, rolling back on an exception. `add_many` is one transaction. Kept the rollback journal rather than WAL, and the module says why. Tests: `SharedBetweenThreads`.

**D1. The Codex's SQLite connection is used across threads.** (re-run)
`codex/store.py:73` opens with the default `check_same_thread=True`. Pages
fetch `self.state.codex` on the GUI thread, then use it inside `run_task`
jobs on `QThreadPool` (`writing_panel.py:2073, 2097, 2414, 2697`;
`_DraftPorts` 5076, 5104, 5172, 5192). Python raises `ProgrammingError:
SQLite objects created in a thread can only be used in that same thread`.
* Continuity → Sweep fails whenever "Include accepted Codex claims" is
  ticked, which is the default (2379).
* Codex → "Read what can be read" and "Ask the model" always fail, so the
  Codex can only be filled by typing claims in.
* The Draft page and the whole-book run catch it, so chapters are drafted
  with **no accepted facts**, nothing is proposed, and there is no log line.

Fix: open a short-lived `CX.Codex(path)` inside each job, or open with
`check_same_thread=False` behind a lock and switch to WAL. Batch `add_many`
into one commit while you are there.

✅ **D2 — fixed.** A derived file (`.docx`) opens read-only; Save is disabled for it and refuses it even if something unlocks the editor. Offscreen Qt test proves the Word file's bytes are unchanged.

**D2. Manuscript Save overwrites a `.docx` with plain text.** (re-run)
`_load_current` (1579-1593) never checks `src.derived`; `_save` (1598)
`write_text`s to the `.docx` path. One keystroke enables Save. Afterwards the
file is no longer a zip and drops out of the manuscript. The README promises
*"a .docx is never written to at all."* Fix: read-only editor, Save
disabled, and a line saying why.

✅ **D3 — fixed.** Thinking sidecars go to `.workshop/thinking/`; exports and `outline.md` go to `exports/`, which the loader skips. The loader also skips any `*.thinking.md` left from before (and `notes()` says so); `find_chapter_file` never binds one.

**D3. Files the workspace writes into the project root become part of the
book.** (re-run) The loader takes every `.md` that is not a dotfile or in a
skipped folder (`document.py:45, 124-135`). Three writers put `.md` files
in the root:
* `NN-title.thinking.md` beside each drafted chapter (5139, 6504);
* `outline.md` (4924);
* Export's default target, `<root>/<name>.md` (3026). Each export then
  contains the previous one.

Repro: one chapter plus its sidecar exports a Shunn manuscript with a chapter
titled **"Thinking — Chapter 1"**. Also (reviewer): once the author renames a
chapter file, `find_chapter_file` can return the **sidecar**. The next brief
then quotes the scratch paper as "the author's own prose", and an overwrite
drafts into it. This is the 2026-09-02 "thinking in the manuscript" incident
coming back through a different door.

Fix: sidecars to `.workshop/thinking/`, `outline.md` and exports to
`exports/` (already skipped), and `*.thinking.md` skipped in the loader and
in `find_chapter_file` for files already out there.

✅ **D4 — fixed.** Dialogue is never reasoning; an announced cut is honoured only on the first paragraph or straight after reasoning; an unterminated think block is all reasoning with no prose, reported as a defect. The clean scene that lost 70% now keeps 1,099 of 1,099 words.

**D4. `prose.split` deletes real prose, and keeps unfinished thinking.**
(re-run)
* The cut lands at the **last** reasoning-shaped paragraph anywhere in the
  reply (`_shape_cut` 390-404, `_announced_cut` 375-387, `_tail_trim`
  346-348). A clean 159-word scene with *"Nobody touches this scene until
  forensics gets here," Tom said…* at paragraph 7 kept **48 words**. My run
  set `uncertain=True`; the reviewer's longer scene kept 432 of 1,099 words
  with `uncertain=False` and no finding.
* A reply cut off inside `[THINK]` comes back with `prose` = the raw reply,
  `[THINK]` and all. The drafting retry keeps the longer reply, so the
  reviewer's autopilot run wrote a chapter file starting
  `[THINK]Okay, the scene should open on Mara…` (reviewer).

Fix: thinking is a **prefix**. Cut only at the end of a contiguous run of
reasoning paragraphs that starts at paragraph 1. An unterminated think
block with nothing after it should return `""` and record a defect. Drop
bare `word(s)`, `beat`, `scene` and `tone` from `_CRAFT`; a novelist uses
them in dialogue.

✅ **D5 — fixed.** `WorkshopState.open` refuses while any page has a job running and names the jobs; the Draft ports capture the project they were started in.

**D5. A job's results land in whichever project is open when it finishes.**
(re-run, by reading)
`WorkshopState.open()` has no busy check. `_DraftPorts._path` re-reads
`state.project` on every call (5039). Switch projects during an overnight
whole-book run and chapter N is written into the *other* project's
`NN-*.md`, with no snapshot. At the end the run saves project A's outline
over B's `storyline.json` (6581). The same pattern is in Plan scenes/stretches
(5950, 5999), "From my own writing" (3724-3726, which also assigns
`state.fingerprint` from the worker thread), Craft's last-run record
(1768-1775) and The Room's baseline (2653). Fix: refuse to open a project
while any page has a job running, and capture paths when a job starts.

✅ **D6 — fixed.** Dirty tracking; confirm before switching section, opening a project or reverting; a clean editor reloads when the file changes on disk (a Versions restore shows up); Save asks before writing over a newer file; encoding and line endings are kept. Offscreen Qt tests for each.

**D6. The Manuscript editor loses or reverts text.** (re-run, by reading)
* No unsaved-changes check: picking another section (1572-1577) or opening a
  project reloads the buffer. `_load_current`'s `force` argument is never
  read.
* No reload after another writer: Draft Save, Versions → Restore and the
  autopilot all rewrite files, and `_save` has no modified-time check.
  Restore a version, fix one typo in the editor, Save: the restore is undone.

Fix: keep a dirty flag and the loaded file's modified time. Prompt when
dirty, and prompt on Save if the file changed underneath.

✅ **D7 — fixed.** Hunks carry the gaps between sentences and `apply` rebuilds separators from them. 0 failures in 9,000 random round-trips (3,500 before), plus a 400-iteration property test in the suite.

**D7. `diff.apply` corrupts spacing and paragraph breaks.** (re-run)
5 of my 6 round-trip cases failed: `One. Two.Three.`, `One.Two. Three.`, a
deleted paragraph leaving `\n\n\n\n`, an inserted paragraph glued on as
`B two.C three.`, and a deleted last sentence leaving a trailing space. The
Room's "Take" uses it (2774), and the author then copies that box into the
book. Separately (reviewer), Take applies hunks computed against the
passage box as it was when the answer arrived (2741 vs 2774), so editing the
box first lands them at the wrong offsets. Fix: take replacement text from
`new[span]` with its own separators, keep the source text the diff was made
from and refuse if the box differs, and add a property test
`apply(old, diff(old, new)) == new`.

### Tier 2 — the headline checks give wrong answers

✅ **D8 — fixed.** `units.quantities` reads WHAT a number is about ("torque for the lid bolts", "Tighten the wheel nuts to", "40 Nm on the lid bolts"); case-sensitive SI prefixes (mW ≠ MW); ranges; exact comparison within one unit and stated-precision intervals across units. A bare quantity is a defect within a section and only a WARN candidate across sections. Wheel nuts vs spark plugs no longer conflict.

**D8. Numbers are compared by quantity word across the whole book.**
(re-run)
* Codex: a numeric claim's subject is just the quantity
  (`claims.py:160`, `types.py:233`). "The torque for the wheel nuts is
  110 Nm" against "…for the spark plugs is 25 Nm" →
  `!! [contradiction] torque: 110 Nm … 25 Nm`, certain, and the CLI exits 1.
  N specs give N(N−1)/2 defects. `select.governing` then hands the
  spark-plug section *"torque = 110 Nm"* as an established fact (reviewer).
* Craft `units`: "logic supply 3.3 V", "main supply 12 V" → DEFECT
  "supply is given 2 different values".
* Recall gap: "Tighten the wheel nuts to 110 Nm", which is how manuals are
  actually written, yields **zero** claims.
* Precision (re-run): `conflict(1 MW, 1000 kW)` is True and
  `conflict(10 mW, 10 MW)` is False, because units are matched
  case-insensitively and stored lower-case. `conflict(3 V, 3.3 V)` is False,
  because a same-unit integer carries ±0.5. Also (reviewer): no sign, so
  −40 °C is read as 40; "10–20 Nm" becomes 20; "10 kΩ" is read as
  kelvin; "steps 1 to 5" reads as 5 inches.

Fix: key on object plus quantity (the noun phrase: "wheel nut torque"),
compare a bare quantity word only within one section, make the m/M
prefixes case-sensitive, compare same-unit values as written, and capture
sign and ranges. Read the imperative "<verb> the X to N unit" form. See I4.

✅ **D9 — fixed.** Word boundary, a separator and a capital id are required; derived numbers are used only when the author numbered nothing. The build plan went from 15 "broken" references to 4 genuine ones.

**D9. Cross-references: plurals are reported as broken references.**
(re-run) `craft/technical.py:390` `_XREF` has no word boundary after the
kind word, and under `re.I` `[A-Z]` matches lower case. "The following
sections describe… All figures… the tables list the parts" → **4 DEFECTs**
in one paragraph. The plan document itself gets 15. Also (reviewer, 411):
references resolve against parser-derived numbers, so with an unnumbered
Preface, "See Section 5" quietly resolves to the author's §3 and a dead
reference is hidden.

✅ **D10 — fixed.** The score is the RMS over every measured metric, not only the ones past 1.5; sentence-distribution metrics are skipped below three sentences and MATTR below 50 words, instead of reading one sentence as "flatter than you". Windows of your own writing flagged: 64% → 1.9%.

**D10. The drift score flags most of your own writing.** (re-run, by
reading) `fingerprint.drift_score` (282) is the RMS of only the *notable*
z-scores, so one of twelve metrics past 1.5 puts the whole score past 1.5.
Fitted on 20k words and scored on its own windows: **66% read as "not
you"**; RMS over all metrics flags 0% (reviewer). One-sentence suggestions
are always flagged, because `sentence_spread` is 0 for one sentence. Fix:
RMS over all metrics, and skip spread-type metrics under about three
sentences. Better still, see I8.

✅ **D11 — fixed.** A single top heading over children is a title over chapters; word count rounds the Shunn way (nearest 100 / 500 / 1,000 by length).

**D11. Shunn export drops chapters nested under a title heading.** (re-run)
`# The Long Road` / `## Chapter One…` exports as the title, then `THE END`,
with no prose, because `doc.chapters()` sections stop at the next heading of
any level. Word count (`shunn.py:40-46`) rounds to the nearest *thousand*
between 1,500 and 10,000 (1,507 → 2,000; Shunn's own example rounds 1,507 to
1,500), and anything under 50 words says "about 0 words".

✅ **D12 — fixed.** A calendar table and its use-as-date test; both `cast.detect` and `threads.candidates` drop months and days used as dates and split "March Ellis"-style matches.

**D12. Name-finding has two detectors, and both mis-read the calendar.**
(re-run)
* `cast.detect` proposes **Tuesday, Thursday, Monday and Friday** as cast
  members on a 150k-word book. Months are not in the common-word list
  either.
* `threads.candidates` (regex at `continuity/threads.py:132`) joins a
  sentence opener to the name after it. "Then Mira left… When Mira
  returned… After Mira read it… On Tuesday Mira rode" gives the threads
  `Then Mira`, `When Mira`, `After Mira` and `Tuesday Mira`. Name drift
  then proposes **"Then Mira" / "When Mira" — one or two characters
  apart.**

Fix: one detector (`cast.detect`) with a calendar stop-list, used by
threads, the Codex and name drift alike, and fed by the Storyline cast (L8).

✅ **D13 — fixed.** A lone `~~~` between blank lines is a scene break, an unclosed fence is a stray line, inline code needs equal backtick runs and cannot cross a blank line, and only real HTML tags are masked.

**D13. Masking blanks real prose.** (re-run)
* A `~~~` scene break opens a code fence that runs to the end of the file:
  15 words in, 2 kept.
* `<Where are you?>` (telepathic or AI dialogue) and `<Enter>` are blanked as
  HTML tags.
* (reviewer) A code span can cross a blank line, so a stray backtick plus a
  later one blanks everything between them.

Nothing reports any of it. Word counts, echo, dialogue and POV silently
lose the text. Fix: an unclosed fence is a paragraph, code spans stop at a
blank line, and `_TAG` matches real HTML tag names only.

✅ **D14 — fixed.** Same claim = key + value + section + quote hash, rejected claims included; `add_many(new_only=True)` reports only new proposals; the sweep uses `CodexStore.for_sweep`, which drops what the author rejected or superseded and uses their stored version of the rest.

**D14. Re-extraction ignores the author's decisions.** (reviewer)
* A rejected claim comes back as a new proposal on the next extract.
* Inserting one paragraph re-proposes an *accepted* claim, because the
  dedupe key includes "para N".
* `workshop continuity` re-extracts from scratch, so it still prints a
  conflict the author rejected.

Related:
* A quote of `"."` or `"the"` passes the quote check (`extract.py:115`).
* "Excalibur was bronze" is filed under predicate `is` while "the steel
  Excalibur" is filed under `material`, so the headline sword case never
  meets itself (`claims.py:240-253`).
* `reconsider` matches numbers without checking dimension, so after a
  torque change "rated for 40 kg" and "after 40 s" come back as certain
  (`reconsider.py:63-68`).

Fix: dedupe on key, value, section and a hash of the quote, including
rejected claims; have continuity read the store.

✅ **D15 — fixed.** `supersede` validates the old claim (accepted or proposed) and is one transaction; `correct` refuses a rejected claim; correcting a superseded claim keeps it superseded.

**D15. Claim state-machine holes.** (reviewer)
* `correct()` on a SUPERSEDED claim leaves **two accepted values**
  (bronze → steel by supersession, then correct bronze to brass: steel and
  brass both accepted).
* `supersede()` doesn't check the old claim, so `supersede(99999, …)`
  creates an accepted claim and journals a non-existent one.
* Multi-step operations commit part-way.

Fix: validate state, and run each operation as one transaction.

### Tier 3 — drafting with small models

✅ **D16 — fixed.** Repairs trailing commas, thousands separators and smart-quote delimiters; a newline ends a runaway string; `_rows` takes the last list of objects and keeps the complete rows of a truncated array.

**D16. Valid model output is thrown away.** (reviewer) `jsonish` returns
None for:
* a trailing comma;
* `"target_words": 90,000`;
* smart-quoted keys;
* a truncated array of complete rows;
* a reasoning preamble containing `6'8"`.

`_rows` also takes the last list in the reply, so a closing remark like
*I used the names ["Tom","Ines"]* replaces the real character array.

Stretch plans go through the *prose* splitter (`continuation.py:691-695`),
and one malformed plan raises inside the scene loop. Two of those in a row
hit `give_up_after=2` and **end the overnight run**. Fix: a repair pass
before `json.loads`, salvage complete objects on truncation, catch per
scene and fall back to one pass — and see I1.

✅ **D17 — fixed.** `Chapter.file` binds a chapter to its file; `renumber` remaps thread chapters and `first_chapter` on delete, move and apply.

**D17. Renumbering binds a chapter to its predecessor's file.** (reviewer)
Delete or move a chapter and the outline renumbers, but files are found by
number prefix and nothing is renamed (`storyline.py:3975-3993, 4639`, against
5012). After deleting chapter 1, "The Window" becomes chapter 1, resolves to
`01-Arrival.md`, and an overwrite replaces Arrival's prose.
`Thread.chapters` and `first_chapter` are not remapped either. Fix: a stable
chapter id in the scaffold.

✅ **D18 — fixed.** Values compared after normalising punctuation and typography; states move, traits clash; the author's Codex facts are not listed as generated; units not doubled.

**D18. The run Ledger is noisy and breaks the two-ledger rule.** (reviewer)
* "green" vs "Green." is a contradiction.
* Ordinary state changes (location, injury) are contradictions too.
* Chapter 4's brief still binds `Mara · location: the lighthouse` from
  chapter 1.
* **Accepted Codex facts are rendered under the "GENERATED, not accepted by
  the author" heading** (`drafting.py:1143-1152, 1557`), which is the one
  confusion the two-ledger design exists to prevent.

Fix: normalise punctuation, split trait from state (I9), keep Codex seeds
out of `established`.

✅ **D19 — fixed.** `thread_chapters` places a thread from the chapters that name it; the resolution is shown only in the chapter where it lands.

**D19. Thread arithmetic does nothing on a model-built outline.**
(reviewer) `thread_state` reads only `Thread.chapters`, which only the
author fills, and only as numbers. It never reads `chapter.threads`, which
the chapters pass fills. So every thread is "running underneath" every
chapter, and chapter 1's brief prints the thread's *resolution*. `carry_of`
matches "The debt to Calloway" on its first word, "The".

✅ **D20 — fixed.** `build_brief(budget_tokens=)` drops named sections in a fixed order and says which; the Draft page passes the measured window through `RunOptions.context_tokens`.

**D20. No prompt budget in the drafting brief.** (reviewer, by arithmetic)
A realistic outline (12 cast, 8 threads, 30 claims, 40 facts, a 400-word
voice card) gives a scene prompt of about 7.4k tokens, plus a 4,096-token
reply. A stretch prompt is about 7.6k, because the full brief is re-sent per
stretch, so continuation mode doesn't shrink the input. `tail()` takes whole
paragraphs, so a file with single-newline paragraphs sends all 5,200 words.
See I3.

✅ **D21 — fixed.** Runs save through a three-way `merge_run` (your edits win); passes are applied on the GUI thread when they finish; editing a scene pins it via `SL.touched`; moving the outline keeps typed concept/form/structure/target.

**D21. Outline edits are lost.** (reviewer; the first two re-read by me)
* Scene and chapter *feel* edits don't set `pinned` (5906, 5932), so the next
  pass wipes them.
* `_feel_changed` saves without emitting `outline_changed`, so the
  Storyline page's stale copy writes the old feel back.
* The inline scene Title and "What changes" cells are editable, and their
  edits are never saved.
* A Storyline pass runs `apply()` on a worker against a captured story. An
  edit made on the Draft page meanwhile reloads it, and the pass result is
  lost while the status says "N added".
* The typed concept and target words are overwritten on reload.

✅ **D22 — fixed.** A Version is saved before the prose is replaced (a test pins the order), and the chapter's encoding and line endings are kept.

**D22. Draft → "Save to chapter" overwrites prose without a Version.**
(re-run) 6480-6494 asks, then writes, and tells you to snapshot it yourself.
Only the whole-book run snapshots. Fix: `Versions(project).save(...)` when
the file already has prose.

✅ **D23 — fixed.** Names match by first or last name with titles stripped; dialogue is stripped before the POV test (curly apostrophes included); placeholders are word-bounded.

**D23. `check_draft` false positives on a sound draft.** (reviewer)
* "the whole tenor of the evening" → *voice type invented: tenor*.
* "Dr. Ines Ruiz" is never matched as named, so she is reported missing, and
  the carry keeps telling the next stretch to introduce her.
* The dialogue strip stops at the apostrophe in "don’t", so a third-person
  draft gets a first-person warning.
* "todo" matches "mastodon".

Also: curly vs straight quotes and dashes defeat exact-quote matching in the
harvest and in `splice`. The cadence trimmer counts "sentences shortening"
and "short last paragraph" as two independent signals, so a stretch that
ends exactly on its `leaves_at` is trimmed.

✅ **D24 — fixed.** The selection's range and text are recorded; the rewrite is inserted only if they are unchanged, otherwise it is refused and said.

**D24. "Rewrite selection" inserts wherever the cursor is when the model
finishes** (1509-1511, 6411-6413). On a CPU-offloaded model that can be
minutes later, after you have selected something else. (reviewer)

### Tier 4 — robustness and edges (reviewer unless marked)

✅ **D25 — fixed.** One decoder (BOM, UTF-16, strict UTF-8, UTF-8 with replacement, cp1252) with a note per file in `notes()`; ATK reads and writes through one helper that keeps the encoding and line endings.

**D25. Encoding.**
* A UTF-8 BOM turns `# Chapter One` into prose.
* A UTF-16 file (Notepad "Unicode") decodes as garbage.
* One stray cp1252 byte turns a whole UTF-8 file into mojibake. None of
  these appear in `notes()`.
* The Draft page reads strict UTF-8 and catches only `OSError`, so a cp1252
  chapter makes its buttons do nothing.
* Save re-encodes the file and turns LF into CRLF.

One shared read/write helper would cover it.

✅ **D26 — fixed.** Content controls read; headings by style name or outline level (localised styles); non-breaking hyphens and symbols kept; text boxes read once as their own paragraph; moveFrom, Fallback and deletions skipped; a leading `#` is escaped; `notes()` says footnotes, comments and headers are not read.

**D26. `.docx` reader gaps** (`formats.py`).
* Content controls (`w:sdt`) are dropped.
* Localised heading styles are not recognised, so the document is one
  section.
* `w:noBreakHyphen` and `w:sym` are dropped: "Wi-Fi" becomes "WiFi" and Ω is
  lost.
* Text-box text is glued on and duplicated from the Choice and Fallback
  copies.
* Tracked-move `w:moveFrom` text is kept.
* A paragraph starting "# of retries" becomes a chapter.
* `notes()` should say that footnotes, comments and headers are not read.

✅ **D27 — fixed.** Key version 2: digits are kept in the subject, in the section a title names (`craft.run` records it) and in a contradiction's values; spelling lists are alphabetical so a count cannot reorder them. Version-1 dismissals still hold, but only for the finding whose title matches exactly. The first run after the update says "no previous run to compare against" once, rather than calling everything new.

**D27. Finding keys collide.** Blanking digits merges findings:
* all "Flat rhythm in Chapter N" findings share one key, so one dismissal
  hides every chapter's, future ones included;
* a dismissed "torque 40 vs 45 Nm" also hides 40 vs 400.

✅ **D28 — fixed.** A trailing comma is forgiven; anything worse is reported (`Store.problems`, shown on the Craft page) and the damaged file is copied to `<name>.corrupt-<time>` before anything replaces it. Unique temp names. `Dismissals.save` re-reads and merges, so two windows don't undo each other. `project.json` is written atomically and a damaged one opens with defaults and a message. A damaged `versions.json` is rebuilt from the version folders, and a new version never reuses an existing folder.

**D28. Side files can be lost.**
* A hand-edited `dismissed.json` with one trailing comma loads as empty, and
  the next dismissal overwrites it.
* `project.json` is written non-atomically, and a truncated one stops the
  project opening.
* `versions.json` the same: a damaged index silently returns `[]`, and the
  next save writes an index with one row.
* A reused version slug writes into the old folder, so a restore
  resurrects a chapter you cut.

✅ **D29 — fixed, all five.** Front matter is no longer a chapter; `.txt` lines like "CHAPTER 7" / "Chapter Seven: The Road" / "PART II" are chapters; a check with nothing to say says why (`CraftReport.quiet`); `"base": ""` round-trips and `"add": "echo"` is one name; `rhyme_key` uses the vowel group and looks through a silent e; `(rise again)` is a backing vocal, `## Chorus` is a tag, and a refrain is compared with its majority version. Per-section loops bisect: 3,000 `.docx` sections now take 0.01 s for `paragraphs()` and 0.04 s for definitions. Also fixed: a headings-scope rule pointed three characters early.

**D29. Smaller engine edges.**
* YAML front matter makes a 0-word phantom chapter per file.
* A `.txt` novel with "CHAPTER 1" lines is one section, so pacing and
  presence run with nothing to say and no skip reason.
* A doctype base of `""` round-trips as technical.
* `rhyme_key` uses the last vowel *letter*: day/way never rhyme, rain/skin
  does, and `(rise again)` backing vocals are read as section tags.
* `paragraphs()` and `definitions` are quadratic in one big file, which a
  `.docx` always is: 3,000 sections take 7.9 s.

✅ **D30 — fixed.** Every silent handler in `writing_panel.py` now logs (27 of them, plus the engine import failure); `writing_host` logs its speech, retrieval, O.W.L. and meter fallbacks; the engine's read-aloud logs a raising speech port; the Draft voice checks log. File dialogs open at the project or the ATK folder. ✏️ `drafting.py` already logged — that part of this item was wrong.

**D30. Silent failures.** (re-run) `writing_panel.py` does not import
`logging` at all and has 29 `except Exception` blocks, many silent
(`_DraftPorts`, `_note_influence`, `_note_fidelity`). `drafting.py`,
`storyline.py` and `continuation.py` have no log calls either;
`writing_host.py` has one. The Room says *"Speech failed — see the log"*,
and nothing logs. This is against your standing rule that
anything built in development logs comprehensively. File dialogs at 1429,
3501, 3604 and 3617 open with no start folder, which on Windows usually
means under `C:\Users`.

✅ **D31 — fixed.** `MIN_ENGINE = "1.3.0"`; a stale engine is shown as missing with the version, its folder and `get_engines.bat /writing`; `status()` reports the module actually imported.

**D31. `writing.status()` has no minimum engine version** (my reading). A 1.1
engine found first would open fine and fail on the first `Codex.revise`.
Its reported path is `find_engine()`'s, not the module actually imported.
Low risk on your machine (no `vendor\Writing_Assistant` clone), cheap to
close.

### Repository hygiene (all re-run)

✅ *Done:* `pythonpath = ["tests"]` (pytest collects all 337); URLs now
`photogbill/Writing_Assistant`; a `.gitignore`; **`untrack_generated.bat`**
takes the tracked `.pyc` and egg-info out of the index once (nothing on
disk is deleted, nothing is committed); README count; ruff clean.
*Not done:* commit messages (yours), moving `adapters/atk/` to `examples/`.
The `install.bat` note was already closed.

* **pytest collects nothing**: 17 collection errors, because the tests do
  `from _base import` and `tests/` is a package. `pythonpath = ["tests"]`
  in `[tool.pytest.ini_options]` makes all 257 pass. `_base.py` claims the
  suite runs under both runners.
* **115 `.pyc` files and 6 `egg-info` files are tracked**, and there is no
  `.gitignore`. `PKG-INFO` shows as modified after every `pip install -e`,
  which it did today.
* `pyproject.toml` `Homepage`/`Source` still point at
  `photogbill/Writing-Workshop`, which does not exist.
* README says 225 checks (it is 257); ruff reports 4 findings in tests
  (the docs say 0).
* All five commits are "Your commit message here". ATK's commit script
  already writes a real summary; worth reusing here.
* `install.bat` line endings are fine now: `.gitattributes` is committed, and
  LF in the index with `eol=crlf` is the normal state. The 09-05
  renormalise note can be closed.
* `adapters/atk/` is honest about being a stale reference copy. It is 55 KB
  that one reviewer still mistook for the live adapter. Moving it to
  `examples/` would end that for good.

---

## Part 3 — Improvements worth making

✅ **I1 — built.** `atk/core/structured.py`: every Storyline pass, the scene and stretch plans and the harvest ask through a GBNF grammar (array or object, with an optional think block first) when the local engine can take one. Models that answer in channels (gpt-oss) are asked free first, with the grammar only if that does not parse. The online core and diffusion models go unconstrained, with `jsonish` as before. Each choice is logged.

**I1. Constrained JSON for every structured pass.** `writing_host` already
takes a `grammar=` argument, and llama.cpp supports GBNF and JSON schema.
Every outline pass, the harvest and the stretch plan can be grammar-bound,
which removes D16's whole class at the source; `jsonish` becomes the
fallback. This is the plan's own §4b ("structure by grammar, not by
parsing"), never applied to the Storyline/Draft half.

✅ **I2 — built.** Prose calls prefill an empty think block (`<think>\n\n</think>` or Mistral's `[THINK][/THINK]`) where the template allows continuing a reply; otherwise they run as before. Draft → "Let it think first" turns it off, and is remembered.

**I2. Don't let prose calls think.** Prefill an empty think block (or use
the model's no-think switch) for drafting calls. The whole reply budget goes
to prose and D4's heuristic is rarely needed. Keep thinking for outline
passes, where it helps.

**I3. Budget the brief.** Give `build_brief` the measured window minus the
reply budget, and drop sections in a fixed order (recall, far-back purposes,
named-only cast, low-relevance facts), listing each in `omitted`. Send
stretches a slim brief: chapter, scene, carry, the scene's cast. This
matters more than anything else for 7–9B models.

✅ **I4 — built** (the keying was the first build's D8). Codex → "Spec sheet…": every numeric claim as component, quantity, value, unit, where and state, with superseded values as history and conflicts marked. Double-click to open the passage; "Rename component…" revises a proposed claim and corrects an accepted one, so the history is kept. Export CSV to `exports\\`.

**I4. Specs keyed by object, and a spec sheet.** Give each numeric claim an
object ("lid bolts" + torque) and let the author merge or split keys in the
Codex. Then add a spec-register view: every component, quantity, value,
unit and location in one table. That turns D8 from noise into the feature a
technical writer would pay for.

**I5. Claim anchors that survive edits.** Store a hash of the quoted
sentence plus the section instead of "para N", and re-locate it on load. A
claim whose quote has vanished becomes *orphaned*, which is exactly when
`reconsider` should run.

**I6. One name vocabulary.** Storyline cast with aliases ("Mara", "Dr.
Ruiz", "Sasha" for Aleksandr) → `project.cast` and `terms` → every check,
the brief, the carry and `check_draft`. This fixes L8 and D12 and most of
D19 and D23 in one move. Feed the same lists to the chapters and scenes
passes and require them to use those names.

✅ **I7 — rest built.** A job banner on every page lists what is running, with Cancel. The Draft box and the Storyline concept autosave (2 s after typing stops) to `.workshop\\unsaved\\` and are offered back on the next open; one that is not put back is moved to a name of its own so nothing overwrites it; the copy is removed once you save.

**I7. Workspace-level busy state and unsaved-work protection.** One banner
listing running jobs, each with Cancel, and "Open project" disabled while
any run. A dirty marker on the Manuscript tab, prompting on section change,
project switch and close. Autosave the Draft box and the Storyline concept
to `.workshop/unsaved/`, so a 40-minute CPU draft survives a crash. Closes
D5 and D6, and most of D21.

**I8. A calibrated drift number.** Report a suggestion's percentile
against the baseline's own windows of the same length instead of a fixed
1.5. It calibrates itself, stays honest for one-sentence edits, and makes
the "quiet number beside the suggestion" mean something.

**I9. A state timeline in the run Ledger.** Harvest `kind: trait | state`.
Clash-check traits only; render each state's *latest* value with its
chapter, so chapter 12 is told where Mara is now, not where she was in
chapter 1.

✅ **I10 — built.** Double-click a Craft finding, a Continuity finding, a Codex claim or a spec-sheet row: the Manuscript page comes to the front with the passage selected.

**I10. Click a finding, land on the passage.** Craft, Continuity and
Reconsider results carry section ids and quotes; the editor opens at the top
of the file. Double-click should open the file scrolled to the passage. The
engine's `SourceFile.clickable` exists for this.

✅ **I11 — built.** The Room → "Put into the editor ▸" replaces the passage in the Manuscript BUFFER if it is still there exactly once (one undo step); you still press Save. Refused, with the reason, for a section that holds a table, code or front matter, for a Word file (read-only in ATK), and when the passage has changed since.

**I11. The Room hands off to the editor.** "Put into the editor" replaces
the exact original passage in the Manuscript buffer if it still matches,
and you still press Save. Two deliberate keystrokes, as now, without the
copy-paste that D7 can corrupt.

✅ **I12 — built.** `lyric_alignment` compares line by line across repeats of the same tag within each song (a note for two repeats, a warning against the median for three or more; a difference of `align_tolerance` is absorbed). The `suno` check: misspelled tags, two voices in one tag, a singer named without a voice, ALL-CAPS words (Roman numerals excepted), parenthetical ad-libs, a song titled with a character's name, style prompt over 1,000 and lyrics over 5,000 characters. `voice_locks`: a tag whose voice contradicts the voice type ON RECORD is a defect, and a character with none on record is named — never guessed. Voice types come from the Storyline, then the Music Workshop's character sheets; Craft → "Record voice type…" writes one to the Storyline, showing the character's history first. The Manuscript tree shows who sings each section and their recorded voice.

**I12. Lyrics as a first-class type** (after L1):
* Line-by-line syllable alignment across repeats of the same tag (verse 1
  line 3 against verse 2 line 3), which matters more for a fixed tune than
  the section median.
* A Suno tag check for unknown or misspelled tags and parenthetical ad-libs.
* Lyric personas in The Room: the singer who must breathe, the listener who
  hears it once.
* Each character's established voice type shown beside their section, never
  guessed. That is your standing rule, and `assign_voices` already enforces
  it.

✅ **I13 — built.** Storyline → "Outline vs manuscript…": chapters with no file or not written, characters never named or first named in a different chapter than planned, a chapter's listed cast or place not named, threads never named, dropped before their last planned chapter, or named outside their plan. Read-only: the outline is not changed.

**I13. Outline vs manuscript.** The Storyline already declares where each
character first appears and which chapters a thread runs through. A report
comparing that plan with where the names actually appear in the files
("Mira is planned in 7 and never named there"; "the ledger thread's last
mention is chapter 9, planned to resolve in 14") would be the dropped-thread
check with the author's own intent as the baseline.

**I14. Round-trip and fuzz tests for everything that writes text.**
`apply(old, diff(old, new)) == new`, version save/restore, `merge_into_file`
and Save over random heading, blank-line, BOM and CRLF edits. D7, D17, D22
and D25 would each have shown up immediately.

---

## Suggested order

1. **D1** — Codex per-job connection. A few lines; it turns the Codex, the
   Continuity sweep and the facts in every drafted chapter back on.
2. **D3** — move sidecars, `outline.md` and exports out of the manuscript;
   skip `*.thinking.md` in the loader.
3. **D2** — `.docx` read-only in the editor.
4. **D4** — prose splitter: prefix-only cut, unterminated think block is a
   defect. Then **I2**.
5. **D5 + D6** — project lock while jobs run; editor dirty flag and
   modified-time check (**I7**).
6. **D8 + D9** — numeric keying by object, the precision fixes, the xref
   plural fix. These are what make a technical manual's report believable.
7. **D7, D10, D11** — diff round-trip, drift score, Shunn nesting.
8. **L1 + I12** — the document-type picker and Lyrics.
9. **L8 + D12 + I6** — one name vocabulary fed by the Storyline.
10. **I1 + I3 + D16** — grammar-bound outline passes and a budgeted brief;
    the biggest quality step for small models.

Everything else can follow in any order.
