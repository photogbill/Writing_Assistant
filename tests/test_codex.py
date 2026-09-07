# SPDX-License-Identifier: Apache-2.0
"""Claims, provenance, supersession, and Reconsider."""

from __future__ import annotations

import unittest

from _base import MANUAL, NOVEL, TempProject
from pathlib import Path

from writing_workshop import (ACCEPTED, Manuscript, NUMERIC, PROPOSED,
                              Project, REJECTED, SUPERSEDED)

ROOT = Path(__file__).resolve().parents[1]
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


class TheAuthorsOwnHand(TempProject):
    """Three verbs, because the three things an author might mean when
    they say "this claim is wrong" are genuinely different.

    Bill, 2026-09-06: *"everything should be editable, both the inputs and
    the outputs."* A ledger is the case where taking that literally would
    destroy the thing being edited — so the edit is offered and the record
    of what happened is kept, which is the whole point of a ledger.
    """

    def setUp(self):
        super().setUp()
        self.project = Project.open(self.root)
        self.codex = CX.Codex(self.project.codex_db,
                              clock=FixedClock("2026-09-06 12:00:00"))

    def tearDown(self):
        self.codex.close()
        super().tearDown()

    # -- author -----------------------------------------------------------

    def test_an_authored_claim_is_the_authors_and_says_so(self):
        claim = self.codex.author(CX.make("Mara", "material", "bronze"))
        self.assertEqual(claim.origin, "author")
        self.assertEqual(claim.state, PROPOSED)

    def test_accepting_as_you_write_is_still_two_acts_in_the_journal(self):
        """The rule that no constructor can make an accepted claim is not
        a formality to be routed around by the one path that finds it
        inconvenient. It is what makes `accepted` mean an act somebody
        took, and the journal has to show the act."""
        claim = self.codex.author(CX.make("Mara", "material", "bronze"),
                                  accept=True)
        self.assertEqual(claim.state, ACCEPTED)
        self.assertEqual([a for a, _at, _d in self.codex.history(claim.id)],
                         ["proposed", "accepted"])

    def test_an_authored_claim_reaches_the_places_accepted_claims_reach(self):
        claim = self.codex.author(
            CX.make("Mara", "material", "bronze"), accept=True)
        self.assertIn(claim.id,
                      [c.id for c in self.codex.all(state=ACCEPTED)])

    # -- revise -----------------------------------------------------------

    def test_a_proposed_claim_can_be_fixed_in_place(self):
        """Nothing can depend on a proposed claim: it is never mirrored,
        never returned by `governing`, and nothing links to it."""
        claim = self.codex.add(CX.make("Sword", "material", "bronz"))
        fixed = self.codex.revise(claim.id, value="bronze",
                                  subject="Sword of Ys")
        self.assertEqual(fixed.id, claim.id)
        self.assertEqual(self.codex.get(claim.id).value, "bronze")
        self.assertEqual(self.codex.get(claim.id).subject, "Sword of Ys")

    def test_revising_rebuilds_the_parsed_number(self):
        """The value carries a number and a unit that were PARSED out of
        it. A revision that wrote the text and kept the old figure would
        leave every numeric check comparing 40 against a claim that reads
        45 for ever — which is the bug this rebuild exists to prevent."""
        claim = self.codex.add(CX.make("torque", "value", "40 Nm",
                                       kind=NUMERIC))
        self.assertEqual(claim.number, 40.0)
        fixed = self.codex.revise(claim.id, value="45 Nm")
        self.assertEqual(fixed.number, 45.0)
        self.assertEqual(self.codex.get(claim.id).number, 45.0)

    def test_revising_rebuilds_the_conflict_key(self):
        claim = self.codex.add(CX.make("Sword", "material", "bronze"))
        fixed = self.codex.revise(claim.id, subject="Dagger")
        self.assertEqual(fixed.key, "dagger|material")
        self.assertEqual([c.id for c in self.codex.by_key("dagger|material")],
                         [claim.id])
        self.assertEqual(self.codex.by_key("sword|material"), [])

    def test_a_revision_is_journalled_with_what_it_was(self):
        claim = self.codex.add(CX.make("Sword", "material", "bronz"))
        self.codex.revise(claim.id, value="bronze")
        actions = [a for a, _at, _d in self.codex.history(claim.id)]
        self.assertIn("revised", actions)
        detail = [d for a, _at, d in self.codex.history(claim.id)
                  if a == "revised"][0]
        self.assertIn("bronz", detail)

    def test_an_accepted_claim_cannot_be_edited_in_place(self):
        claim = self.codex.add(CX.make("Sword", "material", "bronze"))
        self.codex.accept(claim.id)
        with self.assertRaises(ValueError) as caught:
            self.codex.revise(claim.id, value="steel")
        self.assertIn("corrected, not", str(caught.exception))

    # -- correct ----------------------------------------------------------

    def test_a_correction_rejects_the_wrong_claim_and_links_the_right_one(self):
        wrong = self.codex.add(CX.make("Sword", "material", "bronze"))
        self.codex.accept(wrong.id)
        right = self.codex.correct(wrong.id,
                                   CX.make("Sword", "colour", "bronze"))
        old = self.codex.get(wrong.id)
        self.assertEqual(old.state, REJECTED)
        self.assertEqual(old.replaced_by, right.id)
        self.assertEqual(right.state, ACCEPTED)

    def test_a_correction_is_not_a_supersession(self):
        """THE DISTINCTION THIS VERB EXISTS FOR. `supersede` says the world
        moved and both values were true in their turn, which is what lets
        `reconsider` find the four passages still saying bronze. A
        correction says the claim never should have said that — recording
        it as a supersession would send `reconsider` hunting the
        manuscript for a value the manuscript never contained.
        """
        wrong = self.codex.add(CX.make("Sword", "material", "brnze"))
        self.codex.accept(wrong.id)
        self.codex.correct(wrong.id, CX.make("Sword", "material", "bronze"))
        old = self.codex.get(wrong.id)
        self.assertNotEqual(old.state, SUPERSEDED)
        self.assertEqual(old.superseded_by, 0)
        self.assertEqual(self.codex.all(state=SUPERSEDED), [])

    def test_a_correction_inherits_the_evidence_it_did_not_change(self):
        """A correction changes the READING of a passage, never the
        passage. An author who could retype a quote could change what the
        document is recorded as saying, which is the one edit this store
        must not offer."""
        wrong = CX.make("Sword", "material", "bronze",
                        source_ref="ch 3 · para 2", section_id="s1",
                        quote="the bronze sword lay there")
        wrong = self.codex.add(wrong)
        self.codex.accept(wrong.id)
        right = self.codex.correct(wrong.id,
                                   CX.make("Sword", "colour", "bronze"))
        self.assertEqual(right.quote, "the bronze sword lay there")
        self.assertEqual(right.source_ref, "ch 3 · para 2")
        self.assertEqual(right.section_id, "s1")

    def test_a_correction_says_what_it_replaced(self):
        wrong = self.codex.add(CX.make("Sword", "material", "bronze"))
        self.codex.accept(wrong.id)
        self.codex.correct(wrong.id, CX.make("Dagger", "material", "bronze"))
        detail = [d for a, _at, d in self.codex.history(wrong.id)
                  if a == "corrected"][0]
        self.assertIn("Sword", detail)
        self.assertIn("bronze", detail)

    def test_correcting_a_proposed_claim_leaves_it_proposed(self):
        """Nothing has been agreed to yet, so nothing is asserted by
        fixing it."""
        wrong = self.codex.add(CX.make("Sword", "material", "bronze"))
        right = self.codex.correct(wrong.id,
                                   CX.make("Sword", "colour", "bronze"))
        self.assertEqual(right.state, PROPOSED)
        self.assertEqual(self.codex.get(wrong.id).state, REJECTED)

    def test_nothing_is_ever_deleted(self):
        wrong = self.codex.add(CX.make("Sword", "material", "bronze"))
        self.codex.accept(wrong.id)
        self.codex.correct(wrong.id, CX.make("Sword", "colour", "bronze"))
        self.assertEqual(len(self.codex.all()), 2)


class AnOlderCodexStillOpens(TempProject):
    """`CREATE TABLE IF NOT EXISTS` does nothing to a table that already
    exists, so a schema that grows needs a migration or every Codex written
    before today raises `no such column` on the first read — a failure that
    looks like a corrupt project folder and is not.
    """

    #: The schema exactly as it shipped, without `replaced_by`.
    OLD = """
    CREATE TABLE claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL,
        kind TEXT NOT NULL, predicate TEXT NOT NULL, value TEXT NOT NULL,
        unit TEXT DEFAULT '', number REAL, source_ref TEXT DEFAULT '',
        section_id TEXT DEFAULT '', path TEXT DEFAULT '',
        span_start INTEGER DEFAULT 0, span_end INTEGER DEFAULT 0,
        quote TEXT DEFAULT '', state TEXT NOT NULL DEFAULT 'proposed',
        origin TEXT DEFAULT 'author', superseded_by INTEGER DEFAULT 0,
        note TEXT DEFAULT '', key TEXT DEFAULT '', created TEXT DEFAULT '');
    CREATE TABLE journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL,
        action TEXT NOT NULL, at TEXT DEFAULT '', detail TEXT DEFAULT '');
    INSERT INTO claims (subject,kind,predicate,value,state,key)
    VALUES ('Sword','attribute','material','bronze','accepted',
            'sword|material');
    """

    def _old_db(self):
        import sqlite3
        path = self.root / "old-codex.db"
        db = sqlite3.connect(str(path))
        db.executescript(self.OLD)
        db.commit()
        db.close()
        return path

    def test_it_opens_and_reads(self):
        store = CX.Codex(self._old_db())
        try:
            claim = store.all()[0]
            self.assertEqual(claim.value, "bronze")
            self.assertEqual(claim.replaced_by, 0)
        finally:
            store.close()

    def test_and_the_new_verb_works_on_it(self):
        store = CX.Codex(self._old_db())
        try:
            old = store.all()[0]
            right = store.correct(old.id, CX.make("Sword", "colour",
                                                  "bronze"))
            self.assertEqual(store.get(old.id).replaced_by, right.id)
        finally:
            store.close()

    def test_the_migration_is_additive_only(self):
        """A migration that can lose an author's Codex is worse than a
        feature that has to wait.

        On the SQL it EXECUTES, not on the source text: the first version
        of this test read the whole function including its docstring and
        failed on the word "dropped" in the sentence promising nothing is
        dropped. A guard that fires on its own documentation teaches
        people to weaken the guard.
        """
        import ast
        import re
        source = (ROOT / "writing_workshop" / "codex" / "store.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        migrate = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef)
                       and n.name == "_migrate")
        statements = []
        for node in ast.walk(migrate):
            #: Only the strings handed to `execute`, and only those — the
            #: docstring is a string in this function too.
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute"):
                continue
            for arg in node.args:
                statements.append(ast.unparse(arg).upper())
        self.assertTrue(statements, "the migration executes no SQL at all")
        for sql in statements:
            for forbidden in ("DROP", "DELETE", "RENAME", "UPDATE",
                              "INSERT"):
                self.assertIsNone(
                    re.search(rf"\b{forbidden}\b", sql),
                    f"the migration runs {forbidden}: {sql}")
            self.assertTrue(
                sql.startswith("'PRAGMA") or sql.startswith('"PRAGMA')
                or "ADD COLUMN" in sql or sql.startswith("F'ALTER")
                or sql.startswith('F"ALTER'),
                f"unexpected migration statement: {sql}")


if __name__ == "__main__":
    unittest.main()
