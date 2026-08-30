# SPDX-License-Identifier: Apache-2.0
"""Read-aloud, and the rule about a character's established voice."""

from __future__ import annotations

import unittest

from _base import NOVEL
from writing_workshop import Manuscript
from writing_workshop import readaloud as RA
from writing_workshop.ports import Host, Voice


class Speakable(unittest.TestCase):
    def setUp(self):
        self.doc = Manuscript.load(NOVEL)
        self.chapter = self.doc.chapters()[0]

    def test_never_splits_mid_sentence(self):
        """A synthesiser handed half a sentence produces a reading with
        the wrong intonation, and the author hears a problem in their
        prose that is really a problem in the split."""
        for line in RA.passages(self.doc, self.chapter, max_chars=80):
            self.assertTrue(line.text.rstrip()[-1] in '.!?"”’')

    def test_a_long_section_is_broken_up(self):
        few = RA.passages(self.doc, self.chapter, max_chars=2000)
        many = RA.passages(self.doc, self.chapter, max_chars=100)
        self.assertGreater(len(many), len(few))

    def test_dialogue_is_attributed_where_the_text_says_so(self):
        lines = RA.passages(self.doc, self.chapter, max_chars=120,
                            cast=["Mira", "Aleksandr"])
        self.assertTrue(any(line.is_dialogue for line in lines))


class EstablishedVoices(unittest.TestCase):
    """The rule this module will not bend.

    A speaking character is read in the voice ATK has ESTABLISHED for
    them. A character with no established voice type is NAMED, not
    guessed at — assigning one by guess is how a character acquires a
    voice type nobody chose, in a tool whose whole argument is that it
    does not put words in the author's mouth.
    """

    def setUp(self):
        self.lines = [RA.Line("Narration here.", None),
                      RA.Line('"Hello," said Mira.', None, speaker="Mira"),
                      RA.Line('"Hello," said Kestrel.', None,
                              speaker="Kestrel")]

    def test_a_known_character_gets_their_voice(self):
        lines, missing = RA.assign_voices(
            self.lines, narrator="en_GB-narrator",
            character_voices={"Mira": "en_GB-alba"})
        self.assertEqual(lines[1].voice, "en_GB-alba")
        self.assertEqual(missing, ["Kestrel"])

    def test_an_unknown_character_falls_back_and_is_reported(self):
        lines, missing = RA.assign_voices(self.lines,
                                          narrator="en_GB-narrator")
        self.assertEqual(lines[2].voice, "en_GB-narrator")
        self.assertEqual(missing, ["Mira", "Kestrel"])

    def test_narration_is_never_reported_as_missing(self):
        _lines, missing = RA.assign_voices(self.lines[:1])
        self.assertEqual(missing, [])

    def test_a_voice_carries_its_language(self):
        """A Piper voice speaks ONE language. An English voice handed a
        translated passage produces fluent nonsense an operator who does
        not speak the language cannot hear."""
        lines, _missing = RA.assign_voices(
            self.lines, narrator="en_US-lessac-medium",
            voice_languages={"en_US-lessac-medium": "en"})
        self.assertEqual(lines[0].language, "en")


class Jobs(unittest.TestCase):
    def test_one_job_per_chapter_with_a_named_output(self):
        doc = Manuscript.load(NOVEL)
        jobs, missing = RA.chapter_jobs(doc, "/tmp/audio",
                                        narrator="en_GB-narrator")
        self.assertEqual(len(jobs), len(doc.chapters()))
        self.assertTrue(jobs[0].out_path.endswith(".wav"))
        self.assertGreater(jobs[0].chars, 0)
        self.assertIsInstance(missing, list)

    def test_no_speech_engine_is_a_state_not_an_error(self):
        line = RA.Line("Say this.", None)
        self.assertEqual(RA.speak(Host(), line), "")

    def test_speak_uses_the_hosts_engine(self):
        said = []

        class Speech:
            def available(self):
                return True

            def voices(self):
                return [Voice("en_GB-alba", "en")]

            def speak(self, text, *, voice="", out_path=""):
                said.append((text, voice))
                return "/tmp/out.wav"
        host = Host(speech=Speech())
        line = RA.Line("Say this.", None, voice="en_GB-alba")
        self.assertEqual(RA.speak(host, line), "/tmp/out.wav")
        self.assertEqual(said, [("Say this.", "en_GB-alba")])


if __name__ == "__main__":
    unittest.main()
