# SPDX-License-Identifier: Apache-2.0
"""Named drafts, visible on disk."""

from __future__ import annotations

import unittest

from _base import TempProject
from writing_workshop import Project, ProjectError
from writing_workshop.ports import FixedClock
from writing_workshop.versions import Versions


class Saving(TempProject):
    def setUp(self):
        super().setUp()
        self.project = Project.open(self.root)
        self.versions = Versions(self.project,
                                 clock=FixedClock("2026-08-29 12:00:00"))

    def test_a_version_is_a_folder_of_plain_files(self):
        info = self.versions.save("before the legal pass")
        folder = self.project.versions_dir / info.id
        self.assertTrue(folder.is_dir())
        self.assertTrue(sorted(folder.glob("*.md")))
        self.assertEqual(info.name, "before the legal pass")

    def test_names_are_the_authors_words_not_a_hash(self):
        info = self.versions.save("the version where she leaves")
        self.assertEqual(info.id, "the-version-where-she-leaves")

    def test_two_versions_with_one_name_do_not_collide(self):
        a = self.versions.save("draft")
        b = self.versions.save("draft")
        self.assertNotEqual(a.id, b.id)
        self.assertEqual(len(self.versions.list()), 2)

    def test_diff_against_what_is_on_disk_now(self):
        info = self.versions.save("before")
        path = self.root / "02-service.md"
        path.write_text(path.read_text(encoding="utf-8")
                        .replace("40 Nm", "42 Nm"), encoding="utf-8")
        blocks = self.versions.diff(info.id)
        self.assertEqual(list(blocks), ["02-service.md"])
        self.assertTrue(blocks["02-service.md"])


class Restoring(TempProject):
    def setUp(self):
        super().setUp()
        self.project = Project.open(self.root)
        self.versions = Versions(self.project)

    def test_restore_refuses_without_an_explicit_confirmation(self):
        info = self.versions.save("original")
        with self.assertRaises(ProjectError) as caught:
            self.versions.restore(info.id)
        self.assertIn("overwrites", str(caught.exception))

    def test_the_undo_exists_before_the_thing_it_undoes(self):
        """This is the only method in the package that overwrites the
        author's files. The snapshot is not optional and not a setting."""
        info = self.versions.save("original")
        path = self.root / "02-service.md"
        path.write_text("# Replaced\n\nEverything else is gone.\n",
                        encoding="utf-8")
        before = len(self.versions.list())
        self.versions.restore(info.id, confirm=True)
        self.assertIn("40 Nm", path.read_text(encoding="utf-8"))
        self.assertEqual(len(self.versions.list()), before + 1)
        snapshot = [v for v in self.versions.list()
                    if v.id.startswith("before-restoring")][0]
        self.assertIn("Replaced",
                      self.versions.text(snapshot.id, "02-service.md"))

    def test_restoring_something_that_is_not_there(self):
        with self.assertRaises(ProjectError):
            self.versions.restore("nope", confirm=True)


class TheIndexIsNotTheOnlyTruth(TempProject):
    """2026-10-28. A damaged `versions.json` listed nothing and the next
    save wrote a one-row index over it; a slug reused for a folder the
    index had forgotten copied a new version INTO the old one."""

    def setUp(self):
        super().setUp()
        self.project = Project.open(self.root)
        self.versions = Versions(self.project,
                                 clock=FixedClock("2026-08-29 12:00:00"))

    def test_a_damaged_index_still_lists_every_version(self):
        self.versions.save("first")
        self.versions.save("second")
        index = self.versions.index_path
        index.write_text(index.read_text(encoding="utf-8")[:40],
                         encoding="utf-8")
        found = {r.id for r in self.versions.list()}
        self.assertEqual(found, {"first", "second"})
        self.assertIn("could not be read", self.versions.problem)
        self.versions.save("third")
        self.assertEqual({r.id for r in Versions(self.project).list()},
                         {"first", "second", "third"})
        self.assertTrue(list(index.parent.glob("versions.json.corrupt-*")))

    def test_a_forgotten_folder_is_not_written_into(self):
        stale = self.project.versions_dir / "draft"
        stale.mkdir(parents=True)
        (stale / "99-cut-chapter.md").write_text("# Cut\n\nGone.\n",
                                                 encoding="utf-8")
        info = self.versions.save("draft")
        self.assertNotEqual(info.id, "draft")
        self.assertNotIn("99-cut-chapter.md",
                         self.versions.files_in(info.id))

    def test_a_cp1252_chapter_diffs_as_itself_not_as_deleted(self):
        path = self.root / "02-service.md"
        path.write_bytes("# Service\n\n“Don’t,” he said.\n".encode("cp1252"))
        info = self.versions.save("before")
        self.assertIn("Don’t", self.versions.text(info.id, "02-service.md"))
        self.assertEqual(self.versions.diff(info.id, "02-service.md"), {})


class FoundByTheIndependentCheck(TempProject):
    def setUp(self):
        super().setUp()
        self.project = Project.open(self.root)
        self.versions = Versions(self.project,
                                 clock=FixedClock("2026-08-29 12:00:00"))

    def test_a_row_missing_a_field_does_not_take_the_list_down(self):
        self.versions.save("first")
        self.versions.index_path.write_text('[{"id": "first"}]',
                                            encoding="utf-8")
        self.assertEqual([r.name for r in self.versions.list()], ["first"])

    def test_a_missing_index_is_said(self):
        self.versions.save("first")
        self.versions.index_path.rename(
            self.versions.index_path.with_name("gone.json"))
        self.assertEqual([r.id for r in self.versions.list()], ["first"])
        self.assertIn("missing", self.versions.problem)

    def test_a_save_that_died_mid_copy_is_not_a_version(self):
        (self.project.versions_dir / ".half.saving").mkdir(parents=True)
        self.assertEqual(self.versions.list(), [])
        info = self.versions.save("whole")
        self.assertTrue((self.project.versions_dir / info.id).is_dir())
        self.assertFalse(list(self.project.versions_dir.glob(".whole*")))

    def test_a_side_file_with_a_bom_is_read(self):
        from writing_workshop.state import Store
        store = Store(self.root / ".workshop")
        (self.root / ".workshop" / "dismissed.json").write_bytes(
            b"\xef\xbb\xbf" + b'{"entries": {"k": {"title": "t"}}}')
        self.assertIn("k", store.read("dismissed.json")["entries"])
        self.assertNotIn("dismissed.json", store.problems)


class ProjectSettingsAreNotTheBook(TempProject):
    def test_a_truncated_project_json_still_opens(self):
        project = Project.open(self.root)
        project.document_type = "fiction"
        project.save()
        path = project.dir / "project.json"
        whole = path.read_text(encoding="utf-8")
        path.write_text(whole[:25], encoding="utf-8")
        again = Project.open(self.root)
        self.assertTrue(again.problems)
        self.assertTrue(again.manuscript().sections)
        again.save()
        kept = list(project.dir.glob("project.json.corrupt-*"))
        self.assertEqual(kept[0].read_text(encoding="utf-8"), whole[:25])

    def test_an_unknown_target_field_does_not_stop_it_opening(self):
        project = Project.open(self.root)
        path = project.dir / "project.json"
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        data["targets"] = {"daily_words": 500, "added_in_2027": True}
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(Project.open(self.root).targets.daily_words, 500)


if __name__ == "__main__":
    unittest.main()
