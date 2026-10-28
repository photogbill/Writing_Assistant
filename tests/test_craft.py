# SPDX-License-Identifier: Apache-2.0
"""The measurements. Arithmetic, and it cannot invent a finding."""

from __future__ import annotations

import unittest

from _base import MANUAL, NOVEL
from writing_workshop import DEFECT, FICTION, Manuscript, TECHNICAL
from writing_workshop.craft import REGISTRY, run


class Technical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = Manuscript.load(MANUAL)
        cls.report = run(cls.doc, TECHNICAL,
                         terms=["PSU", "bleed valve", "torque wrench"])

    def checks(self, name):
        return self.report.by_check(name)

    def test_nothing_was_skipped(self):
        self.assertEqual(self.report.skipped, {})

    def test_the_torque_spec_defect(self):
        """40 Nm in §4.2 and 45 Nm in §4.3. Two values for one named
        quantity is a defect, full stop, and it needs no model."""
        found = self.checks("units")
        self.assertTrue(found)
        self.assertEqual(found[0].severity, DEFECT)
        self.assertIn("torque", found[0].title)

    def test_units_compare_after_conversion(self):
        """`40 Nm` and `29.5 lb-ft` are the same figure. Reporting them as
        a conflict would be the check inventing one."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.md"
            path.write_text(
                "# T\n\nThe torque is 40 Nm.\n\nElsewhere the torque is "
                "29.5 lb-ft.\n", encoding="utf-8")
            report = run(Manuscript.load(tmp), TECHNICAL)
            self.assertEqual(report.by_check("units"), [])

    def test_broken_cross_references(self):
        titles = [f.title for f in self.checks("xrefs")]
        self.assertTrue(any("9.9" in t for t in titles))
        self.assertTrue(any("Figure 7" in t for t in titles))
        self.assertTrue(all(f.severity == DEFECT for f in self.checks("xrefs")))

    def test_live_cross_references_are_not_reported(self):
        titles = " ".join(f.title for f in self.checks("xrefs"))
        self.assertNotIn("Section 4.2", titles)
        self.assertNotIn("Figure 1", titles)

    def test_step_numbering_gap(self):
        found = self.checks("steps")
        self.assertTrue(found)
        self.assertEqual(found[0].data["numbers"], [1, 2, 3, 5])

    def test_long_step(self):
        found = self.checks("long_steps")
        self.assertTrue(found)
        self.assertGreaterEqual(found[0].data["words"], 30)

    def test_glossary_definitions_are_seen(self):
        """The default glossary titles live in ONE place. When they were
        defaulted only in `Project`, any caller without one got an empty
        list and three defined terms were reported as never defined."""
        self.assertEqual(self.report.metrics["definitions"], 3)

    def test_terminology_drift(self):
        titles = " ".join(f.title for f in self.checks("terminology"))
        self.assertIn("wifi", titles.lower().replace("-", ""))

    def test_echo_ignores_the_documents_own_vocabulary(self):
        """`torque` nine times in the torque procedure is the document
        working correctly. A check that reports it is one the author
        switches off within a day, taking the real findings with it."""
        words = {f.data.get("word", "").lower() for f in self.checks("echo")}
        self.assertNotIn("torque", words)

    def test_readability_is_a_note_never_a_defect(self):
        for finding in self.checks("readability"):
            self.assertEqual(finding.severity, "note")


class Fiction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = Manuscript.load(NOVEL)
        cls.report = run(cls.doc, FICTION)

    def test_fiction_checks_ran_and_technical_ones_did_not(self):
        self.assertIn("pacing", self.report.ran)
        self.assertNotIn("steps", self.report.ran)

    def test_dialogue_ratio_measured(self):
        self.assertIn("dialogue_ratio", self.report.metrics)

    def test_opening_run_flagged(self):
        found = self.report.by_check("openers")
        self.assertTrue(found)
        self.assertEqual(found[0].data["word"], "the")


class Registry(unittest.TestCase):
    def test_every_check_declares_the_documents_it_applies_to(self):
        for name, reg in REGISTRY.items():
            self.assertTrue(reg.applies, name)
            self.assertTrue(reg.label, name)

    def test_one_failing_check_does_not_cost_the_others(self):
        """An empty craft page is indistinguishable from a clean
        manuscript, which is the worst outcome this module has."""
        from writing_workshop.craft import Registered
        broken = Registered("boom", "Boom",
                            lambda ctx: (_ for _ in ()).throw(RuntimeError(
                                "deliberate")), (TECHNICAL,))
        REGISTRY["boom"] = broken
        try:
            report = run(Manuscript.load(MANUAL), TECHNICAL)
        finally:
            del REGISTRY["boom"]
        self.assertIn("boom", report.skipped)
        self.assertIn("units", report.ran)


class TheChecksThatUsedToCryWolf(unittest.TestCase):
    """2026-10-28. False positives are the most expensive thing a check can
    produce: an author switches a noisy check off and loses the real
    findings with the noise."""

    def _run(self, text, only):
        import tempfile
        from pathlib import Path
        from writing_workshop import Project
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.md").write_text(text, encoding="utf-8")
            project = Project.open(tmp)
            return run(project.manuscript(), TECHNICAL,
                       profile=project.profile(), only=only)

    def test_a_plural_is_not_a_cross_reference(self):
        report = self._run(
            "# 1 Pump\n\nThe following sections describe the pump. All "
            "figures are drawn to scale, the tables list the parts, and "
            "this is the section a reader needs. The part I liked.\n\n"
            "See Section 1.\n", ["xrefs"])
        self.assertEqual(report.findings, [])

    def test_a_derived_number_does_not_hide_a_dead_reference(self):
        report = self._run(
            "# Preface\n\nHello.\n\n# Safety\n\nCare.\n\n"
            "# 3 Service\n\nSee Section 5.\n", ["xrefs"])
        self.assertEqual([f.title for f in report.findings],
                         ["“Section 5” does not resolve"])

    def test_two_supplies_are_two_quantities(self):
        report = self._run(
            "# 1 Power\n\nThe logic supply is 3.3 V and the main supply "
            "is 12 V.\n\n# 2 Wheels\n\nTighten the wheel nuts to 110 Nm."
            "\n\n# 3 Plugs\n\nTighten the spark plugs to 25 Nm.\n",
            ["units"])
        self.assertEqual([f for f in report.findings
                          if f.severity == DEFECT], [])

    def test_mm_and_m_are_not_two_spellings(self):
        report = self._run(
            "# 1\n\nThe gap is 2 mm. The gap is 3 mm. The gap is 4 mm. "
            "The cable length is 2 m.\n", ["units"])
        self.assertFalse([f for f in report.findings
                          if "written several ways" in f.title])

    def test_milli_and_mega_are_not_the_same_unit(self):
        from writing_workshop import units as U
        self.assertFalse(U.conflict("1", "MW", "1000", "kW"))
        self.assertTrue(U.conflict("10", "mW", "10", "MW"))
        self.assertTrue(U.conflict("3", "V", "3.3", "V"))
        self.assertFalse(U.conflict("40", "Nm", "29.5", "lb-ft"))
        self.assertFalse(U.conflict("10–20", "Nm", "15", "Nm"))
        self.assertTrue(U.conflict("10–20", "Nm", "25", "Nm"))

    def test_a_sign_and_an_ohm_are_read(self):
        from writing_workshop import units as U
        self.assertEqual(U.split_value("below -40 °C"), ("-40", "°C"))
        self.assertEqual(U.split_value("a 10 kΩ resistor"), ("10", "kΩ"))
        self.assertEqual(U.split_value("steps 1 to 5 in order"), ("1", ""))
        self.assertEqual(U.split_value("take 5 a day"), ("5", ""))


if __name__ == "__main__":
    unittest.main()
