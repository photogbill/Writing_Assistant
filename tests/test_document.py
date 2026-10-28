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


class ReadHonestly(TempProject):
    """2026-10-28. Four Windows encodings that used to read wrongly AND
    silently, and the host sidecar that used to be read as a chapter."""

    source = NOVEL

    def _one(self, name: str, raw: bytes):
        for old in self.root.glob("*.md"):
            old.unlink()
        (self.root / name).write_bytes(raw)
        return Manuscript.load(self.root)

    def test_a_bom_does_not_stop_the_first_line_being_a_heading(self):
        doc = self._one("01.md", b"\xef\xbb\xbf# Chapter One\n\nMira ran.\n")
        self.assertEqual([s.title for s in doc.sections], ["Chapter One"])
        self.assertEqual(doc.files[0].encoding, "utf-8-sig")

    def test_utf16_is_read_as_text_not_one_letter_per_word(self):
        raw = "# Chapter One\n\nMira ran home.\n".encode("utf-16")
        doc = self._one("01.md", raw)
        self.assertEqual(doc.sections[0].title, "Chapter One")
        self.assertIn("Mira ran home.", doc.files[0].text)

    def test_utf16_keeps_its_byte_order_and_line_endings(self):
        """Found by the independent check: CRLF in UTF-16 is \\r\\x00\\n\\x00,
        so counting b"\\r\\n" never found it, and both byte orders were
        "utf-16", which writes little-endian."""
        from writing_workshop.document import decode, newline_of
        le = "# One\r\n\r\nHi.\r\n".encode("utf-16-le")
        be = "# One\r\n\r\nHi.\r\n".encode("utf-16-be")
        for bom, raw, name in ((b"\xff\xfe", le, "utf-16-le"),
                               (b"\xfe\xff", be, "utf-16-be")):
            text, encoding, _note = decode(bom + raw)
            self.assertEqual(encoding, name)
            self.assertEqual(newline_of(text), "\r\n")
            self.assertEqual(newline_of(bom + raw), "\r\n")
            doc = self._one("01.md", bom + raw)
            self.assertEqual(doc.files[0].newline, "\r\n")
        self.assertEqual(newline_of("a\rb\rc"), "\r")

    def test_one_stray_windows_byte_costs_one_character_not_the_file(self):
        raw = ("# One\n\n\u201cDon\u2019t,\u201d she said. "
               "Caf\u00e9.\n").encode("utf-8") + b"\x92\n"
        doc = self._one("01.md", raw)
        self.assertIn("\u201cDon\u2019t,\u201d", doc.files[0].text)
        self.assertTrue(any("not valid UTF-8" in n for n in doc.notes()))

    def test_a_real_cp1252_file_is_read_and_named(self):
        raw = "# One\n\n\u201cDon\u2019t,\u201d she said.\n".encode("cp1252")
        doc = self._one("01.md", raw)
        self.assertIn("\u201cDon\u2019t,\u201d", doc.files[0].text)
        self.assertEqual(doc.files[0].encoding, "cp1252")
        self.assertTrue(any("Windows-1252" in n for n in doc.notes()))

    def test_line_endings_are_recorded_and_offsets_use_newlines(self):
        doc = self._one("01.md", b"# One\r\n\r\nMira ran.\r\n")
        self.assertEqual(doc.files[0].newline, "\r\n")
        self.assertNotIn("\r", doc.files[0].text)

    def test_a_thinking_sidecar_is_not_a_chapter(self):
        (self.root / "01-chapter.thinking.md").write_text(
            "# Thinking — Chapter 1\n\nThe sword is steel here.\n",
            encoding="utf-8")
        doc = Manuscript.load(self.root)
        self.assertNotIn("01-chapter.thinking.md",
                         [f.rel for f in doc.files])
        self.assertFalse(any(s.title.startswith("Thinking")
                             for s in doc.sections))
        self.assertTrue(any("sidecar" in n for n in doc.notes()))


class NoPhantomsAndPlainTextChapters(unittest.TestCase):
    """2026-10-28: YAML front matter made a 0-word chapter per file named
    after the file, and a .txt novel with CHAPTER lines was one section."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_front_matter_is_not_a_chapter(self):
        (self.root / "01.md").write_text(
            "---\ntitle: One\ndraft: 3\n---\n\n# Arrival\n\nShe came.\n",
            encoding="utf-8")
        doc = Manuscript.load(self.root)
        self.assertEqual([s.title for s in doc.sections], ["Arrival"])

    def test_a_file_with_no_heading_is_still_one_section(self):
        (self.root / "parts.md").write_text("| a | b |\n|---|---|\n| 1 | 2 |\n",
                                            encoding="utf-8")
        self.assertEqual(len(Manuscript.load(self.root).sections), 1)

    def test_chapter_lines_in_a_txt_file_are_chapters(self):
        body = "Chapter one was the hardest to write, she said.\n\n"
        for name in ("CHAPTER 1", "Chapter Two: The Road", "PART III",
                     "Epilogue"):
            body += f"{name}\n\nRain fell on the town, and on the river.\n\n"
        (self.root / "book.txt").write_text(body, encoding="utf-8")
        doc = Manuscript.load(self.root)
        titles = [s.title for s in doc.sections]
        self.assertEqual(titles, ["book", "CHAPTER 1", "Chapter Two: The Road",
                                  "PART III", "Epilogue"])
        # the heading line is not prose: it is not counted as words
        self.assertEqual(doc.sections[1].words, 9)
        self.assertNotIn("CHAPTER", doc.prose_of_file("book.txt"))

    def test_a_markdown_file_is_not_second_guessed(self):
        (self.root / "a.md").write_text("# One\n\nCHAPTER 1\n\nText.\n",
                                        encoding="utf-8")
        self.assertEqual(len(Manuscript.load(self.root).sections), 1)

    def test_too_few_chapters_says_why_rather_than_going_quiet(self):
        from writing_workshop.craft import run
        (self.root / "book.txt").write_text(
            "Rain fell on the town, and on the river. " * 20,
            encoding="utf-8")
        report = run(Manuscript.load(self.root), "fiction",
                     only=["pacing", "presence"], cast=["Mira"])
        self.assertIn("CHAPTER 7", report.quiet["pacing"])
        self.assertIn("pacing", report.ran)
        self.assertIn("presence", report.quiet)


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
