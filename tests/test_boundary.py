# SPDX-License-Identifier: Apache-2.0
"""The boundary, enforced mechanically rather than by good intentions.

Three properties this package promises, each of which is easy to break by
accident with one convenient import and hard to notice afterwards:

1. **The engine never imports the host.** ATK's adapter imports the
   engine; the engine imports nothing from ATK. Break that and the
   workshop stops being usable from a terminal, from a test, or from any
   other host — and the day it breaks, nothing fails.
2. **The engine never imports Qt.** Everything that needs a widget lives
   in the adapter, which is what keeps the craft checks, the assembler and
   the claims model testable with no QApplication.
3. **Zero runtime dependencies.** Every measurement here is stdlib
   arithmetic on purpose: that is what lets the workshop be useful with
   the GPU cold, on a laptop, on a plane.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

from _base import *  # noqa: F401,F403

PACKAGE = Path(__file__).resolve().parents[1] / "writing_workshop"
FORBIDDEN_PREFIXES = ("atk", "PySide6", "PyQt5", "PyQt6", "shiboken6")
#: Allowed beyond the standard library: nothing.
ALLOWED_THIRD_PARTY: set[str] = set()


def _module_files():
    return sorted(PACKAGE.rglob("*.py"))


def _imports(tree: ast.AST):
    """Every module name imported, with whether it is at module level."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node))
        elif isinstance(node, ast.ImportFrom):
            if node.level:                      # relative — our own package
                continue
            if node.module:
                out.append((node.module, node))
    return out


class Boundary(unittest.TestCase):
    def test_the_engine_never_imports_the_host_or_qt(self):
        offenders = []
        for path in _module_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name, node in _imports(tree):
                root = name.split(".")[0]
                if root in FORBIDDEN_PREFIXES:
                    offenders.append(f"{path.name}:{node.lineno} {name}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_no_third_party_imports_at_all(self):
        stdlib = getattr(sys, "stdlib_module_names", None)
        if stdlib is None:                      # pragma: no cover
            self.skipTest("needs Python 3.10+ for stdlib_module_names")
        offenders = []
        for path in _module_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name, node in _imports(tree):
                root = name.split(".")[0]
                if root in stdlib or root in ALLOWED_THIRD_PARTY:
                    continue
                if root == "writing_workshop":
                    continue
                offenders.append(f"{path.name}:{node.lineno} {name}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_every_module_imports_cleanly_on_its_own(self):
        """A package that only works when imported in the right order is a
        package with an import cycle waiting to bite a host."""
        import importlib
        for path in _module_files():
            rel = path.relative_to(PACKAGE.parent).with_suffix("")
            name = ".".join(rel.parts)
            if name.endswith("__init__"):
                name = name[: -len(".__init__")]
            with self.subTest(module=name):
                importlib.import_module(name)


class NothingWritesTheManuscript(unittest.TestCase):
    """The rule the whole package rests on, checked the only way source
    can check it: NOTHING in the engine opens a manuscript file for
    writing. Versions copy files, exports return text, the Room returns
    suggestions. The author's editor is the only writer."""

    ALLOWED = {"versions.py",     # named drafts + an explicit restore
               "project.py",      # .workshop/project.json only
               "fingerprint.py",  # .workshop/fingerprint.json only
               "state.py",        # every other .workshop/ side file
               "cli.py"}          # --out, which the operator typed

    #: Anything that needs to persist goes through `state.Store` rather
    #: than opening a file of its own. An allow-list that grows by one
    #: entry per feature is not a guard, and this one is the whole reason
    #: the author's editor is the only thing that writes the book.

    def test_no_module_writes_text_except_the_named_ones(self):
        offenders = []
        for path in _module_files():
            if path.name in self.ALLOWED:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = getattr(func, "attr", None) or getattr(
                    func, "id", None)
                if name in ("write_text", "write_bytes"):
                    offenders.append(f"{path.name}:{node.lineno} {name}")
                if name == "open" and any(
                        isinstance(a, ast.Constant) and isinstance(
                            a.value, str) and "w" in a.value
                        for a in node.args):
                    offenders.append(f"{path.name}:{node.lineno} open(w)")
        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
