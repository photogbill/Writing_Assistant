# SPDX-License-Identifier: Apache-2.0
"""The ATK Writing Workshop.

    A workshop that knows the whole document better than the author can
    hold in their head, and never writes in the author's place.

A 200-page manual and a 120,000-word novel share one failure mode — nobody
can hold either in working memory — so both break identically: the sword is
bronze in chapter 3 and steel in chapter 17; the torque spec is 40 Nm in
§4.2 and 45 in the appendix. Everything in this package exists to catch
that class of defect, and the order of the modules is the order of trust:

    textio, document, project    the manuscript, on disk, structure derived
    craft                        arithmetic. No model. Cannot hallucinate.
    context                      what fits in the model, and what it cost
    codex                        typed claims with provenance, proposed
    continuity                   contradictions, threads, chronology
    fingerprint                  the author's own voice, measured
    room, diff, versions         assistance, last, and never destructive

Four rules hold across all of it:

1. **Nothing writes into the manuscript but the author.** Not the
   extractor, not the Codex, not a persona, not a "fix all".
2. **Extraction proposes, never asserts.** Every model-read claim arrives
   as a proposal carrying its passage.
3. **Measurement before generation.** A tool whose first useful answer
   comes from a model is one the author has to fact-check.
4. **Say what was not done.** Refuse rather than silently degrade; name
   what was left out of a prompt; call an estimate an estimate.
"""

from __future__ import annotations

from .document import Manuscript, SourceFile
from .errors import (BandZeroWontFit, LedgerUnavailable, NoModelError,
                     ProjectError, WorkshopError)
from .ports import (Cancel, CollectingEvents, Host, KeywordRetriever,
                    ModelInfo, NoLedger, NoSpeech, NullLLM, Retrieved,
                    SilentEvents, Voice)
from .project import House, Project
from .types import (ACCEPTED, ATTRIBUTE, DEFECT, FICTION, LYRICS, NOTE,
                    NUMERIC, PROPOSED, RELATIONSHIP, SUPERSEDED, TECHNICAL,
                    TEMPORAL, WARN, Assembly, Budget, Candidate, Claim,
                    Conflict, CraftReport, Drift, Finding, Fingerprint,
                    Hunk, Paragraph, Section, Span, Suggestion, Thread,
                    VersionInfo)
from .version import __version__

__all__ = [
    "__version__", "Manuscript", "SourceFile", "Project", "House", "Host",
    "NullLLM", "KeywordRetriever", "NoLedger", "NoSpeech", "SilentEvents",
    "CollectingEvents", "Cancel", "ModelInfo", "Retrieved", "Voice",
    "WorkshopError", "ProjectError", "BandZeroWontFit", "NoModelError",
    "LedgerUnavailable", "Span", "Section", "Paragraph", "Finding",
    "CraftReport", "Claim", "Conflict", "Thread", "Candidate", "Assembly",
    "Budget", "Fingerprint", "Drift", "Suggestion", "Hunk", "VersionInfo",
    "NOTE", "WARN", "DEFECT", "TECHNICAL", "FICTION", "LYRICS",
    "ATTRIBUTE", "RELATIONSHIP", "TEMPORAL", "NUMERIC", "PROPOSED",
    "ACCEPTED", "SUPERSEDED",
]
