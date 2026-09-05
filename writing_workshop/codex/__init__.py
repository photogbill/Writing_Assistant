# SPDX-License-Identifier: Apache-2.0
"""The Codex — a story bible that is also an evidence ledger."""

from __future__ import annotations

from .claims import (
    attribute_claims,
    base_value,
    dimension,
    make,
    numeric_claims,
    parse_number,
    relationship_claims,
    temporal_claims,
)
from .extract import CLAIMS_GBNF, parse, propose
from .reconsider import (
    DIRECT,
    MENTION,
    NEARBY,
    Dependent,
    ask_model,
    find,
    for_claim,
)
from .select import DEFAULT_LIMIT, governing, index_claims
from .store import Codex

__all__ = ["Codex", "make", "numeric_claims", "temporal_claims",
           "attribute_claims", "relationship_claims", "parse_number",
           "base_value", "dimension", "propose", "parse", "CLAIMS_GBNF",
           "find", "for_claim", "ask_model", "Dependent", "DIRECT",
           "NEARBY", "MENTION", "deterministic", "governing",
           "index_claims", "subjects_for", "DEFAULT_LIMIT"]


def subjects_for(doc, given=None) -> list[str]:
    """Whose attributes to read, and where the list comes from.

    The author's cast if they typed one; otherwise the cast the document
    itself shows — see `writing_workshop.cast` for why that is not a
    guess worth refusing. Exposed rather than buried inside
    `deterministic()` so a host can SHOW which names it used: a Codex
    that filled itself from names nobody can see is a bible the author
    did not write, and the point of every proposal in this package is
    that the author can see what it was based on.
    """
    if given:
        return list(given)
    from .. import cast as _cast
    return _cast.detect(doc)


def deterministic(doc, *, subjects=None, terms=None) -> list:
    """Every claim that can be read with no model at all.

    Run first, always. The deterministic claims are the ones a numeric or
    temporal contradiction check can be trusted on, and having them in the
    Codex before any model speaks is what makes the model-proposed ones
    reviewable rather than overwhelming.
    """
    out = list(numeric_claims(doc, terms=terms))
    out.extend(temporal_claims(doc))
    out.extend(relationship_claims(doc))
    # Falls back to the cast the DOCUMENT shows when the project has not
    # named one. Before it did, an author who had not typed a cast list
    # got no attribute claims at all -- zero, measured on a 155,000-word
    # novel -- so the contradiction check had nothing to compare and the
    # Continuity page was emptiest on the document type that needs it
    # most. Every claim still arrives `proposed`; nothing is asserted.
    who = subjects_for(doc, subjects)
    if who:
        out.extend(attribute_claims(doc, list(who)))
    return out
