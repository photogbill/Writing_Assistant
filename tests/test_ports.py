# SPDX-License-Identifier: Apache-2.0
"""The ports, and the promise that the hostless path is a real path."""

from __future__ import annotations

import unittest

from _base import MANUAL
from writing_workshop import KeywordRetriever, Manuscript, NoModelError
from writing_workshop.ports import (Cancel, CollectingEvents, Host,
                                    NullLLM, Retrieved)


class Defaults(unittest.TestCase):
    def test_a_bare_host_is_a_working_host(self):
        """Blocks 1, 2, 2b and 5 run in exactly this configuration: no
        model, no store, no ledger, no voice. It is a supported state, not
        an error condition."""
        host = Host()
        self.assertFalse(host.has_model())
        self.assertFalse(host.ledger.available())
        self.assertFalse(host.speech.available())
        self.assertIsNone(host.llm.count_tokens("anything"))

    def test_the_null_model_refuses_by_name(self):
        with self.assertRaises(NoModelError) as caught:
            NullLLM().complete("s", "u")
        self.assertIn("craft measurements", str(caught.exception))


class Retrieval(unittest.TestCase):
    """`KeywordRetriever` is a real BM25 index, not a placeholder — the
    hostless path has to be a real path or the whole "useful with the GPU
    cold" claim is decoration."""

    def setUp(self):
        self.doc = Manuscript.load(MANUAL)
        self.store = KeywordRetriever()
        self.store.index(Retrieved(text=text, ref=ref, section_id=sid,
                                   order=order)
                         for text, ref, sid, order in self.doc.passages())

    def test_it_finds_the_right_passage(self):
        hits = self.store.query("torque for the lid bolts", top_k=1)
        self.assertTrue(hits)
        self.assertIn("lid bolts", hits[0].text)
        self.assertRegex(hits[0].text, r"4[05] Nm")

    def test_it_ranks_rather_than_matching(self):
        hits = self.store.query("bleed valve", top_k=3)
        self.assertGreater(len(hits), 1)
        scores = [h.score for h in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_an_empty_index_returns_nothing_rather_than_raising(self):
        self.assertEqual(KeywordRetriever().query("anything"), [])

    def test_refs_survive_so_a_hit_can_be_cited(self):
        hits = self.store.query("torque", top_k=1)
        self.assertIn("§", hits[0].ref)


class Cancellation(unittest.TestCase):
    def test_cancel_is_the_one_cross_thread_call(self):
        token = Cancel()
        self.assertFalse(token.is_set())
        token.set()
        self.assertTrue(token.is_set())


class Events(unittest.TestCase):
    def test_collecting_events_keeps_what_it_was_told(self):
        events = CollectingEvents()
        events.emit("progress", "one", i=1, n=2)
        events.emit("warning", "two")
        self.assertEqual(events.messages(), ["one", "two"])
        self.assertEqual(events.records[0][2], {"i": 1, "n": 2})


if __name__ == "__main__":
    unittest.main()
