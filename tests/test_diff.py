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

    def test_apply_never_touches_disk(self):
        """Nothing writes into the manuscript but the author. `apply`
        returns text; whether it becomes the book is a keystroke."""
        import inspect
        source = inspect.getsource(DF)
        self.assertNotIn("write_text", source)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
