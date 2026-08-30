# SPDX-License-Identifier: Apache-2.0
"""Model-read claims. They arrive as PROPOSALS and stay proposed.

ATK's rule about never presenting a guess as a fact applies here with
force. A Codex that silently fills itself with a model's readings of the
text becomes a bible the author never wrote and cannot trust — and every
continuity answer computed from it inherits that, invisibly.

Structure comes from a GRAMMAR, not from a parser. A model that writes
`##Intro` instead of `## Intro` produced zero sections and an empty
document in the code this workshop replaces, silently. The modern answer is
not a better parser: an outline or a claim list generated under a JSON
grammar CANNOT come back unparseable, and the whole failure class goes
away. The grammar is here; the host feeds it to llama.cpp.
"""

from __future__ import annotations

import json
import re

from ..errors import NoModelError
from ..ports import NEVER
from ..types import CLAIM_KINDS, Span
from .claims import make

#: A GBNF grammar for a JSON array of claims. Kept in this package rather
#: than borrowed from the host, so the shape of the output and the code
#: that reads it can never drift apart.
CLAIMS_GBNF = r'''
root        ::= "[" ws (claim (ws "," ws claim)*)? ws "]"
claim       ::= "{" ws
                "\"subject\"" ws ":" ws string ws "," ws
                "\"kind\"" ws ":" ws kind ws "," ws
                "\"predicate\"" ws ":" ws string ws "," ws
                "\"value\"" ws ":" ws string ws "," ws
                "\"quote\"" ws ":" ws string ws
                "}"
kind        ::= "\"attribute\"" | "\"relationship\"" | "\"temporal\"" | "\"numeric\""
string      ::= "\"" char* "\""
char        ::= [^"\\] | "\\" ["\\/bfnrt]
ws          ::= [ \t\n]*
'''

SYSTEM = ("You extract facts a document asserts about its own world. You "
          "never invent, never infer, and never summarise. Every fact must "
          "be quoted from the passage you were given.")

PROMPT = """Read the passage and list the facts it ASSERTS.

A fact is one of:
  attribute     — a property of a thing ("the housing is aluminium")
  relationship  — how two named things relate ("Mira is Aleksandr's sister")
  temporal      — when something happens ("the wedding is on Wednesday")
  numeric       — a named quantity with a value ("torque: 40 Nm")

Rules:
  * Quote the exact sentence each fact comes from.
  * If the passage asserts nothing, return [].
  * Do not list facts about the writing. Only about the world it describes.

{context}Passage ({label}):
{passage}
"""


def propose(host, doc, section, *, context: str = "", cancel=None,
            max_tokens: int = 700) -> list:
    """Ask the model what this section asserts. Returns PROPOSED claims.

    A map pass in the map-reduce sense: it needs only this section plus
    band 0, so it works at a 10k context as well as at 75k, and it is
    read-heavy — reads a few thousand tokens, writes two hundred — which
    is exactly the shape that can run on a heavily offloaded model while
    nobody waits.
    """
    passage = doc.prose(section).strip()
    if not passage:
        return []
    prompt = PROMPT.format(context=(context.strip() + "\n\n") if context
                           else "", label=doc.label(section),
                           passage=passage)
    try:
        raw = host.llm.complete(SYSTEM, prompt, temperature=0.0,
                                max_tokens=max_tokens,
                                grammar=CLAIMS_GBNF, cancel=cancel or NEVER)
    except NoModelError:
        raise
    except Exception as exc:                          # noqa: BLE001
        raise NoModelError(f"claim extraction failed: {exc}") from exc
    return parse(raw, doc, section)


def parse(raw: str, doc, section) -> list:
    """Read the model's JSON, and locate every quote in the real text.

    A claim whose quote is not in the section is DISCARDED, not repaired.
    That single rule is what stops a model's paraphrase entering the Codex
    with a source reference that looks authoritative and points at nothing.
    """
    data = _json_array(raw)
    prose = doc.prose_of_file(section.path)
    body = prose[section.body.start:section.body.end]
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject", "")).strip()
        value = str(item.get("value", "")).strip()
        predicate = str(item.get("predicate", "")).strip() or "is"
        kind = str(item.get("kind", "")).strip()
        quote = str(item.get("quote", "")).strip()
        if not subject or not value or kind not in CLAIM_KINDS:
            continue
        at = _locate(body, quote)
        if at < 0:
            continue
        span = Span(section.path, section.body.start + at,
                    section.body.start + at + len(quote))
        out.append(make(subject, predicate, value, kind=kind, span=span,
                        source_ref=_ref(doc, span),
                        section_id=section.id,
                        quote=" ".join(quote.split()), origin="extracted"))
    return out


def _locate(body: str, quote: str) -> int:
    if not quote:
        return -1
    at = body.find(quote)
    if at >= 0:
        return at
    # Whitespace differs constantly between what a model echoes and what is
    # on disk; nothing else is allowed to differ.
    flat = re.sub(r"\s+", " ", body)
    at = flat.find(re.sub(r"\s+", " ", quote))
    if at < 0:
        return -1
    consumed = 0
    for i, ch in enumerate(body):
        if consumed == at:
            return i
        if not (ch.isspace() and i and body[i - 1].isspace()):
            consumed += 1
    return -1


def _json_array(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return []
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _ref(doc, span: Span) -> str:
    from .claims import _ref as claim_ref
    return claim_ref(doc, span)
