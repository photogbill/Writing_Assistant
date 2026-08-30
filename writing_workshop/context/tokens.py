# SPDX-License-Identifier: Apache-2.0
"""Counting tokens, and being honest about which kind of count it is.

The assembler makes a promise the author can check — "carrying the outline,
22 claims and §4.2; §7 to §30 are summarised; nothing is out of view" — and
that promise is only worth having if the numbers behind it are real. So a
count is either EXACT (the loaded model's own tokeniser said so) or an
ESTIMATE, the difference is carried all the way to the manifest, and a host
that returns a guess from `count_tokens` instead of `None` breaks the one
thing this module exists to protect.
"""

from __future__ import annotations

import re

#: Characters per token, measured across English prose on the tokenisers
#: ATK's models actually use. Deliberately pessimistic: under-counting
#: overfills the window and the model silently loses the head of the
#: prompt, which is the failure mode with no symptom.
CHARS_PER_TOKEN = 3.6
WORDS_PER_TOKEN = 0.75

_WORDS = re.compile(r"\S+")


def estimate(text: str) -> int:
    """A deliberately conservative estimate. Never call this exact."""
    if not text:
        return 0
    words = len(_WORDS.findall(text))
    by_chars = len(text) / CHARS_PER_TOKEN
    by_words = words / WORDS_PER_TOKEN
    return int(max(by_chars, by_words)) + 1


class TokenCounter:
    """Exact counts when the host can give them, estimates when it cannot.

    Caches, because the assembler prices the same outline and the same
    style card on every request in a session, and a tokeniser call per
    candidate per keystroke is how a good idea becomes a slow one.
    """

    def __init__(self, llm=None) -> None:
        self.llm = llm
        self.exact = False
        self._cache: dict[str, int] = {}
        self._probe()

    def _probe(self) -> None:
        if self.llm is None:
            return
        try:
            got = self.llm.count_tokens("The quick brown fox.")
        except Exception:                        # noqa: BLE001
            got = None
        self.exact = isinstance(got, int) and got > 0

    def count(self, text: str) -> int:
        if not text:
            return 0
        hit = self._cache.get(text)
        if hit is not None:
            return hit
        value = None
        if self.exact:
            try:
                value = self.llm.count_tokens(text)
            except Exception:                    # noqa: BLE001
                # A tokeniser that starts failing mid-session must not take
                # the assembler with it -- and must not go on claiming its
                # numbers are exact either.
                self.exact = False
                value = None
        if not isinstance(value, int) or value <= 0:
            value = estimate(text)
        if len(self._cache) < 4096:
            self._cache[text] = value
        return value
