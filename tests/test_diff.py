# SPDX-License-Identifier: Apache-2.0
"""Sentence-level diff, and the accept surface built on it."""

from __future__ import annotations

import unittest

from _base import *                                  # noqa: F401,F403
from writing_workshop import diff as DF

OLD = ("The housing shall be earthed at all times. Tighten the lid bolts "
       "to 40 Nm. Refit the cover and check the seal.")
NEW = ("The housing shall be earthed at all times. Tighten the lid bolts "
       "to 45 Nm. Refit the cover and check the seal.")


class SentenceLevel(unittest.TestCase):
    def test_one_word_change_is_one_hunk_not_a_paragraph_rewrite(self):
        """A paragraph is one line. A line differ renders a one-word change
        as a whole-paragraph rewrite, which destroys the only thing a
        version feature exists to provide."""
        hunks = DF.diff(OLD, NEW)
        changed = DF.changed(hunks)
        self.assertEqual(len(changed), 1)
        self.assertEqual(len(changed[0].old), 1)
        self.assertIn("40 Nm", changed[0].old[0])

    def test_rewrapping_a_paragraph_is_not_a_change(self):
        """Otherwise every reflow in an editor becomes a hundred hunks and
        the diff is noise again — the line-diff failure, one level down."""
        rewrapped = OLD.replace(". ", ".\n")
        self.assertEqual(DF.changed(DF.diff(OLD, rewrapped)), [])

    def test_spans_point_into_both_texts(self):
        hunk = DF.changed(DF.diff(OLD, NEW))[0]
        self.assertEqual(OLD[hunk.old_span[0]:hunk.old_span[1]],
                         hunk.old[0])
        self.assertEqual(NEW[hunk.new_span[0]:hunk.new_span[1]],
                         hunk.new[0])

    def test_inline_shows_the_word(self):
        hunk = DF.changed(DF.diff(OLD, NEW))[0]
        ops = DF.inline(hunk.old[0], hunk.new[0])
        self.assertIn(("delete", "40"), ops)
        self.assertIn(("insert", "45"), ops)


class Applying(unittest.TestCase):
    def test_taking_one_hunk_leaves_the_rest_alone(self):
        hunks = DF.diff(OLD, NEW)
        taken = {DF.changed(hunks)[0].id}
        self.assertEqual(DF.apply(OLD, hunks, taken), NEW)

    def test_taking_nothing_changes_nothing(self):
        hunks = DF.diff(OLD, NEW)
        self.assertEqual(DF.apply(OLD, hunks, set()), OLD)

    def test_insertions_and_deletions_round_trip(self):
        old = "One. Two. Three. Four."
        new = "One. Two and a half. Three. Four. Five."
        hunks = DF.diff(old, new)
        self.assertEqual(DF.apply(old, hunks, None), new)

    def test_the_separators_survive_every_ordinary_edit(self):
        """2026-10-28: five of six of these came back corrupted —
        `One. Two.Three.`, a deleted paragraph leaving four newlines, an
        inserted paragraph glued on as `B two.C three.`."""
        cases = [
            ("One. Three.", "One. Two. Three."),
            ("Two. Three.", "One. Two. Three."),
            ("A one.\n\nB two.\n\nC three.", "A one.\n\nC three."),
            ("A one.\n\nC three.", "A one.\n\nB two.\n\nC three."),
            ("A one. B two.", "A one."),
            ("A one. X two. Y three. D four.", "A one. D four."),
            ("# Title\n\nFirst line. Second.",
             "# New title\n\nNew first line. Second."),
            ("A1. A2.\n\nB1.", "A1.\n\nB1."),
            ("", "New text here."),
            ("Old text.", ""),
        ]
        for old, new in cases:
            hunks = DF.diff(old, new)
            self.assertEqual(DF.apply(old, hunks), new, (old, new))
            self.assertEqual(DF.apply(old, hunks, set()), old, (old, new))

    def test_round_trip_over_random_edits(self):
        """The property, not a list of examples: take everything and you
        get `new`, take nothing and you get `old`, take any subset and no
        two sentences are glued together and no blank lines pile up."""
        import random
        import re as _re
        from writing_workshop import textio as T
        rng = random.Random(20261028)
        words = ["the", "river", "ran", "cold", "past", "the", "mill",
                 "and", "nobody", "spoke", "of", "it", "again", "until",
                 "winter", "came"]

        def sentence():
            w = rng.sample(words, rng.randint(3, 8))
            w[0] = w[0].capitalize()
            return " ".join(w) + rng.choice([".", "!", "?"])

        def sentences(text):
            return [text[s:e] for s, e in T.sentences(text)]

        for _ in range(400):
            blocks = []
            for _b in range(rng.randint(1, 6)):
                if rng.random() < 0.2:
                    blocks.append("## " + " ".join(rng.sample(words, 3)))
                else:
                    blocks.append(" ".join(sentence()
                                           for _s in range(rng.randint(1, 4))))
            tail = rng.choice(["", "\n"])
            old = "\n\n".join(blocks) + tail
            paras = [[b] if b.startswith("#") else sentences(b)
                     for b in blocks]
            for _e in range(rng.randint(1, 4)):
                op = rng.choice(["ins", "del", "rep", "ins_p", "del_p"])
                if op == "ins_p":
                    paras.insert(rng.randint(0, len(paras)), [sentence()])
                elif op == "del_p" and len(paras) > 1:
                    paras.pop(rng.randrange(len(paras)))
                else:
                    i = rng.randrange(len(paras))
                    if paras[i][0].startswith("#"):
                        continue
                    j = rng.randrange(len(paras[i]))
                    if op == "ins":
                        paras[i].insert(j, sentence())
                    elif op == "del" and len(paras[i]) > 1:
                        paras[i].pop(j)
                    elif op == "rep":
                        paras[i][j] = sentence()
            new = "\n\n".join(" ".join(p) for p in paras) + tail
            hunks = DF.diff(old, new)
            self.assertEqual(DF.apply(old, hunks), new)
            self.assertEqual(DF.apply(old, hunks, set()), old)
            ids = [h.id for h in hunks if h.changed]
            pick = set(rng.sample(ids, rng.randint(0, len(ids))))
            got = DF.apply(old, hunks, pick)
            self.assertIsNone(_re.search(r"[.!?][A-Z#]", got), got)
            self.assertNotIn("\n\n\n", got)
            self.assertNotIn("  ", got)

    def test_apply_never_touches_disk(self):
        """Nothing writes into the manuscript but the author. `apply`
        returns text; whether it becomes the book is a keystroke."""
        import inspect
        source = inspect.getsource(DF)
        self.assertNotIn("write_text", source)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
