# SPDX-License-Identifier: Apache-2.0
"""The manuscript: files on disk, structure derived from them."""

from __future__ import annotations

import unittest

from _base import MANUAL, NOVEL, TempProject
from writing_workshop import Manuscript, Project


class Structure(unittest.TestCase):
    def setUp(self):
        self.doc = Manuscript.load(MANUAL)

    def test_sections_in_reading_order_across_files(self):
        titles = [s.title for s in self.doc.sections]
        self.assertEqual(titles, ["Operator Manual", "Glossary",
                                  "Servicing the housing", "Reassembly"])

    def test_the_authors_own_number_is_kept(self):
        """A reference to a number the reader cannot see is a reference
        this tool invented, so cross-reference checking has to compare
        against the author's numbering, not a derived one."""
        numbers = {s.title: s.number for s in self.doc.sections}
        self.assertEqual(numbers["Servicing the housing"], "4.2")
        self.assertEqual(numbers["Operator Manual"], "")

    def test_prose_before_the_first_heading_is_still_a_section(self):
        doc = Manuscript.load(NOVEL)
        self.assertTrue(all(s.words for s in doc.sections))

    def test_words_exclude_code_and_tables(self):
        doc = Manuscript.load(MANUAL)
        self.assertGreater(doc.words, 100)
        self.assertNotIn("|", "".join(
            doc.prose_of_file(f.rel) for f in doc.files))

    def test_find_searches_prose_only(self):
        hits = self.doc.find("torque")
        self.assertTrue(hits)
        for span in hits:
            self.assertIn("torque",
                          self.doc.prose_of_file(span.path)[
                              span.start:span.end].lower())

    def test_quote_returns_the_whole_sentence(self):
        span = self.doc.find("40 Nm", whole_word=False)[0]
        self.assertIn("40 Nm", self.doc.quote(span))
        self.assertTrue(self.doc.quote(span).endswith("."))

    def test_scenes_default_to_one_per_chapter(self):
        doc = Manuscript.load(NOVEL)
        chapter = doc.chapters()[1]
        self.assertEqual(len(doc.scenes(chapter)), 1)

    def test_scene_breaks_split(self):
        doc = Manuscript.load(NOVEL)
        chapter = doc.chapters()[0]
        self.assertEqual(len(doc.scenes(chapter)), 2)

    def test_outline_text_is_cheap_and_complete(self):
        text = self.doc.outline_text()
        for section in self.doc.sections:
            self.assertIn(section.title, text)


class DerivedNotStored(TempProject):
    def test_reorganising_the_files_moves_the_outline(self):
        """The outline is derived, never stored. Nothing to get out of
        sync, and the author can reorganise in any editor they like."""
        project = Project.open(self.root)
        before = [s.title for s in project.manuscript().sections]
        (self.root / "02-service.md").rename(self.root / "00-service.md")
        after = [s.title for s in project.manuscript().sections]
        self.assertNotEqual(before, after)
        self.assertEqual(sorted(before), sorted(after))

    def test_nothing_of_ours_is_written_into_the_manuscript(self):
        project = Project.open(self.root)
        project.style_card = "short sentences"
        project.save()
        for path in self.root.glob("*.md"):
            body = path.read_text(encoding="utf-8")
            self.assertNotIn("short sentences", body)
        self.assertTrue((self.root / ".workshop" / "project.json").exists())

    def test_deleting_the_workshop_folder_leaves_the_book(self):
        import shutil
        project = Project.open(self.root)
        words = project.manuscript().words
        shutil.rmtree(project.dir)
        self.assertEqual(Project.open(self.root).manuscript().words, words)


class Ritual(TempProject):
    def test_streak_counts_consecutive_days_only(self):
        project = Project.open(self.root)
        for day, words in (("2026-08-01", 500), ("2026-08-02", 700),
                           ("2026-08-04", 300)):
            project.record_words(day, words)
        self.assertEqual(project.targets.streak, 1)
        project.record_words("2026-08-05", 200)
        self.assertEqual(project.targets.streak, 2)


if __name__ == "__main__":
    unittest.main()
