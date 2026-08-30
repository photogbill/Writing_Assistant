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


if __name__ == "__main__":
    unittest.main()
