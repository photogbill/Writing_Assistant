# SPDX-License-Identifier: Apache-2.0
"""Claims, provenance, supersession, and Reconsider."""

from __future__ import annotations

import unittest

from _base import MANUAL, NOVEL, TempProject
from writing_workshop import (ACCEPTED, Manuscript, NUMERIC, PROPOSED,
                              Project, SUPERSEDED)
from writing_workshop import codex as CX
from writing_workshop.ports import FixedClock


class DeterministicExtraction(unittest.TestCase):
    def setUp(self):
        self.doc = Manuscript.load(MANUAL)

    def test_named_quantities_become_numeric_claims(self):
        claims = CX.deterministic(self.doc)
        torque = [c for c in claims if c.subject == "torque"]
        self.assertEqual(len(torque), 2)
        self.assertTrue(all(c.kind == NUMERIC for c in torque))
        self.assertEqual({c.value for c in torque}, {"40 Nm", "45 Nm"})

    def test_a_number_with_no_quantity_word_is_skipped(self):
        """Inventing the subject is how a continuity report fills with
        conflicts that are really parser noise."""
        subjects = {c.subject for c in CX.deterministic(self.doc)}
        self.assertNotIn("", subjects)
        self.assertTrue(subjects <= {"torque", "voltage"})

    def test_source_ref_uses_the_authors_own_numbering(self):
        claim = CX.deterministic(self.doc)[0]
        self.assertIn("§", claim.source_ref)
        self.assertIn("para", claim.source_ref)

    def test_everything_arrives_proposed(self):
        for claim in CX.deterministic(self.doc):
            self.assertEqual(claim.state, PROPOSED)

    def test_material_claims_are_narrow_on_purpose(self):
        """Run over every adjective, "the old sword" conflicts with "the
        bronze sword" and the Codex fills with candidates to dismiss."""
        doc = Manuscript.load(NOVEL)
        claims = CX.attribute_claims(doc, ["sword"])
        values = {c.value for c in claims if c.predicate == "material"}
        self.assertEqual(values, {"bronze", "steel"})


class Store(TempProject):
    def setUp(self):
        super().setUp()
        self.project = Project.open(self.root)
        self.doc = self.project.manuscript()
        self.codex = CX.Codex(self.project.codex_db,
                              clock=FixedClock("2026-08-29 12:00:00"))

    def tearDown(self):
        self.codex.close()
        super().tearDown()

    def test_re_running_extraction_does_not_multiply_the_codex(self):
        first = self.codex.add_many(CX.deterministic(self.doc))
        again = self.codex.add_many(CX.deterministic(self.doc))
        self.assertEqual(len(self.codex.all()), len(first))
        self.assertEqual([c.id for c in first], [c.id for c in again])

    def test_supersede_keeps_the_old_claim(self):
        """Deleting it is the obvious implementation and it destroys
        Reconsider: knowing the sword USED to be bronze is the entire
        basis for finding the four passages that still say so."""
        claims = self.codex.add_many(CX.deterministic(self.doc))
        old = [c for c in claims if c.value == "40 Nm"][0]
        self.codex.accept(old.id)
        new = self.codex.supersede(old.id, CX.make("torque", "value",
                                                   "50 Nm"))
        self.assertEqual(self.codex.get(old.id).state, SUPERSEDED)
        self.assertEqual(self.codex.get(old.id).superseded_by, new.id)
        self.assertEqual(self.codex.get(new.id).state, ACCEPTED)

    def test_the_journal_records_who_decided_what(self):
        claim = self.codex.add(CX.make("housing", "material", "aluminium"))
        self.codex.accept(claim.id, "checked against the drawing")
        actions = [row[0] for row in self.codex.history(claim.id)]
        self.assertEqual(actions, ["proposed", "accepted"])
        self.assertEqual(self.codex.history(claim.id)[0][1],
                         "2026-08-29 12:00:00")

    def test_only_accepted_claims_are_mirrored(self):
        """A ledger that receives a model's proposals is a ledger whose
        provenance means nothing."""
        sent = []

        class Ledger:
            def available(self):
                return True

            def observe(self, text, *, origin="", source_ref=""):
                sent.append(text)
                return ""
        self.codex.add_many(CX.deterministic(self.doc))
        accepted = self.codex.all()[0]
        self.codex.accept(accepted.id)
        self.assertEqual(self.codex.mirror(Ledger()), 1)
        self.assertEqual(len(sent), 1)

    def test_governing_claims_prefer_this_section(self):
        a = self.codex.add(CX.make("torque", "value", "40 Nm",
                                   section_id="02-service.md#0"))
        b = self.codex.add(CX.make("finish", "colour", "grey"))
        for claim in (a, b):
            self.codex.accept(claim.id)
        ranked = self.codex.governing("02-service.md#0")
        self.assertEqual(ranked[0].subject, "torque")


class Reconsider(unittest.TestCase):
    def setUp(self):
        self.doc = Manuscript.load(NOVEL)

    def test_it_finds_the_passages_that_still_say_the_old_thing(self):
        found = CX.find(self.doc, "sword", "bronze")
        self.assertTrue(found)
        self.assertTrue(found[0].certain)
        self.assertIn("bronze", found[0].quote)

    def test_weaker_matches_come_after_stronger_ones(self):
        found = CX.find(self.doc, "sword", "bronze")
        strengths = [d.strength for d in found]
        self.assertEqual(strengths, sorted(strengths, reverse=True))

    def test_every_dependent_says_why_it_is_listed(self):
        for dep in CX.find(self.doc, "sword", "bronze"):
            self.assertTrue(dep.why)
            self.assertIn("sword", dep.why)

    def test_numeric_values_are_matched_after_conversion(self):
        """The passage a reader would find contradictory is exactly the
        one a substring search misses."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.md").write_text(
                "# T\n\nThe torque is 40 Nm.\n\nSet the torque to "
                "29.5 lb-ft.\n", encoding="utf-8")
            doc = Manuscript.load(tmp)
            found = CX.find(doc, "torque", "40 Nm")
            self.assertTrue(any(d.certain and "29.5" in d.quote
                                for d in found))


class ModelProposals(unittest.TestCase):
    """Extraction proposes, never asserts — and a claim whose quote is not
    in the section is DISCARDED, not repaired. That single rule is what
    stops a model's paraphrase entering the Codex with a source reference
    that looks authoritative and points at nothing."""

    def setUp(self):
        self.doc = Manuscript.load(MANUAL)
        self.section = self.doc.sections[2]

    def test_a_real_quote_is_kept(self):
        raw = ('[{"subject":"torque","kind":"numeric","predicate":"value",'
               '"value":"40 Nm","quote":"The torque for the lid\\nbolts is '
               '40 Nm."}]')
        claims = CX.parse(raw, self.doc, self.section)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].state, "proposed")
        self.assertEqual(claims[0].origin, "extracted")

    def test_an_invented_quote_is_discarded(self):
        raw = ('[{"subject":"torque","kind":"numeric","predicate":"value",'
               '"value":"90 Nm","quote":"The torque is ninety newton'
               ' metres."}]')
        self.assertEqual(CX.parse(raw, self.doc, self.section), [])

    def test_junk_around_the_json_is_survivable(self):
        raw = ('Sure! Here you go:\n[{"subject":"torque","kind":"numeric",'
               '"predicate":"value","value":"40 Nm","quote":"The torque for'
               ' the lid\\nbolts is 40 Nm."}]\nHope that helps.')
        self.assertEqual(len(CX.parse(raw, self.doc, self.section)), 1)

    def test_unparseable_output_is_empty_not_an_exception(self):
        self.assertEqual(CX.parse("I could not do that", self.doc,
                                  self.section), [])

    def test_the_grammar_names_only_the_four_kinds(self):
        for kind in ("attribute", "relationship", "temporal", "numeric"):
            # GBNF escapes its own quotes, so the literal in
            # the grammar is \"attribute\" rather than "attribute".
            self.assertIn(f'\\"{kind}\\"', CX.CLAIMS_GBNF)

    def test_propose_without_a_model_raises_the_named_error(self):
        from writing_workshop.errors import NoModelError
        from writing_workshop.ports import Host
        with self.assertRaises(NoModelError):
            CX.propose(Host(), self.doc, self.section)


if __name__ == "__main__":
    unittest.main()
