# SPDX-License-Identifier: Apache-2.0
"""The assembler: what fits, what it cost, and what it refused to drop."""

from __future__ import annotations

import unittest

from _base import MANUAL

from writing_workshop import BandZeroWontFit, Manuscript, ModelInfo
from writing_workshop import context as CT
from writing_workshop.context.assembler import BAND_INVARIANT, assemble
from writing_workshop.types import Budget, Candidate


def budget(tokens: int, **kw) -> Budget:
    return CT.from_model(ModelInfo(name="test", usable_tokens=tokens,
                                   measured=True, **kw))


class BandZero(unittest.TestCase):
    def test_it_refuses_rather_than_dropping(self):
        """Silently losing the style card produces a confident answer in
        the wrong voice with nothing on screen to explain it."""
        doc = Manuscript.load(MANUAL)
        with self.assertRaises(BandZeroWontFit) as caught:
            CT.build(doc, doc.sections[0], budget=budget(400),
                     style_card="word " * 500)
        self.assertIn("style card", str(caught.exception))
        self.assertIn("style card", caught.exception.items)

    def test_the_refusal_says_what_would_fix_it(self):
        with self.assertRaises(BandZeroWontFit) as caught:
            assemble([Candidate("s", BAND_INVARIANT, "x " * 4000,
                                "style card")], budget(600))
        message = str(caught.exception)
        for hint in ("larger usable context", "offload", "shorten"):
            self.assertIn(hint, message)


class Packing(unittest.TestCase):
    def setUp(self):
        self.doc = Manuscript.load(MANUAL)
        self.section = self.doc.sections[2]

    def test_the_prompt_never_exceeds_the_budget_it_reports(self):
        """Packing prices the candidates; the emitted prompt also carries
        band headers and separators. Reporting 396 of 376 tokens is the
        one thing the Budget Meter cannot afford to do."""
        for tokens in (300, 400, 700, 1400, 4000, 12000):
            with self.subTest(tokens=tokens):
                assembly = CT.build(self.doc, self.section, request="Draft.",
                                    budget=budget(tokens),
                                    style_card="Short sentences.")
                self.assertLessEqual(assembly.tokens, assembly.budget)

    def test_a_small_real_budget_is_not_read_as_unset(self):
        """A 900-token model reserving 1024 for output gave an input
        budget of zero, which the assembler read as "unset" and replaced
        with its 8k default — the smallest model got the largest budget."""
        small = budget(900)
        self.assertGreater(small.input_tokens, 0)
        self.assertLess(small.input_tokens, 900)
        assembly = CT.build(self.doc, self.section, budget=small)
        self.assertLess(assembly.budget, 900)

    def test_the_section_being_written_outranks_a_shorter_neighbour(self):
        """Band 1 is an ordered priority, not a knapsack. Pricing it per
        token put a short neighbour ahead of the one item in the prompt
        that cannot be traded for anything."""
        assembly = CT.build(self.doc, self.section, budget=budget(700))
        carried = " ".join(c.reason for c in assembly.carried)
        self.assertIn(self.doc.label(self.section), carried)

    def test_the_manifest_never_says_both_summarised_and_out_of_view(self):
        for tokens in (300, 420, 600, 900):
            assembly = CT.build(self.doc, self.section, budget=budget(tokens))
            summarised = {c.key for c in assembly.summarised}
            dropped = {c.key for c in assembly.dropped}
            self.assertEqual(summarised & dropped, set(), tokens)

    def test_estimates_are_labelled_as_estimates(self):
        assembly = CT.build(self.doc, self.section, budget=budget(8000))
        self.assertFalse(assembly.exact_counts)
        self.assertIn("estimated", assembly.manifest())

    def test_exact_counts_when_the_host_can_give_them(self):
        class Exact:
            def count_tokens(self, text):
                return max(1, len(text) // 4)
        counter = CT.TokenCounter(Exact())
        assembly = CT.build(self.doc, self.section, budget=budget(8000),
                            counter=counter)
        self.assertTrue(assembly.exact_counts)
        self.assertNotIn("estimated", assembly.manifest())

    def test_passing_the_host_model_is_enough_to_get_exact_counts(self):
        """The gap this closes was silent. Every call site built its own
        `TokenCounter()` with no model, so the exact tokeniser the host
        offered was never used and the manifest said "estimated" about
        numbers it did not have to estimate."""
        class Exact:
            def count_tokens(self, text):
                return max(1, len(text) // 4)
        assembly = CT.build(self.doc, self.section, budget=budget(8000),
                            llm=Exact())
        self.assertTrue(assembly.exact_counts)
        self.assertNotIn("estimated", assembly.manifest())

    def test_a_host_that_guesses_is_not_trusted_forever(self):
        """A tokeniser that starts failing mid-session must not take the
        assembler with it, and must not go on claiming exactness."""
        class Flaky:
            def __init__(self):
                self.calls = 0

            def count_tokens(self, text):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("gone")
                return 5
        counter = CT.TokenCounter(Flaky())
        self.assertTrue(counter.exact)
        counter.count("something else entirely")
        self.assertFalse(counter.exact)


class Ordering(unittest.TestCase):
    def test_stable_first_volatile_last(self):
        """Cache efficiency wants the stable material first; long-context
        attention wants the decision-relevant material last. Those only
        fight if the important material is also the stable material, and
        it is not."""
        doc = Manuscript.load(MANUAL)
        assembly = CT.build(doc, doc.sections[2], request="Draft it.",
                            style_card="Short sentences.",
                            document_rules="Use shall.", budget=budget(9000))
        text = assembly.text
        self.assertLess(text.index("How this document is written"),
                        text.index("The document's outline"))
        self.assertLess(text.index("The document's outline"),
                        text.index("The passage being worked on"))
        self.assertLess(text.index("The passage being worked on"),
                        text.index("The request"))

    def test_the_stable_prefix_is_identical_between_two_sections(self):
        """The whole point: `Llama.generate()` reuses the KV cache for the
        longest prefix shared with the PREVIOUS call. If the prefix moves
        between requests, every request pays a full prefill."""
        doc = Manuscript.load(MANUAL)
        common = {"style_card": "Short sentences.",
                  "document_rules": "Use shall.", "budget": budget(20000),
                  "include_prior": False}
        a = CT.build(doc, doc.sections[2], request="One.", **common)
        b = CT.build(doc, doc.sections[3], request="Two.", **common)
        prefix = a.text[:a.text.index("Established facts")] \
            if "Established facts" in a.text else \
            a.text[:a.text.index("The passage being worked on")]
        self.assertTrue(b.text.startswith(prefix))


class Meter(unittest.TestCase):
    def test_the_price_line_appears_with_the_ceiling(self):
        """Without it the operator raises the context, everything gets
        mysteriously slower, and nothing connects the two."""
        spent = budget(40960, layers_on_card=28, total_layers=40,
                       host_mb=6100)
        lines = "\n".join(spent.meter_lines())
        self.assertIn("40,960 tokens usable", lines)
        self.assertIn("28 of 40 layers", lines)
        self.assertIn("system RAM", lines)

    def test_an_unmeasured_budget_says_so(self):
        guess = CT.from_model(ModelInfo(name="m", usable_tokens=8192))
        self.assertIn("Estimated", "\n".join(guess.meter_lines()))

    def test_no_model_is_a_state_not_an_error(self):
        self.assertIn("measurement and craft checks only",
                      "\n".join(CT.offline().meter_lines()))


class Summaries(unittest.TestCase):
    def test_band_five_needs_no_model(self):
        doc = Manuscript.load(MANUAL)
        text = CT.summarise(doc, doc.sections[2])
        self.assertIn("§4.2", text)
        self.assertIn("words", text)


if __name__ == "__main__":
    unittest.main()
