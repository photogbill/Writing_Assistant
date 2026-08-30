# SPDX-License-Identifier: Apache-2.0
"""Contradictions, dropped threads, name drift and chronology."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from _base import MANUAL, NOVEL
from writing_workshop import DEFECT, Manuscript, WARN
from writing_workshop import codex as CX
from writing_workshop import continuity as CN


def doc_from(text: str, name: str = "a.md"):
    tmp = tempfile.mkdtemp()
    Path(tmp, name).write_text(text, encoding="utf-8")
    return Manuscript.load(tmp)


class Contradictions(unittest.TestCase):
    def test_numeric_conflicts_are_stated_flatly(self):
        doc = Manuscript.load(MANUAL)
        conflicts = CN.contradictions.find(CX.deterministic(doc))
        numeric = [c for c in conflicts if c.kind == "numeric"]
        self.assertEqual(len(numeric), 1)
        self.assertTrue(numeric[0].deterministic)
        self.assertEqual(numeric[0].severity, DEFECT)

    def test_attribute_conflicts_are_candidates_with_both_passages(self):
        """An attribute conflict is a reading. The author adjudicates; the
        tool never "fixes" anything."""
        doc = Manuscript.load(NOVEL)
        claims = CX.attribute_claims(doc, ["sword"])
        conflicts = CN.contradictions.find(claims)
        self.assertEqual(len(conflicts), 1)
        self.assertFalse(conflicts[0].deterministic)
        self.assertEqual(conflicts[0].severity, WARN)
        finding = CN.sweep(doc, claims).findings[0]
        self.assertEqual(len(finding.evidence), 2)

    def test_a_superseded_claim_is_not_re_reported(self):
        """The author already told us the fact changed. Reporting it as a
        contradiction punishes them for using the feature."""
        doc = Manuscript.load(NOVEL)
        claims = CX.attribute_claims(doc, ["sword"])
        claims[0].superseded_by = 99
        self.assertEqual(CN.contradictions.find(claims), [])

    def test_different_dimensions_under_one_name_are_not_a_conflict(self):
        doc = doc_from("# T\n\nThe clearance is 4 mm.\n\nThe clearance is "
                       "3 seconds.\n")
        self.assertEqual(CN.contradictions.find(CX.deterministic(doc)), [])

    def test_two_weekdays_for_one_event(self):
        doc = doc_from("# One\n\nThe wedding is on Wednesday.\n\n"
                       "# Two\n\nThe wedding was Tuesday.\n")
        conflicts = [c for c in CN.contradictions.find(
            CX.temporal_claims(doc)) if c.kind == "temporal"]
        self.assertTrue(conflicts)
        self.assertTrue(conflicts[0].deterministic)


class Threads(unittest.TestCase):
    def build(self):
        chapters = ["# One\n\nThe Kestrel Locket lay on the table. The "
                    "Kestrel Locket had been her mother's, and the Kestrel "
                    "Locket was the only thing she kept.\n"]
        chapters += [f"# Chapter {i}\n\nThey walked on through the rain and "
                     f"said very little to each other that day.\n"
                     for i in range(2, 9)]
        tmp = tempfile.mkdtemp()
        for i, text in enumerate(chapters):
            Path(tmp, f"{i:02d}.md").write_text(text, encoding="utf-8")
        return Manuscript.load(tmp)

    def test_chekhovs_gun_by_arithmetic(self):
        doc = self.build()
        threads = CN.threads.track(doc, ["Kestrel Locket"])
        self.assertEqual(threads[0].count, 3)
        dropped = CN.threads.dropped(doc, threads, min_sections=1)
        self.assertEqual([t.name for t in dropped], ["Kestrel Locket"])

    def test_a_thread_carried_to_the_end_is_not_dropped(self):
        doc = self.build()
        threads = CN.threads.track(doc, ["rain"])
        self.assertEqual(CN.threads.dropped(doc, threads, min_sections=1),
                         [])

    def test_emphasis_notices_a_loud_introduction(self):
        doc = self.build()
        thread = CN.threads.track(doc, ["Kestrel Locket"])[0]
        self.assertGreaterEqual(thread.emphasis, 2.0)


class NameDrift(unittest.TestCase):
    def test_it_proposes_and_never_merges(self):
        doc = doc_from("# One\n\nAleksandr waited. Alexander waited too, "
                       "and Sasha waited longest of all. Aleksandr said "
                       "nothing. Alexander said nothing. Sasha said "
                       "nothing.\n")
        found = CN.namedrift.find(doc, ["Aleksandr", "Alexander", "Sasha"])
        self.assertEqual(len(found), 1)
        self.assertEqual(set(found[0].forms),
                         {"Aleksandr", "Alexander", "Sasha"})
        self.assertTrue(found[0].reason)

    def test_unrelated_names_stay_apart(self):
        doc = doc_from("# One\n\nMira and Kestrel spoke. Mira left. "
                       "Kestrel stayed.\n")
        self.assertEqual(CN.namedrift.find(doc, ["Mira", "Kestrel"]), [])


class Chronology(unittest.TestCase):
    def test_the_timeline_is_a_view_not_an_assertion(self):
        """Flashbacks exist. Tuesday after Wednesday is shown, in reading
        order, and not called wrong."""
        doc = doc_from("# One\n\nOn Wednesday they left.\n\n# Two\n\n"
                       "On Tuesday she had arrived.\n")
        moments = CN.chronology.timeline(doc)
        self.assertEqual([m.text.lower() for m in moments],
                         ["wednesday", "tuesday"])
        self.assertEqual(len(CN.sweep(doc).findings), 0)

    def test_durations_are_collected_per_section(self):
        doc = doc_from("# Steps\n\nWait 20 minutes.\n\n# Summary\n\n"
                       "Allow 15 minutes.\n")
        found = CN.chronology.durations(doc)
        self.assertEqual(len(found), 2)


class Sweep(unittest.TestCase):
    def test_progress_is_reported(self):
        """A forty-section sweep that says nothing for two minutes is
        indistinguishable from a hang, and ATK has shipped that bug."""
        from writing_workshop.ports import CollectingEvents
        events = CollectingEvents()
        doc = Manuscript.load(MANUAL)
        CN.sweep(doc, CX.deterministic(doc), events=events)
        self.assertTrue(events.messages())

    def test_cancellation_stops_between_stages(self):
        class Stop:
            def is_set(self):
                return True
        doc = Manuscript.load(MANUAL)
        result = CN.sweep(doc, CX.deterministic(doc), cancel=Stop())
        self.assertEqual(result.threads, [])

    def test_map_sections_contains_a_failing_section(self):
        doc = Manuscript.load(MANUAL)

        def boom(sec):
            if sec.order == 1:
                raise RuntimeError("deliberate")
            return [sec.id]
        got = CN.map_sections(doc, boom)
        self.assertEqual(len(got), len(doc.sections) - 1)


if __name__ == "__main__":
    unittest.main()
