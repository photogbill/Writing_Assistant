# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures.

Every test here is `unittest`-style on purpose. ATK has been bitten once by
pytest-only test files: `python -m unittest discover` silently collects
NOTHING from them and reports OK while ten tests are failing. A suite that
can lie about being green is worse than no suite, so these run under both
runners.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANUAL = FIXTURES / "manual"
NOVEL = FIXTURES / "novel"


class TempProject(unittest.TestCase):
    """A copy of a fixture in a temp folder, so tests may write."""

    source = MANUAL

    def setUp(self) -> None:
        import shutil
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "project"
        shutil.copytree(self.source, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()
