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


class KeysThatUsedToCollide(unittest.TestCase):
    """2026-10-28. Version-1 keys blanked every digit, so these pairs were
    ONE key each, and one dismissal hid both — including findings about
    chapters not yet written."""

    def test_one_chapters_flat_rhythm_is_not_every_chapters(self):
        a = _finding("lengths", "Flat rhythm in Chapter 3",
                     evidence=(), section="Chapter 3")
        b = _finding("lengths", "Flat rhythm in Chapter 9",
                     evidence=(), section="Chapter 9")
        self.assertNotEqual(FD.key(a), FD.key(b))
        self.assertEqual(FD.key_v1(a), FD.key_v1(b))     # the old bug

    def test_forty_against_four_hundred_is_not_forty_against_forty_five(self):
        def units(values):
            return _finding("units", "“lid bolts torque” is given 2 "
                            "different values",
                            evidence=(f"§3: {values[0]}",),
                            subject="lid bolts torque", values=values)
        self.assertNotEqual(FD.key(units(["40 Nm", "45 Nm"])),
                            FD.key(units(["40 Nm", "400 Nm"])))

    def test_a_figure_number_is_the_subject_not_a_count(self):
        self.assertNotEqual(
            FD.key(_finding("xref", "Figure 3 is never defined",
                            kind="figure", id="3")),
            FD.key(_finding("xref", "Figure 9 is never defined",
                            kind="figure", id="9")))

    def test_a_count_in_a_spelling_list_is_still_not_the_identity(self):
        a = _finding("terminology", "2 spellings of one term: “Wi-Fi” ×3, "
                     "“WiFi” ×1", forms={"Wi-Fi": 3, "WiFi": 1})
        b = _finding("terminology", "2 spellings of one term: “Wi-Fi” ×4, "
                     "“WiFi” ×1", forms={"Wi-Fi": 4, "WiFi": 1})
        self.assertEqual(FD.key(a), FD.key(b))

    def test_craft_records_the_section_a_title_names(self):
        from writing_workshop import Manuscript
        from writing_workshop.craft import run as run_craft
        import tempfile
        from pathlib import Path
        sentence = "The man walked to the shop and bought some bread. "
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for n in (1, 2):
                (root / f"0{n}.md").write_text(
                    f"# Chapter {n}\n\n" + sentence * 14, encoding="utf-8")
            report = run_craft(Manuscript.load(root), "fiction",
                               only=["lengths"])
        flat = [f for f in report.findings if f.title.startswith("Flat")]
        self.assertEqual(len(flat), 2)
        self.assertEqual({f.data.get("section") for f in flat},
                         {"Chapter 1", "Chapter 2"})
        self.assertNotEqual(FD.key(flat[0]), FD.key(flat[1]))


class DismissalsSurviveTheUpgradeAndTheEditor(TempProject):   # noqa: F405
    def setUp(self):
        super().setUp()
        self.store = Store(self.root / ".workshop")
        self.path = self.root / ".workshop" / "dismissed.json"

    def _write(self, text):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def test_a_version_1_dismissal_holds_only_the_finding_it_was(self):
        three = _finding("lengths", "Flat rhythm in Chapter 3",
                         evidence=(), section="Chapter 3")
        nine = _finding("lengths", "Flat rhythm in Chapter 9",
                        evidence=(), section="Chapter 9")
        import json
        self._write(json.dumps({"version": 1, "entries": {
            FD.key_v1(three): {"check": "lengths",
                               "title": "Flat rhythm in Chapter 3"}}}))
        marks = FD.Dismissals(self.store)
        self.assertTrue(marks.holds(three))
        self.assertFalse(marks.holds(nine))
        self.assertTrue(marks.remove(three))
        self.assertFalse(FD.Dismissals(self.store).holds(three))

    def test_a_trailing_comma_is_forgiven(self):
        one = _finding(word="valve")
        self._write(f'{{"version": 2, "entries": {{"{FD.key(one)}": '
                    f'{{"title": "x", "reason": "mine"}},}},}}')
        marks = FD.Dismissals(self.store)
        self.assertTrue(marks.holds(one))
        self.assertIn("trailing comma", marks.problem)

    def test_a_file_that_will_not_parse_is_kept_not_overwritten(self):
        broken = '{"entries": {"abc": {"title": "four hundred of these"'
        self._write(broken)
        marks = FD.Dismissals(self.store)
        self.assertEqual(len(marks), 0)
        self.assertIn("could not be read", marks.problem)
        marks.add(_finding(word="valve"))
        kept = list(self.path.parent.glob("dismissed.json.corrupt-*"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(encoding="utf-8"), broken)
        self.assertIn(kept[0].name, marks.problem)

    def test_two_windows_do_not_undo_each_other(self):
        page, cli = FD.Dismissals(self.store), FD.Dismissals(self.store)
        page.add(_finding(word="valve"))
        cli.add(_finding(word="bolt"))
        again = FD.Dismissals(self.store)
        self.assertTrue(again.holds(_finding(word="valve")))
        self.assertTrue(again.holds(_finding(word="bolt")))
        # and a removal in one is not resurrected by the other's save
        page.remove(_finding(word="valve"))
        cli.add(_finding(word="nut"))
        self.assertFalse(FD.Dismissals(self.store).holds(
            _finding(word="valve")))

    def test_a_later_save_does_not_replay_an_earlier_one(self):
        """Found by the independent check: pending changes were never
        cleared, so every later save re-applied them."""
        x, y, z = (_finding(word=w) for w in ("x", "y", "z"))
        a = FD.Dismissals(self.store)
        a.add(x)
        b = FD.Dismissals(self.store)
        b.remove(x)
        a.add(y)
        self.assertFalse(FD.Dismissals(self.store).holds(x))
        c = FD.Dismissals(self.store)
        c.add(z)
        c.remove(z)
        d = FD.Dismissals(self.store)
        d.add(z)
        c.add(x)
        self.assertTrue(FD.Dismissals(self.store).holds(z))

    def test_a_last_run_from_another_key_version_is_not_compared(self):
        self.store.write("last-run.json", {"version": 1, "keys": {
            "aaaaaaaaaaaa": "old"}})
        out = FD.triage([_finding(word="valve")],
                        previous=FD.previous(self.store))
        self.assertFalse(out.had_previous)
        self.assertEqual(out.gone, [])


if __name__ == "__main__":
    unittest.main()
