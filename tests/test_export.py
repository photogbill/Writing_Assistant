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


class ShunnGetsTheBookRight(unittest.TestCase):
    """2026-10-28."""

    def test_chapters_under_a_title_heading_are_exported(self):
        import tempfile
        from pathlib import Path
        from writing_workshop import Manuscript
        from writing_workshop import export as EX
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "01.md").write_text(
                "# The Long Road\n\n## Chapter One\n\nMira walked for a "
                "day and a night.\n\n## Chapter Two\n\nAleksandr waited "
                "by the bridge.\n", encoding="utf-8")
            spec = EX.shunn_spec(Manuscript.load(tmp))
        self.assertEqual(spec.title, "The Long Road")
        self.assertEqual([t for t, _p in spec.chapters],
                         ["Chapter One", "Chapter Two"])
        self.assertIn("Mira walked for a day and a night.",
                      spec.chapters[0][1])

    def test_prose_under_the_title_heading_is_not_dropped(self):
        """Found by the independent check: a prologue written straight
        under `# The Long Road` vanished from the export, unsaid."""
        import tempfile
        from pathlib import Path
        from writing_workshop import Manuscript
        from writing_workshop import export as EX
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "01.md").write_text(
                "# The Long Road\n\nBefore any of it, there was the road."
                "\n\n## Chapter One\n\nMira walked.\n\n## Chapter Two\n\n"
                "Aleksandr waited.\n", encoding="utf-8")
            spec = EX.shunn_spec(Manuscript.load(tmp))
        self.assertEqual(spec.chapters[0],
                         ("", ["Before any of it, there was the road."]))
        md = EX.shunn_markdown(spec)
        self.assertIn("Before any of it", md)
        self.assertNotIn("## \n", md)

    def test_word_count_rounds_the_way_shunn_says(self):
        from writing_workshop.export.shunn import ShunnSpec

        def rounded(n):
            return ShunnSpec(title="", word_count=n).rounded_words
        self.assertEqual(rounded(1486), 1500)   # Shunn's own example
        self.assertEqual(rounded(1507), 1500)
        self.assertEqual(rounded(1250), 1300)   # half rounds up
        self.assertEqual(rounded(18240), 18000)  # novella: nearest 500
        self.assertEqual(rounded(40), 40)        # never "about 0 words"


if __name__ == "__main__":
    unittest.main()
