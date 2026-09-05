# Two workflows the measurements were missing

## 1. The second run

The first craft pass over a long document is useful. The second one is the
test of whether this is a tool or a demonstration, because it produces the
same findings again — including every one the author already read and
decided about.

On one real 81,000-word document the pass produces **916 findings**: 409
echoes, 333 acronyms, 34 terminology clusters, and — underneath all of
that — the 28 broken cross-references, which are the only `defect`s in the
run and the only things that are certainly wrong.

Three things now stand between that list and the author, and none of them
hides anything:

**A per-check cap.** One check may list 100 findings before the rest
become a single note saying how many there are. The check still runs in
full, the true count is in the metrics, and `max_findings: 0` turns it off.

**Dismissals.** `workshop dismiss PATH <key> --reason "…"`, or "I know
about this ▸" in ATK. The finding stops being listed until "Show
dismissed" brings it back.

**The delta.** `workshop craft PATH --remember` records this run's keys;
the next run knows which findings are new.

```
workshop craft  ~/books/bronze-sword --remember
workshop craft  ~/books/bronze-sword --new        # after an afternoon's work
```

An afternoon in chapter nine should produce twelve findings, not nine
hundred. That is the whole claim.

### Why the key is what it is

A finding's identity is built from the check, what the finding is about
(taken from the check's own `data`), its title with numbers normalised to
`#`, and its first quoted line. It contains **no offset**, so:

* a paragraph that moves is the same finding — the dismissal survives;
* "3 sentences in a row open with The" and "5 sentences in a row open with
  The" are one decision, not two;
* a sentence that is rewritten produces a NEW finding, which is correct:
  the thing the author dismissed is no longer there.

---

## 2. Has the book drifted from the voice it started in?

The style fingerprint was built to answer one question — *use an AI
writing tool long enough and the prose converges on the model's voice* —
and it could only ever ask it one sentence at a time, which is precisely
the level at which the drift is invisible. The module's own words: *"not
through any single bad suggestion — each one looks like an improvement."*

Nothing new is needed to ask it properly. Named versions are already
folders of plain files, the fingerprint already fits per window, and
chapters already exist.

```
workshop versions ~/books/bronze-sword --save "before the Room"
# … eight months …
workshop drift    ~/books/bronze-sword --since before-the-room -v
```

```
Measured against “before the Room” (43,100 words) · overall drift 1.12.
First half 0.41, second half 1.83 — the later chapters sit further from
the baseline, which is the shape a convergence has.
Drift is distance from your own earlier writing. It is not a quality
score, and a deliberate change of style will register exactly like an
accidental one.

   2.31  Chapter Seventeen
         flatter on variety in sentence length (0.19 against 0.44)
         plainer vocabulary on share of uncommon words
```

In ATK the same thing is the **"Style drift since this version ▸"** button
on the Versions page.

### The honest part

That last line of the summary is not a disclaimer, it is the finding. An
author who deliberately tightened their prose over eight months will light
this up and *should*. What the tool contributes is that the change is now
visible and located, rather than being something they suspect at three in
the morning.

### The input that makes it mean anything

The baseline has to be fitted on the author's own prose. Accept twenty
rewrites from The Room and — before this existed — the next baseline
included them, so the tool reported that everything matched beautifully.

Now every accepted passage is recorded in `.workshop/influence.json` (see
[project-files.md](project-files.md)) and the baseline can leave it out:

```
workshop fingerprint ~/books/bronze-sword --exclude-room
```

ATK does this automatically when you fit a baseline from The Room page.

---

## 3. And one thing that is deliberately absent

There is **no time budget** anywhere in this package, and there must not
be one. An operator who has offloaded model layers to the CPU has chosen
to wait; a check the tool abandoned on a timer would be a silent gap in a
report whose fourth rule is that it says what it did not do.

What a slow pass gets is `--progress` (which check, and where it has got
to) and cancellation, which is the operator's decision and not ours.
