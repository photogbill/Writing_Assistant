# SPDX-License-Identifier: Apache-2.0
"""The capabilities added on 2026-09-05, and the properties they promise.

Grouped by the promise rather than by the module, because that is what a
later reader needs to know is still true.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest
import zipfile

from _base import *  # noqa: F401,F403

from writing_workshop import cast as CAST
from writing_workshop import codex as CX
from writing_workshop import continuity as CN
from writing_workshop import doctypes as DT
from writing_workshop import drift as DR
from writing_workshop import fingerprint as FP
from writing_workshop import rules as R
from writing_workshop.craft import ANY_LANGUAGE, registry
from writing_workshop.craft import run as run_craft
from writing_workshop.document import Manuscript
from writing_workshop.influence import Influences
from writing_workshop.project import Project
from writing_workshop.state import Store
from writing_workshop.types import FICTION, LYRICS, TECHNICAL
from writing_workshop.versions import Versions

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# ---------------------------------------------------------------------------
# the registry can never be observed empty
# ---------------------------------------------------------------------------


class RegistryIsAlwaysLoaded(unittest.TestCase):
    """ATK builds its per-check dropdown from this the moment a project
    opens, which is before any craft pass has run. It used to get an
    empty dict, so the filter offered nothing but "every check" and
    nothing failed."""

    def test_checks_for_populates_the_registry_itself(self):
        from writing_workshop.craft import checks_for
        self.assertTrue(checks_for(TECHNICAL))

    def test_the_registry_accessor_populates_it_too(self):
        self.assertTrue(registry())

    def test_every_check_declares_the_languages_it_is_valid_for(self):
        for name, reg in registry().items():
            with self.subTest(check=name):
                self.assertTrue(reg.languages, f"{name} declares none")


# ---------------------------------------------------------------------------
# language
# ---------------------------------------------------------------------------


class LanguageIsDeclaredNotAssumed(TempProject):      # noqa: F405
    def test_english_only_checks_are_skipped_with_a_reason(self):
        doc = Manuscript.load(self.root)
        report = run_craft(doc, TECHNICAL, language="de")
        self.assertTrue(report.skipped, "nothing was skipped for German")
        for name, why in report.skipped.items():
            with self.subTest(check=name):
                self.assertIn("de", why)
        self.assertIn("acronyms", report.ran,
                      "a structural check must still run")

    def test_english_runs_everything(self):
        doc = Manuscript.load(self.root)
        report = run_craft(doc, TECHNICAL, language="en")
        self.assertEqual(report.skipped, {})

    def test_a_language_neutral_check_says_so(self):
        self.assertEqual(registry()["acronyms"].languages, ANY_LANGUAGE)


# ---------------------------------------------------------------------------
# thresholds actually arrive
# ---------------------------------------------------------------------------


class ProjectSettingsReachTheChecks(TempProject):      # noqa: F405
    def test_craft_options_come_from_the_project(self):
        project = Project.open(self.root)
        project.settings = {"craft": {"echo_window": 3}}
        project.save()
        doc = project.manuscript()
        tight = run_craft(doc, TECHNICAL, only=["echo"],
                          options=project.craft_options())
        wide = run_craft(doc, TECHNICAL, only=["echo"],
                         options={"echo_window": 400})
        self.assertLess(len(tight.findings), len(wide.findings))

    def test_the_house_is_under_the_project(self):
        house = self.root.parent / "house.json"
        house.write_text(json.dumps({
            "name": "Acme", "terms": ["Widget"],
            "settings": {"craft": {"echo_window": 999}}}), encoding="utf-8")
        project = Project.open(self.root)
        self.assertTrue(project.house.found)
        self.assertEqual(project.craft_options()["echo_window"], 999)
        self.assertIn("Widget", project.effective_terms())
        project.settings = {"craft": {"echo_window": 5}}
        self.assertEqual(project.craft_options()["echo_window"], 5)


class FindingsAreCapped(TempProject):                 # noqa: F405
    def test_the_cap_says_how_many_it_did_not_list(self):
        doc = Manuscript.load(self.root)
        report = run_craft(doc, TECHNICAL, only=["echo"],
                           options={"max_findings": 2})
        self.assertLessEqual(len(report.findings), 3)
        self.assertTrue(any("not listed" in f.title
                            for f in report.findings))

    def test_zero_means_no_cap(self):
        doc = Manuscript.load(self.root)
        capped = run_craft(doc, TECHNICAL, only=["echo"],
                           options={"max_findings": 1})
        uncapped = run_craft(doc, TECHNICAL, only=["echo"],
                             options={"max_findings": 0})
        self.assertGreater(len(uncapped.findings), len(capped.findings))


# ---------------------------------------------------------------------------
# the project's own rules
# ---------------------------------------------------------------------------


class ProjectRules(TempProject):                      # noqa: F405
    def test_a_phrase_rule_finds_the_phrase(self):
        doc = Manuscript.load(self.root)
        (self.root / "extra.md").write_text(
            "# Extra\n\nSimply tighten the bolt.\n", encoding="utf-8")
        doc = Manuscript.load(self.root)
        rules = R.parse([{"id": "no-simply", "phrase": "simply",
                          "message": "no 'simply'"}])
        report = run_craft(doc, TECHNICAL, only=["rules"], rules=rules)
        self.assertTrue(report.findings)
        self.assertIn("simply", report.findings[0].title.lower())

    def test_a_broken_rule_reports_itself_rather_than_going_quiet(self):
        doc = Manuscript.load(self.root)
        rules = R.parse([{"id": "bad", "pattern": "(unclosed"}])
        report = run_craft(doc, TECHNICAL, only=["rules"], rules=rules)
        self.assertTrue(any("not running" in f.title
                            for f in report.findings))

    def test_a_project_rule_overrides_a_house_rule_of_the_same_id(self):
        house = R.parse([{"id": "x", "phrase": "a", "message": "house"}],
                        source="house")
        mine = R.parse([{"id": "x", "phrase": "b", "message": "mine"}])
        merged = R.merge(house, mine)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].message, "mine")


# ---------------------------------------------------------------------------
# document types
# ---------------------------------------------------------------------------


class DocumentTypes(TempProject):                     # noqa: F405
    def test_an_unknown_type_still_measures(self):
        profile = DT.get("screenplay")
        self.assertEqual(profile.base, TECHNICAL)
        doc = Manuscript.load(self.root)
        report = run_craft(doc, "screenplay", profile=profile)
        self.assertTrue(report.ran)

    def test_a_declared_type_drops_the_checks_it_names(self):
        store = Store(self.root / ".workshop")
        store.write(DT.DOCTYPES_FILE, {"doctypes": [
            {"key": "release-notes", "base": TECHNICAL,
             "drop": ["readability", "passive"]}]})
        project = Project.open(self.root)
        project.document_type = "release-notes"
        project.save()
        profile = project.profile()
        self.assertEqual(profile.key, "release-notes")
        report = run_craft(project.manuscript(), "release-notes",
                           profile=profile)
        self.assertNotIn("readability", report.ran)
        self.assertIn("terminology", report.ran)

    def test_a_project_cannot_shadow_a_builtin(self):
        table = DT.parse([{"key": TECHNICAL, "drop": ["units"]}])
        self.assertEqual(table, {})


class Lyrics(unittest.TestCase):
    SONG = """# Song

[Verse 1]
The lamp was low and the city slept
A promise made and a promise kept

[Chorus]
And I'll be waiting by the water
Till you call my name again

[Verse 2]
The morning came with a colder light
A hollow sound in the amber night

[Chorus]
And I will wait beside the water
Till you call my name again
"""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "song.md").write_text(self.SONG, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_chorus_that_drifted_is_found(self):
        report = run_craft(Manuscript.load(self.root), LYRICS,
                           only=["refrain"])
        titles = [f.title for f in report.findings]
        self.assertTrue(any("chorus" in t.lower() for t in titles), titles)

    def test_verses_are_not_reported_as_drifted_refrains(self):
        """Two verses under one tag differ everywhere, which is what a
        verse IS. Reporting those four lines was this check's first
        output and its first false positive."""
        report = run_craft(Manuscript.load(self.root), LYRICS,
                           only=["refrain"])
        self.assertFalse([f for f in report.findings
                          if "verse" in f.title.lower()])

    def test_prose_checks_do_not_run_on_lyrics(self):
        report = run_craft(Manuscript.load(self.root), LYRICS)
        for name in ("echo", "readability", "passive", "openers"):
            self.assertNotIn(name, report.ran)

    def test_syllables_per_line_are_measured(self):
        report = run_craft(Manuscript.load(self.root), LYRICS,
                           only=["lyric_lines"])
        self.assertIn("syllables_per_line", report.metrics)


# ---------------------------------------------------------------------------
# .docx, read-only
# ---------------------------------------------------------------------------


def _docx(path: Path, body: str) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml",
                    '<?xml version="1.0"?><Types xmlns="http://schemas.'
                    'openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("word/document.xml",
                    f'<?xml version="1.0"?><w:document xmlns:w="{W}">'
                    f'<w:body>{body}</w:body></w:document>')
    return path


def _para(text, style=""):
    props = (f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else "")
    return f'<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>'


class Docx(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _docx(self.root / "manual.docx",
              _para("Servicing", "Heading1")
              + _para("The torque of 40 Nm applies to the housing.")
              + _para("4.2 Torque", "Heading2")
              + _para("Use a torque of 45 Nm on the cover.")
              + _para("Remove the cover.", "ListParagraph"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_headings_become_structure(self):
        doc = Manuscript.load(self.root)
        self.assertEqual([s.title for s in doc.sections],
                         ["Servicing", "Torque"])
        self.assertEqual(doc.sections[1].number, "4.2")

    def test_the_file_is_marked_derived_and_not_clickable(self):
        doc = Manuscript.load(self.root)
        self.assertTrue(doc.derived_files)
        self.assertFalse(doc.files[0].clickable)
        self.assertTrue(doc.notes())

    def test_the_measurements_still_work(self):
        doc = Manuscript.load(self.root)
        report = run_craft(doc, TECHNICAL, only=["units"])
        self.assertTrue([f for f in report.findings
                         if f.severity == "defect"])

    def test_step_numbering_is_not_checked_on_a_derived_file(self):
        """Word stores no list numbers — the renderer supplies them — so
        a gap found here would be one this package invented."""
        doc = Manuscript.load(self.root)
        report = run_craft(doc, TECHNICAL, only=["steps"])
        self.assertIn("steps_not_checked", report.metrics)

    def test_an_unreadable_file_is_reported_not_raised(self):
        (self.root / "broken.docx").write_bytes(b"not a zip")
        doc = Manuscript.load(self.root)
        self.assertTrue(doc.unreadable)
        self.assertTrue(any("broken.docx" in n for n in doc.notes()))
        self.assertTrue(doc.sections, "one bad file cost the good one")


# ---------------------------------------------------------------------------
# the codex fills itself honestly
# ---------------------------------------------------------------------------


class CastAndClaims(TempProject):                     # noqa: F405
    source = NOVEL                                    # noqa: F405

    def test_a_cast_is_read_from_the_document(self):
        doc = Manuscript.load(self.root)
        self.assertTrue(CAST.detect(doc, minimum=2))

    def test_deterministic_claims_no_longer_need_a_typed_cast(self):
        doc = Manuscript.load(self.root)
        self.assertTrue(CX.subjects_for(doc, None))

    def test_the_authors_own_list_still_wins(self):
        doc = Manuscript.load(self.root)
        self.assertEqual(CX.subjects_for(doc, ["Mira"]), ["Mira"])


class ConflictsCarryReadingOrder(unittest.TestCase):
    def test_the_earlier_claim_comes_first_and_the_arc_is_built(self):
        from writing_workshop.codex.claims import make
        from writing_workshop.continuity import contradictions as C
        from writing_workshop.types import ATTRIBUTE
        early = make("sword", "material", "bronze", kind=ATTRIBUTE,
                     section_id="a")
        late = make("sword", "material", "steel", kind=ATTRIBUTE,
                    section_id="b")
        out = C.find([late, early], order={"a": 0, "b": 9})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].a.value, "bronze")
        self.assertTrue(out[0].sequential)
        self.assertEqual([r["shown"] for r in out[0].arc],
                         ["bronze", "steel"])


class ConflictsAreOnePerValuePair(unittest.TestCase):
    """Forty mentions of bronze against twelve of steel is ONE finding.

    It used to be one per pair of CLAIMS — 480 of them, all saying the
    same sentence — and measured 5,821 on a single manuscript. A
    continuity report nobody can read is not a continuity report.
    """

    def test_many_mentions_of_two_values_are_one_conflict(self):
        from writing_workshop.codex.claims import make
        from writing_workshop.continuity import contradictions as C
        from writing_workshop.types import ATTRIBUTE
        claims = []
        for _ in range(40):
            claims.append(make("sword", "material", "bronze",
                               kind=ATTRIBUTE, section_id="a"))
        for _ in range(12):
            claims.append(make("sword", "material", "steel",
                               kind=ATTRIBUTE, section_id="b"))
        out = C.find(claims, order={"a": 0, "b": 9})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].mentions, (40, 12))

    def test_three_values_are_three_pairs_not_a_thousand(self):
        from writing_workshop.codex.claims import make
        from writing_workshop.continuity import contradictions as C
        from writing_workshop.types import ATTRIBUTE
        claims = []
        for value, section in (("bronze", "a"), ("steel", "b"),
                               ("iron", "c")):
            for _ in range(20):
                claims.append(make("sword", "material", value,
                                   kind=ATTRIBUTE, section_id=section))
        out = C.find(claims, order={"a": 0, "b": 4, "c": 9})
        self.assertEqual(len(out), 3)


class SweepIsCapped(TempProject):                     # noqa: F405
    source = NOVEL                                    # noqa: F405

    def test_the_cap_says_how_many_it_did_not_list(self):
        doc = Manuscript.load(self.root)
        from writing_workshop.codex.claims import make
        from writing_workshop.types import ATTRIBUTE
        claims = [make(f"thing{i}", "material", value, kind=ATTRIBUTE,
                       section_id="x")
                  for i in range(30) for value in ("bronze", "steel")]
        sweep = CN.sweep(doc, claims, max_findings=5)
        capped = [f for f in sweep.findings
                  if f.data.get("capped")]
        self.assertTrue(capped)
        self.assertEqual(sweep.metrics["conflicts"], 30)


class ChronologyIsAggregated(TempProject):            # noqa: F405
    source = NOVEL                                    # noqa: F405

    def test_a_summary_exists_beside_the_raw_list(self):
        doc = Manuscript.load(self.root)
        moments = CN.timeline(doc)
        summary = CN.summarise(moments)
        self.assertEqual(summary["total"], len(moments))
        self.assertIn("by_kind", summary)


class GoverningClaims(TempProject):                   # noqa: F405
    def test_only_the_claims_a_section_mentions_are_carried(self):
        doc = Manuscript.load(self.root)
        claims = CX.deterministic(doc)
        if not claims:
            self.skipTest("fixture has no deterministic claims")
        section = doc.sections[0]
        picked = CX.governing(doc, section, claims)
        for claim in picked:
            with self.subTest(subject=claim.subject):
                self.assertTrue(doc.find(claim.subject))

    def test_a_missing_retriever_costs_retrieval_and_nothing_else(self):
        doc = Manuscript.load(self.root)
        claims = CX.deterministic(doc)
        picked = CX.governing(doc, doc.sections[0], claims, retriever=None)
        self.assertIsInstance(picked, list)


# ---------------------------------------------------------------------------
# the fingerprint finally measures the book
# ---------------------------------------------------------------------------


class DriftAcrossVersions(TempProject):               # noqa: F405
    source = NOVEL                                    # noqa: F405

    def test_a_book_does_not_drift_from_itself(self):
        project = Project.open(self.root)
        project.document_type = FICTION
        project.save()
        versions = Versions(project)
        versions.save("baseline")
        report = DR.since_version(project.manuscript(), versions,
                                  "baseline")
        self.assertLess(report.overall, 0.5)

    def test_a_rewritten_chapter_shows_up(self):
        project = Project.open(self.root)
        versions = Versions(project)
        versions.save("baseline")
        target = sorted(self.root.glob("*.md"))[-1]
        head = target.read_text(encoding="utf-8").splitlines()[0]
        target.write_text(
            head + "\n\n" + ("She went. It was cold. He was there. "
                             "She saw him. He left. It was late.\n\n") * 30,
            encoding="utf-8")
        report = DR.since_version(project.manuscript(), versions,
                                  "baseline")
        self.assertGreater(report.overall, 1.0)
        self.assertTrue(report.summary())

    def test_a_missing_version_is_an_empty_report_not_a_crash(self):
        project = Project.open(self.root)
        report = DR.since_version(project.manuscript(),
                                  Versions(project), "nope")
        self.assertEqual(report.sections, [])


class InfluenceIsRecordedOutsideTheManuscript(TempProject):  # noqa: F405
    def test_an_accepted_passage_is_found_again_after_a_reflow(self):
        project = Project.open(self.root)
        influences = Influences(project.store)
        target = sorted(self.root.glob("*.md"))[0]
        text = target.read_text(encoding="utf-8")
        passage = ("The workshop measures before it generates, and it "
                   "never writes into the manuscript by itself at all.")
        target.write_text(text + "\n\n" + passage + "\n", encoding="utf-8")
        self.assertTrue(influences.record(passage, persona="line_editor"))
        doc = project.manuscript()
        self.assertEqual(influences.still_present(doc), 1)

    def test_a_passage_rewritten_past_recognition_stops_counting(self):
        project = Project.open(self.root)
        influences = Influences(project.store)
        influences.record("a passage that is nowhere in this manuscript "
                          "at all and never was, not once, anywhere")
        self.assertEqual(influences.still_present(project.manuscript()), 0)

    def test_the_baseline_can_leave_the_rooms_prose_out(self):
        project = Project.open(self.root)
        doc = project.manuscript()
        whole = FP.from_manuscript(doc)
        section = doc.sections[0]
        from writing_workshop.types import Span
        part = FP.from_manuscript(doc, exclude=[Span(
            section.path, section.body.start, section.body.end)])
        self.assertLess(part.n_words, whole.n_words)
        self.assertIn("excluded", part.fitted_on)

    def test_nothing_is_written_into_the_manuscript(self):
        project = Project.open(self.root)
        before = {p: p.read_bytes() for p in self.root.glob("*.md")}
        influences = Influences(project.store)
        influences.record("some text the author accepted from a persona "
                          "in the room, which is recorded outside the book")
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertTrue((self.root / ".workshop" / "influence.json"
                         ).exists())


if __name__ == "__main__":
    unittest.main()
