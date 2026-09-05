# SPDX-License-Identifier: Apache-2.0
"""Finding identity, dismissals, and the delta between runs."""

from __future__ import annotations

import unittest

from _base import *  # noqa: F401,F403

from writing_workshop import findings as FD
from writing_workshop.state import Store
from writing_workshop.types import WARN, Finding, Span


def _finding(check="echo", title="“valve” twice within 12 words",
             evidence=("The valve is a valve.",), **data):
    return Finding(check, WARN, title, evidence=list(evidence),
                   data=dict(data))


class Keys(unittest.TestCase):
    def test_a_key_survives_the_paragraph_moving(self):
        """The whole point: an offset must not be part of the identity."""
        a = _finding(word="valve")
        b = _finding(word="valve")
        a.span = Span("a.md", 10, 20)
        b.span = Span("a.md", 9000, 9010)
        self.assertEqual(FD.key(a), FD.key(b))

    def test_a_count_in_the_title_does_not_change_the_key(self):
        a = _finding(title="3 sentences in a row open with “The”",
                     word="the")
        b = _finding(title="5 sentences in a row open with “The”",
                     word="the")
        self.assertEqual(FD.key(a), FD.key(b))

    def test_a_different_subject_is_a_different_finding(self):
        self.assertNotEqual(FD.key(_finding(word="valve")),
                            FD.key(_finding(word="bolt")))

    def test_rewritten_evidence_is_a_new_finding(self):
        a = _finding(evidence=("The valve is a valve.",), word="valve")
        b = _finding(evidence=("The valve seat is a valve seat.",),
                     word="valve")
        self.assertNotEqual(FD.key(a), FD.key(b))

    def test_stamp_fills_the_field(self):
        rows = [_finding(word="valve"), _finding(word="bolt")]
        FD.stamp(rows)
        self.assertTrue(all(f.key for f in rows))


class DismissAndDelta(TempProject):                   # noqa: F405
    def setUp(self):
        super().setUp()
        self.store = Store(self.root / ".workshop")

    def test_a_dismissed_finding_stays_dismissed(self):
        one = _finding(word="valve")
        marks = FD.Dismissals(self.store)
        marks.add(one, reason="deliberate", at="2026-09-05")
        again = FD.Dismissals(self.store)
        self.assertTrue(again.holds(one))
        self.assertEqual(again.reason(one), "deliberate")

    def test_dismissed_findings_are_hidden_but_not_lost(self):
        rows = [_finding(word="valve"), _finding(word="bolt")]
        marks = FD.Dismissals(self.store)
        marks.add(rows[0])
        out = FD.triage(rows, dismissals=marks)
        self.assertEqual(len(out.shown), 1)
        self.assertEqual(len(out.hidden), 1)

    def test_restoring_a_dismissal(self):
        one = _finding(word="valve")
        marks = FD.Dismissals(self.store)
        marks.add(one)
        self.assertTrue(marks.remove(one))
        self.assertFalse(FD.Dismissals(self.store).holds(one))

    def test_the_delta_names_what_is_new(self):
        first = [_finding(word="valve")]
        FD.remember(self.store, first, at="2026-09-05")
        second = [_finding(word="valve"), _finding(word="bolt")]
        out = FD.triage(second, previous=FD.previous(self.store))
        self.assertTrue(out.had_previous)
        self.assertEqual([f.data["word"] for f in out.fresh], ["bolt"])
        self.assertEqual(out.gone, [])

    def test_the_delta_names_what_went_away(self):
        FD.remember(self.store, [_finding(word="valve"),
                                 _finding(word="bolt")])
        out = FD.triage([_finding(word="valve")],
                        previous=FD.previous(self.store))
        self.assertEqual(len(out.gone), 1)

    def test_with_no_previous_run_nothing_is_called_new(self):
        """A first run must not report every finding as new — that is a
        lie the operator would learn to ignore the delta over."""
        out = FD.triage([_finding(word="valve")], previous={})
        self.assertEqual(out.fresh, [])
        self.assertIn("no previous run", out.summary())

    def test_a_corrupt_store_costs_the_feature_and_not_the_book(self):
        (self.root / ".workshop").mkdir(parents=True, exist_ok=True)
        (self.root / ".workshop" / "dismissed.json").write_text(
            "{not json", encoding="utf-8")
        self.assertEqual(len(FD.Dismissals(self.store)), 0)


if __name__ == "__main__":
    unittest.main()
