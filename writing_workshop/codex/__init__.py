# SPDX-License-Identifier: Apache-2.0
"""The Codex — a story bible that is also an evidence ledger."""

from __future__ import annotations

from .claims import (attribute_claims, base_value, dimension, make,
                     numeric_claims, parse_number, relationship_claims,
                     temporal_claims)
from .extract import CLAIMS_GBNF, parse, propose
from .reconsider import (DIRECT, MENTION, NEARBY, Dependent, ask_model,
                         find, for_claim)
from .store import Codex

__all__ = ["Codex", "make", "numeric_claims", "temporal_claims",
           "attribute_claims", "relationship_claims", "parse_number",
           "base_value", "dimension", "propose", "parse", "CLAIMS_GBNF",
           "find", "for_claim", "ask_model", "Dependent", "DIRECT",
           "NEARBY", "MENTION", "deterministic"]


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
    if subjects:
        out.extend(attribute_claims(doc, list(subjects)))
    return out
