# SPDX-License-Identifier: Apache-2.0
"""Every error this package raises, and what a host is meant to do about it.

The rule the whole package follows: **an error says what could not be done
and what would fix it.** A `ValueError("bad input")` reaching a GUI becomes
a dialog the author cannot act on, and ATK has paid for that lesson more
than once.
"""

from __future__ import annotations


class WorkshopError(Exception):
    """Base class, so a host can catch everything from here in one clause."""


class ProjectError(WorkshopError):
    """The project folder is missing, unreadable, or not a project."""


class BandZeroWontFit(WorkshopError):
    """The invariant band does not fit the context budget.

    This is a REFUSAL, not a degradation, and that is the whole point of it.
    Band 0 is the style card, the document rules and the section brief —
    the material that defines what the work is. Silently dropping it
    produces a request the model answers confidently and wrongly, and
    nothing downstream can tell that happened.

    Carries what did not fit so the host can say so.
    """

    def __init__(self, needed: int, budget: int, items: list[str]):
        self.needed = needed
        self.budget = budget
        self.items = items
        super().__init__(
            f"the invariant context needs {needed} tokens and the budget is "
            f"{budget}. Not dropping it — {', '.join(items)} defines the "
            f"work. Load a model with a larger usable context, allow layer "
            f"offload, or shorten the style card.")


class NoModelError(WorkshopError):
    """A model-backed feature was asked for with no LLM port wired.

    Named separately because it is the ONE failure the workshop expects to
    hit routinely: blocks 1, 2, 2b and 5 work with no model at all, and an
    author on a plane should be told "that part needs a model" rather than
    shown a stack trace.
    """


class LedgerUnavailable(WorkshopError):
    """O.W.L. is not importable or is switched off.

    Not fatal anywhere: the Codex degrades to a plain list, the same way
    every other O.W.L. surface in ATK does.
    """
