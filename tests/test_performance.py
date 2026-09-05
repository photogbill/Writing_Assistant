# SPDX-License-Identifier: Apache-2.0
"""The ratchets on the defect that made this package unusable at size.

`textio._is_boundary` used to end with `rest = text[end:]` and then
`rest.strip()`: a copy and a scan of the whole remainder of the file,
once per `.!?…`. On 610 KB of prose that is ~64,000 passes over an average
300 KB tail, and it made the craft pass over an 81,000-word document — a
document SMALLER than the 200-page manual this package was designed for —
take longer than five minutes. `Manuscript.quote()` compounded it by
re-splitting the entire file for every evidence quote: thirteen quotes
cost thirty-nine of one check's forty seconds.

Two of the three tests here are structural rather than timed, because a
timing test on a shared machine is a test that cries wolf. The structural
ones state the actual property:

* nothing in the sentence splitter slices the tail of the text, and
* `quote()` splits a file once however many times it is called.

The timed one is kept as a backstop and is deliberately generous.
"""

from __future__ import annotations

import ast
from pathlib import Path
import time
import unittest

from _base import *  # noqa: F401,F403

from writing_workshop import textio as T
from writing_workshop.document import Manuscript

TEXTIO = Path(T.__file__)


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone from textio")


class NoTailSlicing(unittest.TestCase):
    """The AST claim, per the house rule: pin the structure, not a string.

    An open-ended slice of the text inside a function called once per
    terminator is the quadratic defect, whatever it is spelled. Anything
    these functions need to know about what follows is a bounded
    lookahead, which `re.match(text, pos)` and a forward scan both give
    without allocating.
    """

    def _open_slices(self, name):
        tree = ast.parse(TEXTIO.read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(_function(tree, name)):
            if not isinstance(node, ast.Subscript):
                continue
            index = node.slice
            if not isinstance(index, ast.Slice):
                continue
            if index.upper is None and index.lower is not None:
                found.append(ast.dump(node))
        return found

    def test_is_boundary_never_slices_the_rest_of_the_file(self):
        self.assertEqual(self._open_slices("_is_boundary"), [])

    def test_continues_never_slices_the_rest_of_the_file(self):
        self.assertEqual(self._open_slices("_continues"), [])


class QuoteSplitsOnce(TempProject):                   # noqa: F405
    """`quote()` is called once per finding, and a craft pass produces
    hundreds. Splitting the file again for each is the difference between
    a report and a hang."""

    def test_a_file_is_split_into_sentences_once(self):
        doc = Manuscript.load(self.root)
        calls = []
        real = T.sentences

        def counted(text, base=0):
            calls.append(len(text))
            return real(text, base)

        T.sentences = counted
        try:
            src = doc.files[0]
            spans = [T.Block, None]                    # noqa: F841
            from writing_workshop.types import Span
            for i in range(0, 200, 4):
                doc.quote(Span(src.rel, i, i + 3))
        finally:
            T.sentences = real
        whole = [n for n in calls if n == len(doc.prose_of_file(src.rel))]
        self.assertEqual(len(whole), 1, f"split {len(whole)} times")


class SectionLookupIsExact(TempProject):              # noqa: F405
    """The bisect must return what the old linear scan returned."""

    def test_bisect_agrees_with_a_brute_force_scan(self):
        from writing_workshop.types import Span
        doc = Manuscript.load(self.root)
        for src in doc.files:
            length = len(doc.prose_of_file(src.rel))
            for pos in range(0, length, 17):
                span = Span(src.rel, pos, pos + 1)
                brute = None
                for sec in doc.sections:
                    if sec.path == span.path and (
                            sec.span.start <= pos < sec.span.end):
                        if brute is None or sec.level >= brute.level:
                            brute = sec
                got = doc.section_at(span)
                self.assertEqual(
                    got.id if got else None,
                    brute.id if brute else None,
                    f"disagreed at {src.rel}:{pos}")


class ScalesLinearly(unittest.TestCase):
    """The backstop. Generous on purpose — quadratic was 40x, not 2x."""

    def test_four_times_the_text_is_not_sixteen_times_the_work(self):
        unit = ("The housing is aluminium and the torque is 40 Nm. "
                "Tighten each bolt in sequence, then check the seal. "
                "See Figure 3 for the layout of the assembly. ") * 400
        small = unit
        large = unit * 4

        def timed(text):
            best = None
            for _ in range(3):
                start = time.perf_counter()
                T.sentences(text)
                took = time.perf_counter() - start
                best = took if best is None else min(best, took)
            return best

        one = timed(small)
        four = timed(large)
        if one < 0.002:                     # too fast to measure honestly
            self.skipTest("machine too fast for a meaningful ratio")
        self.assertLess(four / one, 10.0,
                        f"4x the text took {four / one:.1f}x the time — "
                        f"linear is 4, the old quadratic was ~16")


if __name__ == "__main__":
    unittest.main()
