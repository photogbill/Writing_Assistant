# SPDX-License-Identifier: Apache-2.0
"""The Context Assembler — a knapsack, not a template.

The plan this replaces specified a fixed prompt string: summary + RAG +
previous 1000 words + request. That is the right answer for a 2048-token
window and the wrong one now, because the budget varies by EIGHT TIMES
depending on which model is loaded. So the assembler takes candidates and a
budget and packs by value per token.

Six bands, priced by what they buy:

    0  invariant       style card, document rules, the section brief
    1  immediate       the section being written and its neighbours
    2  governing       the claims that constrain THIS section
    3  the spine       the complete outline
    4  prior text      real prose, nearest first
    5  summaries       a paragraph per completed section

Bands 0-3 come to under 8k for a substantial manual, which fits in EVERY
model in ATK's folder including the 24B at 10,813 — that is why this design
works at both ends of the range instead of picking one.

Two rules do the real work.

**BAND 0 REFUSES.** If the invariant material does not fit, the assembler
raises rather than dropping it. Silently losing the style card produces a
confident answer in the wrong voice with nothing on screen to explain it.

**STABLE FIRST, VOLATILE LAST.** `Llama.generate()` reuses the KV cache for
the longest prefix shared with the previous call, so the stable material
belongs at the front; long-context attention degrades in the middle, so the
decision-relevant material belongs at the end. Those only fight if the
important material is also the stable material, and it is not: the bulk
(outline, prior text) is stable and general, the critical part (this
section's claims, the request) is volatile and specific. **Stable-first and
important-last are the same ordering.**
"""

from __future__ import annotations

from dataclasses import replace

from ..errors import BandZeroWontFit
from ..types import Assembly, Budget, Candidate
from .tokens import TokenCounter

BAND_INVARIANT = 0
BAND_IMMEDIATE = 1
BAND_CLAIMS = 2
BAND_SPINE = 3
BAND_PRIOR = 4
BAND_SUMMARY = 5

#: Header a band gets in the emitted prompt. The model is told what each
#: block IS, because "here is some text" and "here are the rules this
#: document is written to" are answered differently.
HEADERS = {
    BAND_INVARIANT: "",
    BAND_SPINE: "## The document's outline",
    BAND_PRIOR: "## Prior text from this document",
    BAND_SUMMARY: "## Sections summarised (not shown in full)",
    BAND_CLAIMS: "## Established facts that govern this passage",
    BAND_IMMEDIATE: "## The passage being worked on",
}

#: Emission order. Stable bands first for the cache, the volatile ones last
#: for attention. Band 0's stable half (style card, rules) leads; its
#: volatile half (this section's brief) travels with the volatile group.
STABLE_ORDER = (BAND_INVARIANT, BAND_SPINE, BAND_PRIOR, BAND_SUMMARY)
VOLATILE_ORDER = (BAND_INVARIANT, BAND_CLAIMS, BAND_IMMEDIATE)


def price(candidates: list[Candidate], counter: TokenCounter
          ) -> list[Candidate]:
    """Fill in `tokens` for anything that has not been priced yet."""
    out = []
    for cand in candidates:
        out.append(cand if cand.tokens else
                   replace(cand, tokens=counter.count(cand.text)))
    return out


def assemble(candidates: list[Candidate], budget: Budget,
             request: str = "", counter: TokenCounter | None = None,
             system: str = "") -> Assembly:
    """Pack the candidates into the budget and say what happened.

    Bands 0-3 are taken in order, each item by descending value per token.
    Band 4 fills what is left, nearest-first. Anything band 4 could not
    take falls back to its band-5 summary if it has one, which is what
    summarisation is for here: a COMPRESSION FALLBACK, not the headline
    mechanism the original plan made it.
    """
    counter = counter or TokenCounter()
    cands = price(candidates, counter)
    # `or 8192` only when NO model is loaded. Reading a real, small
    # budget as "unset" is how a 900-token model got an 8k allowance.
    limit = budget.input_tokens if budget.usable_tokens else 8192
    spent = counter.count(request) + counter.count(system)

    invariant = [c for c in cands if c.band == BAND_INVARIANT]
    need = sum(c.tokens for c in invariant)
    if need + spent > limit:
        raise BandZeroWontFit(need + spent, limit,
                              [c.reason for c in invariant])

    carried: list[Candidate] = list(invariant)
    spent += need
    summarised: list[Candidate] = []
    dropped: list[Candidate] = []

    for band in (BAND_IMMEDIATE, BAND_CLAIMS, BAND_SPINE, BAND_PRIOR):
        group = [c for c in cands if c.band == band]
        if band in (BAND_IMMEDIATE, BAND_PRIOR):
            # NOT value-per-token. Band 1 is "you cannot write this section
            # without it" and band 4 is "nearest first" -- both are ordered
            # priorities, not a knapsack. Pricing band 1 per token put a
            # short neighbouring section ahead of the section being
            # written, which is the one item in the whole prompt that
            # cannot be traded for anything.
            group.sort(key=lambda c: -c.value)
        else:
            group.sort(key=lambda c: (-c.value / max(1, c.tokens), c.tokens))
        for cand in group:
            if spent + cand.tokens <= limit:
                carried.append(cand)
                spent += cand.tokens
                continue
            summary = _summary_of(cand, counter)
            if summary is not None and spent + summary.tokens <= limit:
                carried.append(summary)
                summarised.append(cand)
                spent += summary.tokens
            else:
                dropped.append(cand)

    for cand in [c for c in cands if c.band == BAND_SUMMARY]:
        if any(s.key == cand.key for s in carried):
            continue
        if spent + cand.tokens <= limit:
            carried.append(cand)
            spent += cand.tokens
        else:
            dropped.append(cand)

    # THE CLOSING CHECK, and it is not belt-and-braces. Packing prices the
    # candidates; the EMITTED prompt also carries band headers, the
    # request header and a blank line between every block, and none of
    # that is a candidate. Charging an estimate for it up front is not
    # enough either -- headers only appear for bands that survived. So
    # the final text is measured and trimmed until it really fits, lowest
    # band first. An assembler that reports 396 of 376 tokens has told the
    # operator a number that is not true, which is the one thing the
    # Budget Meter cannot afford to do.
    text, carried, trimmed = _fit(carried, request, counter, limit)
    dropped.extend(trimmed)
    # A summary that was itself trimmed is OUT OF VIEW, not summarised.
    # Leaving it in both lists made the manifest contradict itself in the
    # one place the operator is relying on it to be exact.
    gone = {c.key for c in trimmed}
    summarised = [c for c in summarised if c.key not in gone]
    return Assembly(text=text, tokens=counter.count(text), budget=limit,
                    carried=carried, summarised=summarised, dropped=dropped,
                    exact_counts=counter.exact)


#: Trim in reverse priority. Band 0 is never trimmed -- if the invariant
#: material plus its own headers cannot fit, that is a refusal, not a
#: degradation, and it was already raised above.
TRIM_ORDER = (BAND_SUMMARY, BAND_PRIOR, BAND_SPINE, BAND_CLAIMS,
              BAND_IMMEDIATE)


def _fit(carried: list[Candidate], request: str, counter: TokenCounter,
         limit: int) -> tuple[str, list[Candidate], list[Candidate]]:
    text = _emit(carried, request, counter)
    trimmed: list[Candidate] = []
    guard = 0
    while counter.count(text) > limit and guard < 500:
        guard += 1
        victim = None
        for band in TRIM_ORDER:
            group = [c for c in carried if c.band == band]
            if group:
                victim = min(group, key=lambda c: (c.value, -c.tokens))
                break
        if victim is None:
            break
        carried.remove(victim)
        trimmed.append(victim)
        text = _emit(carried, request, counter)
    return text, carried, trimmed


def _summary_of(cand: Candidate, counter: TokenCounter) -> Candidate | None:
    if not cand.summary.strip():
        return None
    return Candidate(key=cand.key, band=BAND_SUMMARY, text=cand.summary,
                     reason=f"{cand.reason} (summarised)",
                     tokens=counter.count(cand.summary), stable=cand.stable,
                     value=cand.value)


def _emit(carried: list[Candidate], request: str,
          counter: TokenCounter) -> str:
    parts: list[str] = []
    seen: set[int] = set()

    def add(band: int, want_stable: bool) -> None:
        group = [c for c in carried
                 if c.band == band and c.stable is want_stable
                 and id(c) not in seen]
        if not group:
            return
        header = HEADERS.get(band, "")
        if header:
            parts.append(header)
        for cand in group:
            seen.add(id(cand))
            parts.append(cand.text.strip())

    for band in STABLE_ORDER:
        add(band, True)
    for band in VOLATILE_ORDER:
        add(band, False)
    # Anything a caller marked unusually (a stable claim, say) still ships,
    # after its band-mates rather than not at all.
    for cand in carried:
        if id(cand) not in seen:
            seen.add(id(cand))
            parts.append(cand.text.strip())
    if request.strip():
        parts.append("## The request")
        parts.append(request.strip())
    return "\n\n".join(p for p in parts if p)
