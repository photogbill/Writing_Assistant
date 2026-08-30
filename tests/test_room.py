# SPDX-License-Identifier: Apache-2.0
"""The Room: isolation, the diff surface, and the drift score."""

from __future__ import annotations

import unittest

from _base import MANUAL
from writing_workshop import FICTION, Manuscript, NoModelError, TECHNICAL
from writing_workshop import fingerprint as FP
from writing_workshop import room as RM
from writing_workshop.ports import Host, ModelInfo


class FakeLLM:
    """Records every call, so isolation can be tested as an ABSENCE."""

    def __init__(self, reply: str = "Revised text.") -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, user, *, temperature=0.2, max_tokens=1024,
                 grammar="", cancel=None):
        self.calls.append((system, user))
        return self.reply

    def count_tokens(self, text):
        return None

    def info(self):
        return ModelInfo(name="fake", usable_tokens=8192, measured=True)


class Cast(unittest.TestCase):
    def test_the_adversary_differs_by_document_type(self):
        tech = RM.get(RM.ADVERSARY, TECHNICAL)
        fic = RM.get(RM.ADVERSARY, FICTION)
        self.assertIn("3am", tech.blurb)
        self.assertIn("train", fic.blurb)
        self.assertNotEqual(tech.system, fic.system)

    def test_every_persona_declares_what_its_output_is(self):
        for persona in RM.ALL:
            self.assertIsInstance(persona.returns_text, bool)

    def test_a_critic_cannot_be_asked_for_a_rewrite(self):
        """A persona that criticises returns notes and can never be
        'applied'. Getting this wrong is how a critique ends up pasted
        into a manuscript."""
        room = RM.Room(Host(llm=FakeLLM()))
        critic = RM.get(RM.CONTINUITY_READER)
        with self.assertRaises(ValueError) as caught:
            room.rewrite(critic, "Some text.")
        self.assertIn("notes, not text", str(caught.exception))


class Isolation(unittest.TestCase):
    def test_no_persona_sees_another(self):
        """Isolation is architectural, not a system prompt — the Athena
        lesson. Tested as an absence: nothing from call one appears in
        call two."""
        llm = FakeLLM()
        room = RM.Room(Host(llm=llm))
        room.rewrite(RM.get(RM.LINE_EDITOR), "First passage about bolts.")
        room.critique(RM.get(RM.ADVERSARY, TECHNICAL),
                      "Second passage about seals.")
        self.assertEqual(len(llm.calls), 2)
        self.assertNotIn("bolts", llm.calls[1][1])
        self.assertNotIn("Revised text.", llm.calls[1][1])
        self.assertNotEqual(llm.calls[0][0], llm.calls[1][0])

    def test_claims_only_reach_the_personas_that_asked_for_them(self):
        from writing_workshop import codex as CX
        llm = FakeLLM()
        room = RM.Room(Host(llm=llm))
        claims = [CX.make("torque", "value", "40 Nm")]
        room.rewrite(RM.get(RM.LINE_EDITOR), "Text.", claims=claims)
        room.rewrite(RM.get(RM.EXPANDER), "Text.", claims=claims)
        self.assertNotIn("Established facts", llm.calls[0][1])
        self.assertIn("Established facts", llm.calls[1][1])


class Output(unittest.TestCase):
    def test_a_fenced_reply_is_unwrapped(self):
        llm = FakeLLM("```\nThe revised sentence.\n```")
        room = RM.Room(Host(llm=llm))
        got = room.rewrite(RM.get(RM.LINE_EDITOR), "x")
        self.assertEqual(got.text, "The revised sentence.")

    def test_nothing_reports_clean(self):
        room = RM.Room(Host(llm=FakeLLM("NOTHING")))
        result = room.critique(RM.get(RM.ADVERSARY, TECHNICAL), "x")
        self.assertTrue(result.clean)

    def test_notes_are_split_into_lines(self):
        room = RM.Room(Host(llm=FakeLLM("- one thing\n- another thing")))
        result = room.critique(RM.get(RM.ADVERSARY, TECHNICAL), "x")
        self.assertEqual(result.notes, ["one thing", "another thing"])

    def test_no_model_raises_the_named_error(self):
        room = RM.Room(Host())
        with self.assertRaises(NoModelError):
            room.rewrite(RM.get(RM.LINE_EDITOR), "x")


class DriftIsAttached(unittest.TestCase):
    """A number beside the suggestion, not a dialog — and attached in the
    Room rather than in the panel, so a host cannot ship a suggestion
    without it by forgetting a call."""

    def setUp(self):
        doc = Manuscript.load(MANUAL)
        self.fp = FP.from_manuscript(doc)

    def test_a_suggestion_carries_its_score(self):
        llm = FakeLLM("Short. Very short. Tiny. Small. Brief. Terse. Blunt.")
        room = RM.Room(Host(llm=llm), self.fp)
        got = room.rewrite(RM.get(RM.LINE_EDITOR), "x")
        self.assertTrue(got.drifts)
        self.assertGreater(got.drift_score, 0)
        self.assertTrue(got.note)

    def test_without_a_baseline_it_says_nothing_rather_than_zero(self):
        room = RM.Room(Host(llm=FakeLLM()), None)
        got = room.rewrite(RM.get(RM.LINE_EDITOR), "x")
        self.assertEqual(got.drifts, [])
        self.assertEqual(got.note, "")


class NoGhostText(unittest.TestCase):
    def test_the_package_offers_no_autocomplete(self):
        """The highest-slop-risk feature in the category: it trains the
        author to accept the model's next word thousands of times a
        session, below the level where any of them is a decision.
        Everything here is opt-in per suggestion; ghost text is opt-out
        per keystroke.

        Checked against the package's NAMES rather than its source text —
        the module docstring says the words "autocomplete" and "ghost
        text" out loud, and a grep over prose would fail on the very
        sentence that promises the feature does not exist.
        """
        import writing_workshop
        seen = set()
        for module in (writing_workshop, RM, RM.personas):
            seen |= {name.lower() for name in dir(module)}
        for banned in ("autocomplete", "ghost", "complete_next",
                       "suggest_next", "inline_suggestion"):
            self.assertNotIn(banned, seen)
        for name in seen:
            self.assertNotIn("autocomplete", name)


if __name__ == "__main__":
    unittest.main()
