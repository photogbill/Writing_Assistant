# SPDX-License-Identifier: Apache-2.0
"""Export that respects the destination."""

from __future__ import annotations

import unittest

from _base import MANUAL, NOVEL
from writing_workshop import Manuscript
from writing_workshop import export as EX


class Shunn(unittest.TestCase):
    def setUp(self):
        self.doc = Manuscript.load(NOVEL)
        self.spec = EX.shunn_spec(self.doc, title="The Bronze Sword",
                                  author="A. Writer",
                                  legal_name="Alexandra Writer",
                                  address=["12 Some Street"],
                                  email="a@example.com")

    def test_word_count_is_rounded_the_way_shunn_rounds(self):
        """'about 74,000 words', never 73,842."""
        self.spec.word_count = 73842
        self.assertEqual(self.spec.rounded_words, 74000)
        self.spec.word_count = 1240
        self.assertEqual(self.spec.rounded_words, 1200)

    def test_the_running_header_is_surname_and_short_title(self):
        self.assertEqual(self.spec.running_header, "Writer / Bronze Sword")

    def test_scene_breaks_become_a_hash(self):
        body = EX.shunn_markdown(self.spec)
        self.assertIn("\n#\n", body)
        self.assertTrue(body.rstrip().endswith("THE END"))

    def test_the_typographic_half_travels_in_the_spec(self):
        """Markdown cannot express double-spacing or a running header, so
        it goes to a .docx renderer as data rather than being lost."""
        self.assertEqual(self.spec.line_spacing, 2.0)
        self.assertEqual(self.spec.font, "Courier New")
        self.assertEqual(self.spec.first_line_indent_inches, 0.5)

    def test_every_chapter_survives(self):
        body = EX.shunn_markdown(self.spec)
        for chapter in self.doc.chapters():
            self.assertIn(chapter.title, body)


class Numbered(unittest.TestCase):
    def setUp(self):
        self.doc = Manuscript.load(MANUAL)

    def test_the_authors_own_numbers_are_used(self):
        """Renumbering on export is how a cross-reference that was correct
        on Friday points at the wrong clause on Monday."""
        body = EX.numbered_markdown(self.doc, title="Manual")
        self.assertIn("4.2 Servicing the housing", body)
        self.assertIn("4.3 Reassembly", body)

    def test_a_contents_list_is_produced(self):
        body = EX.numbered_markdown(self.doc, title="Manual")
        self.assertIn("## Contents", body)
        for line in EX.toc_lines(self.doc):
            self.assertIn(line.strip(), body)

    def test_only_the_markdown_subset_atk_already_renders(self):
        body = EX.numbered_markdown(self.doc, title="Manual")
        for unsupported in ("<div", "|:--", "$$"):
            self.assertNotIn(unsupported, body)


class Plain(unittest.TestCase):
    def test_nothing_is_lost(self):
        doc = Manuscript.load(MANUAL)
        body = EX.plain_markdown(doc)
        for src in doc.files:
            self.assertIn(src.text.strip()[:40], body)


if __name__ == "__main__":
    unittest.main()
