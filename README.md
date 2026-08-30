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
workshop craft   path/to/project     # the measurements
workshop continuity path/to/project  # contradictions, threads, names
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

## The manuscript is never locked inside the tool

A project is a folder of `.md` files. **The outline is derived, never
stored** — the headings in the files are the structure, so there is
nothing to get out of sync and the author can reorganise in any editor
they like. Everything this package knows lives in one `.workshop/` folder
beside them. Delete it and you still have the book.

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

`adapters/atk/` is **outside** the package on purpose: it is the only code
that imports `atk.*` and PySide6, and a test in this repo fails the build
if anything under `writing_workshop/**` ever does.

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

168 checks, no third-party dependency, no Qt, no model. They are
`unittest`-style deliberately: a pytest-only suite is silently collected as
*nothing* by `unittest discover`, which reports OK while tests are failing,
and a suite that can lie about being green is worse than no suite.

Apache-2.0.
