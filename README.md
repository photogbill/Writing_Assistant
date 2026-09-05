# Writing Workshop

> A workshop that knows the whole document better than the author can hold
> in their head, and never writes in the author's place.

A 200-page technical manual and a 120,000-word novel share one failure
mode — nobody can hold either in working memory — so both break
identically: **the sword is bronze in chapter 3 and steel in chapter 17;
the torque spec is 40 Nm in §4.2 and 45 Nm in the appendix.** Everything
here exists to catch that class of defect.

It is the engine behind ATK's Writing Workshop workspace, and it is a
separate project for the same reason O.W.L. and Cognitive Coder are: the
core knows nothing about its host, so it runs in a terminal, in a test, or
in any other application, with no Qt and no GPU.

```
pip install -e .
workshop craft   path/to/project --remember   # the measurements
workshop craft   path/to/project --new        # only what appeared since
workshop dismiss path/to/project <key> --reason "deliberate"
workshop continuity path/to/project           # contradictions, threads
workshop drift   path/to/project --since before-the-room
workshop checks  path/to/project              # what this build measures
workshop budget  path/to/project --model Magistral-24B --tokens 40960
```

## What makes it different

**Measurement before generation.** Craft checks are arithmetic: fast,
offline, and *incapable of inventing a finding*. A workshop whose first
useful answer comes from a model is one the author has to fact-check; one
whose first answers are measurements has earned the benefit of the doubt
by the time a model speaks. Blocks 1, 2, 2b and 5 of the build need no
inference at all — a usable tool exists with the GPU cold.

**The Codex is an evidence ledger.** Claims are typed (attribute /
relationship / temporal / numeric), carry the passage they came from, and
can be superseded rather than overwritten. Out of that falls the feature
no writing tool has: *"you changed the sword to steel in chapter 17; here
are four passages that describe it as bronze."*

**The style fingerprint.** Every AI writing tool has the same unadmitted
defect — use it long enough and the prose converges on the model's voice,
cumulatively, because each edit looks like an improvement. Fit a
measurable fingerprint on the author's own accepted text, score every
suggestion against it *before* it is offered, and show the drift. It is
the honest answer to "can it write like me?": it cannot, but it can tell
you when it is not.

**Dropped-thread detection.** An entity introduced with emphasis,
developed across three chapters, then absent for twelve with no
resolution. Chekhov's gun, found by arithmetic.

**The book measured against its own past.** The fingerprint scores a
suggestion before it is offered; that catches one sentence at a time,
which is exactly the level at which convergence is invisible — *each edit
looks like an improvement*. So fit the baseline on a draft you name
("before I started using The Room") and score the manuscript as it is now,
chapter by chapter. Nothing new is stored to do it: named versions are
already folders of plain files.

**Findings you can be done with.** Every finding has a content key derived
from what it is about rather than from where it is, so dismissing one
survives the paragraph moving; and the run before this one is remembered,
so the question "what appeared since Monday" has an answer. An afternoon
in one chapter should produce a short list, not the same nine hundred
rows.

**The check you write yourself.** *"Never write 'simply'."* *"Say
'select', not 'click'."* A pattern, a message, a severity, in
`.workshop/rules.json` — offline, incapable of inventing a finding, and
the thing a documentation team asks for first.

## Four rules

1. **Nothing writes into the manuscript but the author.** Not the
   extractor, not the Codex, not a persona, not a "fix all". The moment a
   tool can edit the book without a human keystroke, every other guarantee
   here is a promise rather than a property.
2. **Extraction proposes, never asserts.** Every model-read claim arrives
   as a proposal carrying its passage, and stays proposed until accepted.
3. **Refuse rather than silently degrade.** If the invariant context does
   not fit the model's window, the assembler raises and says so instead of
   dropping the style card.
4. **Say what was not done.** The manifest names what is in view and what
   is not; an estimated token count is called an estimate; a thin style
   baseline says it is thin.

Deliberately **not** built: ChromaDB or FAISS (a store is the host's job),
a hidden repository, and **no autocomplete or ghost text** — the
highest-slop-risk feature in the category, because it trains the author to
accept the model's next word thousands of times a session, below the level
where any of them is a decision.

## What it will not do to be quick

**Nothing is ever dropped for taking too long.** There is no time budget
in any pass and there must not be one. An operator who has offloaded
layers to the CPU has *chosen* to wait, and a check the tool abandoned on
a timer is a silent gap in a report whose fourth rule is that it says what
it did not do. A slow pass gets progress and a cancel button; the decision
to stop is the operator's.

That is also why the sentence splitter's cost was a defect rather than a
tuning problem. It was quadratic — a copy and a scan of the whole
remainder of the file for every `.!?…` — so a craft pass over an 81,000-
word document did not finish in five minutes. It is linear now, byte for
byte the same output, and the same pass takes about three seconds. Being
fast is not the point; being *able to finish* is.

## The manuscript is never locked inside the tool

A project is a folder of `.md`, `.txt` or (read-only) `.docx` files. **The outline is derived, never
stored** — the headings in the files are the structure, so there is
nothing to get out of sync and the author can reorganise in any editor
they like. Everything this package knows lives in one `.workshop/` folder
beside them — the project settings, the Codex, your style baseline, the
findings you dismissed, the passages you took from The Room. Delete it and
you still have the book, and a `.docx` is never written to at all.

## Layout

| Module | What it is |
|---|---|
| `textio` | blocks, sentences, words, syllables — all with file offsets |
| `document`, `project` | the manuscript on disk, structure derived |
| `units` | the unit table, conversion, and stated precision |
| `craft/` | the measurements: shared, technical, fiction |
| `context/` | the six-band assembler and the budget meter |
| `codex/` | typed claims, provenance, supersession, reconsider |
| `continuity/` | contradictions, threads, chronology, name drift |
| `fingerprint` | the author's own voice, measured |
| `room/`, `diff`, `versions` | assistance, last, and never destructive |
| `export/` | Shunn manuscript format and numbered `.docx` structure |
| `readaloud` | passages on demand, chapters as a batch |
| `ports` | everything the host provides, with a working default for each |
| `findings` | a finding's identity, the dismissal list, the delta |
| `state` | the one module that writes `.workshop/` side files |
| `rules` | the project's own checks, declared rather than coded |
| `doctypes` | technical, fiction, lyrics — and the ones a project declares |
| `drift` | the manuscript against a named earlier draft |
| `influence` | which prose came from The Room, kept out of the manuscript |
| `formats` | `.docx`, read-only, standard library |
| `cast` | who is in this book, when the project has not said |

`adapters/atk/` is **outside** the package on purpose: nothing under
`writing_workshop/**` may import `atk.*` or PySide6, and a test in this
repo fails the build if it ever does.

**What `adapters/atk/` is NOT, stated because it used to say otherwise.**
It is a REFERENCE implementation of a host, not the adapter ATK ships. ATK
has its own — `atk/core/writing.py`, `atk/core/writing_host.py` and
`atk/ui/writing_panel.py` — which has since grown three pages this copy
has never had (Storyline, Draft, Author Styles) and is three times the
size. ATK does not read this folder at all. Keep it as the worked example
of the ports; do not treat it as the current ATK surface, and do not fix a
bug here expecting ATK to change.

## Hosting it

Implement the Protocols in `ports.py` — structurally, with no inheritance
and no import of our base classes. Every one ships a default that actually
works, so `Host()` is a complete host with no model:

```python
from writing_workshop import Manuscript, Project, Host
from writing_workshop.craft import run

project = Project.open("D:/Books/the-bronze-sword")
report = run(project.manuscript(), project.document_type)
for finding in report.problems():
    print(finding.severity, finding.title)
```

## Tests

```
python -m unittest discover -s tests -t tests
```

225 checks, no third-party dependency, no Qt, no model. They are
`unittest`-style deliberately: a pytest-only suite is silently collected as
*nothing* by `unittest discover`, which reports OK while tests are failing,
and a suite that can lie about being green is worse than no suite.

Apache-2.0.
