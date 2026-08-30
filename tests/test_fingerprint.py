# SPDX-License-Identifier: Apache-2.0
"""The style fingerprint: measurable, per-project, and honest about itself."""

from __future__ import annotations

import unittest

from _base import MANUAL, NOVEL, TempProject
from writing_workshop import Manuscript, Project
from writing_workshop import fingerprint as FP

PLAIN = ("The team finished the task. The system was updated. The results "
         "were checked. The report was filed. The work was done. The day "
         "ended. The lights went out. The building was empty.")
LAYERED = ("Although the team had finished, which nobody had expected, the "
           "system — updated twice that week, and badly — still refused the "
           "checks; the report, filed late, said as much. Because nobody "
           "read it, the building emptied with the question still hanging "
           "in the corridor air, unanswered and, if anyone had asked, "
           "unanswerable. Which was, as these things go, entirely typical "
           "of a week that had begun badly and gone on from there.")


class Windows(unittest.TestCase):
    def test_metrics_are_fitted_per_window(self):
        """A 120,000-word baseline and a sixty-word suggestion are not
        comparable quantities. Fitting on the whole document gives a spread
        so tight that every suggestion scores as an outlier."""
        fp = FP.fit([PLAIN + " " + LAYERED] * 6, sentences=3)
        self.assertGreater(fp.metrics["_windows"], 1)
        self.assertGreater(fp.spread["sentence_words"], 0)

    def test_a_thin_baseline_says_so(self):
        fp = FP.fit([PLAIN])
        self.assertFalse(fp.trustworthy)
        drifts = FP.score(fp, LAYERED)
        self.assertIn("indicative", FP.describe(fp, drifts))


class MATTR(unittest.TestCase):
    def test_vocabulary_variety_does_not_fall_with_length(self):
        """Plain type-token ratio is a length measurement wearing a
        vocabulary costume: a chapter always looks 'more repetitive' than a
        paragraph, and a baseline and a suggestion cannot be compared."""
        tokens = [f"w{i % 40}" for i in range(200)]
        short = FP.mattr(tokens[:60])
        long = FP.mattr(tokens)
        self.assertAlmostEqual(short, long, delta=0.05)
        naive_short = len(set(tokens[:60])) / 60
        naive_long = len(set(tokens)) / 200
        self.assertGreater(naive_short - naive_long, 0.2)


class Drift(unittest.TestCase):
    def setUp(self):
        self.fp = FP.fit([LAYERED] * 8, sentences=2)

    def test_a_flattened_rewrite_scores_as_drift(self):
        drifts = FP.score(self.fp, PLAIN)
        self.assertGreater(FP.drift_score(drifts), 1.5)

    def test_the_description_is_specific_or_it_says_nothing(self):
        text = FP.describe(self.fp, FP.score(self.fp, PLAIN))
        self.assertIn("%", text)
        self.assertIn("Accept it as a change, not as your voice.", text)

    def test_writing_in_the_same_voice_does_not_alarm(self):
        drifts = FP.score(self.fp, LAYERED)
        self.assertLess(FP.drift_score(drifts), 1.5)

    def test_a_flat_metric_cannot_dominate(self):
        """No spread means the baseline never varied on that measure. A
        z-score would be infinite; the fallback is capped so one flat
        metric cannot swamp the summary."""
        fp = FP.fit([PLAIN] * 6, sentences=2)
        for drift in FP.score(fp, LAYERED):
            self.assertLessEqual(abs(drift.z), 20)

    def test_every_drift_names_a_direction_a_human_can_read(self):
        for drift in FP.score(self.fp, PLAIN):
            self.assertTrue(drift.label)
            self.assertIn(drift.direction, (
                "longer", "shorter", "more varied", "flatter",
                "more punctuated", "plainer", "more", "fewer",
                "more layered", "rarer vocabulary", "plainer vocabulary",
                "more repetitive", "more dialogue", "less dialogue",
                "within counting noise"))


class Persistence(TempProject):
    def test_round_trip(self):
        project = Project.open(self.root)
        fp = FP.from_manuscript(project.manuscript())
        FP.save(fp, project.fingerprint_file)
        again = FP.load(project.fingerprint_file)
        self.assertEqual(fp.metrics, again.metrics)
        self.assertEqual(fp.n_words, again.n_words)

    def test_a_missing_file_is_none_not_an_exception(self):
        self.assertIsNone(FP.load(self.root / "nope.json"))

    def test_a_corrupt_file_is_none_not_an_exception(self):
        path = self.root / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(FP.load(path))


class PerProject(unittest.TestCase):
    def test_a_manual_and_a_novel_have_different_fingerprints(self):
        manual = FP.from_manuscript(Manuscript.load(MANUAL))
        novel = FP.from_manuscript(Manuscript.load(NOVEL))
        self.assertNotEqual(manual.metrics.get("dialogue"),
                            novel.metrics.get("dialogue"))


if __name__ == "__main__":
    unittest.main()
