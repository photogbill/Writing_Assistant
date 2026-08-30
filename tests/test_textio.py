# SPDX-License-Identifier: Apache-2.0
"""The text spine. Every measurement in the package rests on this."""

from __future__ import annotations

import unittest

from _base import *                                  # noqa: F401,F403
from writing_workshop import textio as T


class SentenceSplitting(unittest.TestCase):
    def split(self, text: str) -> list[str]:
        return [text[s:e] for s, e in T.sentences(text)]

    def test_plain(self):
        self.assertEqual(self.split("One. Two! Three?"),
                         ["One.", "Two!", "Three?"])

    def test_decimal_is_not_a_stop(self):
        self.assertEqual(self.split("Tighten to 4.2 mm exactly. Then stop."),
                         ["Tighten to 4.2 mm exactly.", "Then stop."])

    def test_label_abbreviation_followed_by_a_digit(self):
        self.assertEqual(self.split("See Fig. 7 for the layout."),
                         ["See Fig. 7 for the layout."])

    def test_label_abbreviation_that_really_does_end_a_sentence(self):
        """The trap a flat abbreviation list creates.

        `no`, `min`, `max`, `in`, `para` are all abbreviations AND ordinary
        words. Listing them flatly makes the splitter silently under-split
        and every length distribution shifts with nothing to show for it.
        """
        self.assertEqual(self.split("It works in principle. No. It does not."),
                         ["It works in principle.", "No.", "It does not."])
        self.assertEqual(self.split("Read the para. Then sign it."),
                         ["Read the para.", "Then sign it."])

    def test_title_abbreviation_never_ends(self):
        self.assertEqual(self.split("Ask Dr. Rowe about it."),
                         ["Ask Dr. Rowe about it."])

    def test_initials(self):
        self.assertEqual(
            self.split("Tighten to 40 Nm. J. R. R. Tolkien wrote it."),
            ["Tighten to 40 Nm.", "J. R. R. Tolkien wrote it."])

    def test_quote_then_new_sentence(self):
        self.assertEqual(self.split('"Go." Then she left.'),
                         ['"Go."', "Then she left."])

    def test_blank_line_always_ends_a_sentence(self):
        self.assertEqual(self.split("One two\n\nthree four"),
                         ["One two", "three four"])

    def test_eg_does_not_split(self):
        self.assertEqual(self.split("Use a wrench, e.g. this one. Not that."),
                         ["Use a wrench, e.g. this one.", "Not that."])


class Blocks(unittest.TestCase):
    MD = ("---\ntitle: t\n---\n\n# H1\n\npara one\n\n"
          "1. step one\n2. step two\n\n| a | b |\n|---|---|\n\n"
          "```py\nx = 1  # not prose. Really.\n```\n\n> quoted\n")

    def test_kinds(self):
        kinds = [b.kind for b in T.scan_blocks(self.MD)]
        self.assertEqual(kinds, [T.FRONT, T.HEADING, T.PARA, T.ORDERED,
                                 T.ORDERED, T.TABLE, T.CODE, T.QUOTE])

    def test_ordered_numbers_come_from_the_source(self):
        nums = [b.number for b in T.scan_blocks(self.MD)
                if b.kind == T.ORDERED]
        self.assertEqual(nums, [1, 2])

    def test_unrecognised_line_is_a_paragraph_not_nothing(self):
        """`line.startswith('## ')` produced ZERO sections and an empty
        document, silently, for a model that wrote `##Intro`. A scanner
        that can return nothing is the bug; a paragraph is always safe."""
        blocks = T.scan_blocks("##Intro\nbody text here")
        self.assertTrue(blocks)
        self.assertEqual(blocks[0].kind, T.PARA)


class Masking(unittest.TestCase):
    def test_offsets_survive(self):
        """Masking, not stripping. A finding that cannot be pointed at in
        the file the author is editing is a finding they cannot act on."""
        text = "Intro para.\n\n```\ncode. here.\n```\n\nAfter the fence."
        prose = T.prose_of(text)
        self.assertEqual(len(prose), len(text))
        found = [prose[s:e] for s, e in T.sentences(prose)]
        self.assertEqual(found, ["Intro para.", "After the fence."])
        start = prose.index("After")
        self.assertEqual(text[start:start + 5], "After")

    def test_tables_are_not_prose(self):
        text = "Prose here.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
        self.assertNotIn("|", T.prose_of(text))

    def test_list_text_survives_the_marker_going(self):
        text = "- tighten the bolt to 40 Nm\n"
        prose = T.prose_of(text)
        self.assertIn("tighten the bolt", prose)
        self.assertTrue(prose.startswith("  "))

    def test_link_label_kept_url_dropped(self):
        text = "See [the manual](https://example.com/a) for more."
        prose = T.prose_of(text)
        self.assertIn("the manual", prose)
        self.assertNotIn("example.com", prose)
        self.assertEqual(len(prose), len(text))


class Words(unittest.TestCase):
    def test_term_key_clusters_the_right_things(self):
        for a, b in (("Wi-Fi", "WiFi"), ("e-mail", "email"),
                     ("power supply", "power supplies")):
            self.assertEqual(T.term_key(a), T.term_key(b), f"{a} vs {b}")

    def test_term_key_does_not_over_cluster(self):
        self.assertNotEqual(T.term_key("power supply"),
                            T.term_key("power supply unit"))

    def test_syllables(self):
        for word, want in (("the", 1), ("simple", 2), ("little", 2),
                           ("table", 2), ("walked", 1), ("needed", 2),
                           ("calibrated", 4), ("idea", 2), ("queue", 1)):
            self.assertEqual(T.syllables(word), want, word)


if __name__ == "__main__":
    unittest.main()
