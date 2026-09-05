# SPDX-License-Identifier: Apache-2.0
"""Which claims govern THIS passage — band 2, finally filled.

`ports.Retriever` ships a real BM25 index in the standard library, ATK
wires `SafeStore` into it, and until now **nothing in this package ever
called it.** Band 2 of the assembler is documented as *"the Codex claims
that constrain THIS section, retrieved"* and described as the highest
value-per-token in the whole design — twenty claims is a thousand tokens
and it is the difference between consistent and not — and in practice
`context.build(claims=…)` took whatever list its caller happened to pass.
A port that is wired end to end and never called is a feature that exists
in the documentation.

Two ways of finding the claims that matter to a passage, because they
fail differently:

* **By name.** A claim whose subject appears in the passage constrains
  it, and that is arithmetic — no model, no embedder, no retriever.
* **By retrieval.** A claim about "the harbour" governs a passage that
  talks about the quay and never says harbour. Only retrieval finds that,
  and it is exactly what the CPU embedder is there for.

The first is exact and runs everywhere. The second is a guess and is
ranked below it, always. A retriever that is absent, empty or broken
costs the second half and never the first — which is the same posture
every other port in this package takes.
"""

from __future__ import annotations

from ..types import ACCEPTED, Claim

#: Claims carried by default. Twenty is ~1,000 tokens at the ~50 tokens a
#: claim costs, which is what §4b priced the band at.
DEFAULT_LIMIT = 20


def index_claims(retriever, claims: list[Claim]) -> int:
    """Put the claims' own quoted passages into the host's retriever.

    The QUOTE is what gets indexed, not the claim's value: "the sword is
    bronze" retrieves poorly and the sentence it came from retrieves
    well, because it is real prose and the passage being written is real
    prose too.
    """
    if retriever is None:
        return 0
    rows = []
    for claim in claims:
        text = (claim.quote or f"{claim.subject} {claim.predicate} "
                f"{claim.value}").strip()
        if not text:
            continue
        rows.append(_row(text, str(claim.id), claim.section_id))
    if not rows:
        return 0
    try:
        return int(retriever.index(rows) or 0)
    except Exception:                                 # noqa: BLE001
        # A host's store may be cold, locked or mid-rebuild. Retrieval is
        # the half of this module that is allowed to be missing.
        return 0


def _row(text: str, ref: str, section_id: str):
    from ..ports import Retrieved
    return Retrieved(text=text, ref=ref, section_id=section_id)


def _mentioned(doc, section, claim: Claim) -> bool:
    subject = (claim.subject or "").strip()
    if len(subject) < 2:
        return False
    for span in doc.find(subject):
        if span.path != section.path:
            continue
        if section.body.start <= span.start < section.body.end:
            return True
    return False


def governing(doc, section, claims: list[Claim], *, retriever=None,
              limit: int = DEFAULT_LIMIT,
              accepted_only: bool = False) -> list[Claim]:
    """The claims a passage has to stay consistent with, best first.

    Ordering, and every part of it is deliberate:

    1. **Accepted before proposed.** A claim the author signed off is a
       fact about the document; a proposal is a reading of it, and a
       reading has no business constraining prose at the same weight.
    2. **Named before retrieved.** "The passage says 'sword'" is exact.
       "The passage is about something like this" is a guess.
    3. **Deterministic before model-read**, by `origin`, for the same
       reason as (1) one level down.

    Never more than `limit`, because band 2 has a price and the whole
    argument for it is that it is cheap.
    """
    live = [c for c in claims
            if c.state != "rejected" and c.superseded_by == 0
            and (not accepted_only or c.state == ACCEPTED)]
    if not live or section is None:
        return []

    scored: dict[int, tuple[tuple, Claim]] = {}
    for i, claim in enumerate(live):
        named = _mentioned(doc, section, claim)
        if not named:
            continue
        rank = (0 if claim.state == ACCEPTED else 1,
                0 if claim.origin in ("author", "measured") else 1,
                0, i)
        scored[id(claim)] = (rank, claim)

    if retriever is not None and len(scored) < limit:
        by_id = {str(c.id): c for c in live if c.id}
        try:
            hits = retriever.query(doc.prose(section), top_k=limit * 2)
        except Exception:                             # noqa: BLE001
            hits = []
        for rank_i, hit in enumerate(hits or []):
            claim = by_id.get(str(getattr(hit, "ref", "")))
            if claim is None or id(claim) in scored:
                continue
            scored[id(claim)] = (
                (0 if claim.state == ACCEPTED else 1,
                 0 if claim.origin in ("author", "measured") else 1,
                 1, rank_i), claim)

    ordered = sorted(scored.values(), key=lambda pair: pair[0])
    return [claim for _rank, claim in ordered][:limit]
