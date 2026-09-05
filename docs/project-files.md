# What lives in `.workshop/`, and what each file is for

The manuscript is a folder of `.md`, `.txt` or (read-only) `.docx` files.
Everything the workshop knows about it lives in one `.workshop/` folder
beside them. **Delete `.workshop` and you still have the book**, which is
the test this layout exists to pass.

Every file here is written by one module — `writing_workshop.state` — and
`tests/test_boundary.py` fails the build if anything else opens a file for
writing outside a short named list. An allow-list that grows by one entry
per feature is not a guard, and this one is the whole reason the author's
editor is the only thing that touches the book.

| File | Written by | What it is |
|---|---|---|
| `project.json` | `project.py` | document type, language, style card, cast, terms, targets |
| `codex.db` | `codex/store.py` | the claims ledger, with its journal |
| `fingerprint.json` | `fingerprint.py` | the author's measured style baseline |
| `versions/` | `versions.py` | named drafts, as folders of plain files |
| `dismissed.json` | `state.py` | findings the author has decided about |
| `last-run.json` | `state.py` | the previous run's keys, for the delta |
| `influence.json` | `state.py` | passages accepted from The Room |
| `rules.json` | *the author* | the project's own checks |
| `doctypes.json` | *the author* | document types this project declares |

A `house.json` may sit **above** the project — at most four directories up
— and every project under it inherits its style card, rules, terms,
glossary titles and craft settings. Inherited, never copied in: change the
house file and every project follows, which is the only reason to have
one.

---

## `rules.json` — the check you write yourself

Every other check is a Python function inside the package, which means the
thing a documentation team asks for first is the thing they cannot have.
A rule is a pattern and a message. It runs with the GPU cold, it cannot
invent a finding, and it says exactly what it matched.

```json
{
  "rules": [
    {
      "id": "no-simply",
      "phrase": "simply",
      "severity": "warn",
      "message": "“simply” tells the reader the thing they are stuck on is easy",
      "hint": "Delete it. It never adds information."
    },
    {
      "id": "no-first-person-in-steps",
      "scope": "steps",
      "pattern": "\\b(?:I|we|our)\\b",
      "ignorecase": false,
      "severity": "warn",
      "message": "a procedure step written in the first person"
    }
  ]
}
```

| Field | Default | Meaning |
|---|---|---|
| `id` | `rule-N` | how the rule is named in findings, and what a project overrides a house rule by |
| `phrase` | — | a literal, matched whole-word |
| `pattern` | — | a regular expression; use this or `phrase` |
| `message` | — | what the finding says |
| `hint` | — | the detail line under it |
| `severity` | `warn` | `note`, `warn` or `defect` |
| `scope` | `prose` | `prose` (masked — no code, no tables), `raw`, `headings`, `steps` |
| `files` | all | an `fnmatch` pattern against the file's relative path |
| `ignorecase` | `true` | |
| `whole_word` | `true` | applies to `phrase` only |
| `enabled` | `true` | |

`workshop rules PATH --init` writes a starter file if there is not one.

**A broken rule reports itself.** A pattern that will not compile becomes
a `defect` finding naming the rule and the error, rather than going quiet.
A rule the author believes is running and is not is worse than no rule —
it is the failure the rest of this package spends `skipped`,
`not_checked` and "estimated" on avoiding.

---

## `doctypes.json` — a document type this package never met

Three types ship built in: `technical`, `fiction`, `lyrics`. A project may
declare more. A profile selects from the checks that exist; it cannot
carry code, because a type that could would be a plugin system, and a
plugin system is how a package with zero dependencies acquires some.

```json
{
  "doctypes": [
    {
      "key": "release-notes",
      "label": "Release notes",
      "base": "technical",
      "drop": ["readability", "passive", "long_steps"],
      "options": {"echo_window": 60},
      "blurb": "Short, repetitive, and read by people in a hurry."
    }
  ]
}
```

`base` says whose checks to inherit; `add` and `drop` adjust the list;
`options` sets thresholds the profile wants by default. A project may not
shadow a built-in type, and an unknown type still measures — it falls back
to the technical checks rather than to an empty report, because a project
whose `doctypes.json` was deleted must still open.

---

## `dismissed.json` — being done with a finding

```json
{
  "version": 1,
  "entries": {
    "5c2bfbab2b79": {
      "check": "steps",
      "title": "Step numbering broken in §4.2 Servicing the housing",
      "reason": "deliberate — the renumber is in the next revision",
      "at": "2026-09-05 03:31:09",
      "severity": "defect"
    }
  }
}
```

The key is derived from **what the finding is about** — the check, the
subject drawn from the check's own data, the title with numbers
normalised, the quoted evidence — and deliberately **not** from an offset.
A paragraph that moves is the same finding. A sentence that is rewritten
is a new one, and should be: what the author dismissed is no longer there.

There is no auto-dismissal, no confidence threshold and no "clear all". A
dismissal is an act by the author, recorded with a date and a reason, and
reviewable: `workshop dismiss PATH --list`, and `--restore KEY` to undo
it. A decision you cannot review is a decision you cannot undo.

---

## `influence.json` — which prose came from The Room

`fingerprint.fit` has always said that fitting a baseline on a draft
containing the model's rewrites *"bakes the drift into the baseline, and
the tool then reports that everything matches beautifully — the exact
failure it exists to prevent"*. Nothing tracked it, so the defence grew
weaker exactly as it was used more.

What is recorded is the **text** the author accepted, not a span: a span
recorded on Tuesday points at the wrong characters on Wednesday. It is
re-located when needed, which has a property worth having on purpose —
once the author has rewritten an accepted passage past recognition, it
stops counting as the model's, because by then it is theirs.

Nothing is written into the manuscript to do this. No marker, no comment,
no span in the file.
