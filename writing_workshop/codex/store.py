# SPDX-License-Identifier: Apache-2.0
"""The Codex store: sqlite in the project's own folder.

A SECOND DATABASE FILE beside ATK's `state.db` is fine; a second schema
inside it is not. That is the rule Cognitive Coder settled and it is what
keeps a project portable — copy the folder and the Codex travels with the
manuscript, delete `.workshop` and the book is untouched.

Every state change is journalled. `accepted` is a decision the author made
and a Codex that cannot say when, or what it superseded, is a bible with no
provenance — which is the only thing it was for.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

from ..types import (ACCEPTED, PROPOSED, REJECTED, SUPERSEDED, Claim, Span)

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subject       TEXT NOT NULL,
    kind          TEXT NOT NULL,
    predicate     TEXT NOT NULL,
    value         TEXT NOT NULL,
    unit          TEXT DEFAULT '',
    number        REAL,
    source_ref    TEXT DEFAULT '',
    section_id    TEXT DEFAULT '',
    path          TEXT DEFAULT '',
    span_start    INTEGER DEFAULT 0,
    span_end      INTEGER DEFAULT 0,
    quote         TEXT DEFAULT '',
    state         TEXT NOT NULL DEFAULT 'proposed',
    origin        TEXT DEFAULT 'author',
    superseded_by INTEGER DEFAULT 0,
    note          TEXT DEFAULT '',
    key           TEXT DEFAULT '',
    created       TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS claims_key   ON claims(key);
CREATE INDEX IF NOT EXISTS claims_state ON claims(state);
CREATE INDEX IF NOT EXISTS claims_subj  ON claims(subject);
CREATE TABLE IF NOT EXISTS journal (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    action   TEXT NOT NULL,
    at       TEXT DEFAULT '',
    detail   TEXT DEFAULT ''
);
"""

_COLS = ("id", "subject", "kind", "predicate", "value", "unit", "number",
         "source_ref", "section_id", "path", "span_start", "span_end",
         "quote", "state", "origin", "superseded_by", "note", "key",
         "created")


class Codex:
    def __init__(self, path: str | Path, clock=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()
        self._clock = clock

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:                            # noqa: BLE001
            pass

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now()
        import datetime as _dt
        return _dt.datetime.now().replace(microsecond=0).isoformat(" ")

    # -- writing ----------------------------------------------------------

    def add(self, claim: Claim, dedupe: bool = True) -> Claim:
        """Insert a claim as PROPOSED. Re-adding the same claim from the
        same passage is a no-op, so re-running extraction after an edit
        does not multiply the Codex by the number of times it was run."""
        if dedupe:
            existing = self._find_same(claim)
            if existing is not None:
                return existing
        row = (claim.subject, claim.kind, claim.predicate, claim.value,
               claim.unit, claim.number, claim.source_ref, claim.section_id,
               claim.span.path if claim.span else "",
               claim.span.start if claim.span else 0,
               claim.span.end if claim.span else 0, claim.quote,
               claim.state or PROPOSED, claim.origin, claim.superseded_by,
               claim.note, claim.key, self._now())
        cur = self.db.execute(
            "INSERT INTO claims (subject,kind,predicate,value,unit,number,"
            "source_ref,section_id,path,span_start,span_end,quote,state,"
            "origin,superseded_by,note,key,created) VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
        claim.id = int(cur.lastrowid)
        self._journal(claim.id, "proposed", claim.source_ref)
        self.db.commit()
        return claim

    def _find_same(self, claim: Claim) -> Claim | None:
        cur = self.db.execute(
            "SELECT * FROM claims WHERE key=? AND value=? AND source_ref=? "
            "AND state != ?",
            (claim.key, claim.value, claim.source_ref, REJECTED))
        row = cur.fetchone()
        return _to_claim(row) if row else None

    def _journal(self, claim_id: int, action: str, detail: str = "") -> None:
        self.db.execute(
            "INSERT INTO journal (claim_id,action,at,detail) VALUES "
            "(?,?,?,?)", (claim_id, action, self._now(), detail))

    def set_state(self, claim_id: int, state: str, note: str = "") -> None:
        self.db.execute("UPDATE claims SET state=? WHERE id=?",
                        (state, claim_id))
        self._journal(claim_id, state, note)
        self.db.commit()

    def accept(self, claim_id: int, note: str = "") -> None:
        self.set_state(claim_id, ACCEPTED, note)

    def reject(self, claim_id: int, note: str = "") -> None:
        self.set_state(claim_id, REJECTED, note)

    def supersede(self, old_id: int, new_claim: Claim,
                  note: str = "") -> Claim:
        """The fact changed. The old claim is kept, marked, and linked.

        Deleting it would be the obvious implementation and it destroys
        `reconsider`: knowing that the sword USED to be bronze is the
        entire basis for finding the four passages that still say so.
        """
        new_claim.state = ACCEPTED
        added = self.add(new_claim, dedupe=False)
        self.db.execute(
            "UPDATE claims SET state=?, superseded_by=? WHERE id=?",
            (SUPERSEDED, added.id, old_id))
        self._journal(old_id, "superseded", note or f"by #{added.id}")
        self._journal(added.id, "accepted", note)
        self.db.execute("UPDATE claims SET state=? WHERE id=?",
                        (ACCEPTED, added.id))
        self.db.commit()
        return added

    def add_many(self, claims: list[Claim]) -> list[Claim]:
        return [self.add(c) for c in claims]

    # -- reading ----------------------------------------------------------

    def get(self, claim_id: int) -> Claim | None:
        row = self.db.execute("SELECT * FROM claims WHERE id=?",
                              (claim_id,)).fetchone()
        return _to_claim(row) if row else None

    def all(self, state: str | None = None,
            kind: str | None = None) -> list[Claim]:
        sql = "SELECT * FROM claims"
        args: list = []
        where = []
        if state:
            where.append("state=?")
            args.append(state)
        if kind:
            where.append("kind=?")
            args.append(kind)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id"
        return [_to_claim(r) for r in self.db.execute(sql, args)]

    def about(self, subject: str, include_superseded: bool = True
              ) -> list[Claim]:
        sql = "SELECT * FROM claims WHERE lower(subject)=lower(?)"
        if not include_superseded:
            sql += f" AND state != '{SUPERSEDED}'"
        return [_to_claim(r) for r in
                self.db.execute(sql + " ORDER BY id", (subject,))]

    def by_key(self, key: str) -> list[Claim]:
        return [_to_claim(r) for r in self.db.execute(
            "SELECT * FROM claims WHERE key=? ORDER BY id", (key,))]

    def governing(self, section_id: str, subjects: list[str] | None = None,
                  limit: int = 24) -> list[Claim]:
        """The accepted claims that constrain one section — band 2.

        The highest value-per-token material in the whole system: twenty
        claims is about a thousand tokens and it is the difference between
        consistent and not.

        **This is the store-only version and it is the weaker one.** It
        knows which section a claim was READ FROM, which is not the same
        question as which section a claim CONSTRAINS, and it takes the
        whole cast as `subjects` so every claim about anybody scores the
        same whether the passage mentions them or not.
        `writing_workshop.codex.select.governing` has the manuscript and
        can ask the real question — does this passage name the subject —
        and can use a retriever for the claims a passage is about without
        naming. Prefer it wherever a `Manuscript` is in hand; this stays
        for callers that have only the store.
        """
        rows = self.all(state=ACCEPTED)
        wanted = {s.lower() for s in (subjects or [])}
        scored = []
        for claim in rows:
            score = 0
            if claim.section_id == section_id:
                score += 3
            if wanted and claim.subject.lower() in wanted:
                score += 4
            if claim.kind in ("numeric", "temporal"):
                score += 1
            if score:
                scored.append((score, claim))
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [c for _s, c in scored[:limit]]

    def counts(self) -> dict:
        rows = self.db.execute(
            "SELECT state, COUNT(*) n FROM claims GROUP BY state")
        out = dict.fromkeys((PROPOSED, ACCEPTED, REJECTED, SUPERSEDED), 0)
        for row in rows:
            out[row["state"]] = row["n"]
        return out

    def history(self, claim_id: int) -> list[tuple[str, str, str]]:
        return [(r["action"], r["at"], r["detail"]) for r in self.db.execute(
            "SELECT * FROM journal WHERE claim_id=? ORDER BY id",
            (claim_id,))]

    # -- mirroring --------------------------------------------------------

    def mirror(self, ledger, limit: int = 0) -> int:
        """Push ACCEPTED claims into O.W.L. Only accepted ones, ever.

        A ledger that receives a model's proposals is a ledger whose
        provenance means nothing, and provenance is the only reason to use
        one.
        """
        if not getattr(ledger, "available", lambda: False)():
            return 0
        sent = 0
        for claim in self.all(state=ACCEPTED):
            text = (f"{claim.subject}: {claim.predicate} = {claim.value}"
                    + (f" ({claim.quote})" if claim.quote else ""))
            try:
                ledger.observe(text, origin="manuscript",
                               source_ref=claim.source_ref)
            except Exception:                        # noqa: BLE001
                continue
            sent += 1
            if limit and sent >= limit:
                break
        return sent


def _to_claim(row: sqlite3.Row) -> Claim:
    span = (Span(row["path"], row["span_start"], row["span_end"])
            if row["path"] else None)
    return Claim(
        subject=row["subject"], kind=row["kind"], predicate=row["predicate"],
        value=row["value"], id=row["id"], unit=row["unit"] or "",
        number=row["number"], source_ref=row["source_ref"] or "",
        section_id=row["section_id"] or "", span=span,
        quote=row["quote"] or "", state=row["state"],
        origin=row["origin"] or "author",
        superseded_by=row["superseded_by"] or 0, note=row["note"] or "")
