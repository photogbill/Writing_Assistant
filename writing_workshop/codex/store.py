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
    created       TEXT DEFAULT '',
    replaced_by   INTEGER DEFAULT 0
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
         "created", "replaced_by")

#: Columns added after the first release, with the type to add them as.
#: `CREATE TABLE IF NOT EXISTS` does nothing to a table that already
#: exists, so a schema that grows needs this or every Codex written before
#: today raises `no such column` on the first read — which is the shape of
#: failure that looks like a corrupt project folder and is not.
_ADDED = {"replaced_by": "INTEGER DEFAULT 0"}


class Codex:
    def __init__(self, path: str | Path, clock=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()
        self.db.commit()
        self._clock = clock

    def _migrate(self) -> None:
        """Add columns this version knows about to a database written by
        an older one. Additive only — nothing is dropped, renamed or
        rewritten, because a migration that can lose an author's Codex is
        worse than a feature that has to wait."""
        have = {row[1] for row in self.db.execute("PRAGMA table_info(claims)")}
        for column, decl in _ADDED.items():
            if column not in have:
                self.db.execute(
                    f"ALTER TABLE claims ADD COLUMN {column} {decl}")

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

    # -- the author's own hand ---------------------------------------------
    #
    # Bill, 2026-09-06: *"everything should be editable, both the inputs and
    # the outputs."* He is right, and a ledger is the case where taking that
    # literally would destroy the thing being edited. Mutating an accepted
    # claim in place would silently rewrite the record `reconsider` reasons
    # over and the journal claims to hold; the answer is not to refuse the
    # edit but to give the author THREE verbs instead of one, because the
    # three things they might mean are genuinely different:
    #
    #   author()    a fact nothing read — the author asserts it themselves
    #   revise()    this claim is still PROPOSED and nearly right; fix it
    #   correct()   this claim is WRONG, as opposed to the fact having
    #               CHANGED, which is `supersede`
    #
    # Conflating the last two is the expensive mistake. `supersede` says the
    # world moved and both values were true in their turn, which is exactly
    # what makes `reconsider` able to find the four passages still saying
    # bronze. A correction says the claim never should have said that — a
    # parser that attached the wrong subject, a typo, the wrong kind — and
    # recording it as a supersession would send `reconsider` hunting the
    # manuscript for a value the manuscript never contained.

    def author(self, claim: Claim, *, accept: bool = False,
               note: str = "") -> Claim:
        """A claim the AUTHOR wrote, rather than one anything read.

        TWO JOURNAL ENTRIES WHEN ACCEPTED, never one. The rule that no
        constructor can make an accepted claim is not a formality to be
        routed around by the first path that finds it inconvenient — it is
        what makes `accepted` mean an act somebody took. The act is still
        taken here; it just happens in the same breath as the writing, and
        the journal records both halves in order.
        """
        claim.origin = "author"
        claim.state = PROPOSED
        added = self.add(claim, dedupe=False)
        if accept:
            self.accept(added.id, note or "written and accepted by the author")
            added.state = ACCEPTED
        return added

    def revise(self, claim_id: int, *, subject: str | None = None,
               predicate: str | None = None, value: str | None = None,
               kind: str | None = None, note: str | None = None) -> Claim:
        """Correct a claim IN PLACE. Only while it is still proposed.

        The one in-place edit in this store, and it is safe for exactly one
        reason: **nothing can depend on a proposed claim.** It is never
        mirrored into O.W.L., never returned by `governing`, never used by
        a check the author has agreed to, and no other claim links to it.
        The common case is a model proposal that is nearly right and would
        otherwise have to be rejected and retyped.

        An accepted claim is a different matter and raises — use `correct`,
        which keeps the wrong one and says why.
        """
        from . import claims as _claims

        current = self.get(claim_id)
        if current is None:
            raise ValueError(f"no claim #{claim_id}")
        if current.state != PROPOSED:
            raise ValueError(
                f"claim #{claim_id} is {current.state}, not proposed — a "
                f"claim the author has decided about is corrected, not "
                f"edited, so that the record says what happened")
        #: Rebuilt through `make` rather than written field by field: the
        #: number and unit are PARSED OUT of the value, so a value edited
        #: from "40 Nm" to "45 Nm" that kept number=40.0 would leave a
        #: numeric conflict check comparing the old figure against the new
        #: text for ever.
        fresh = _claims.make(
            subject if subject is not None else current.subject,
            predicate if predicate is not None else current.predicate,
            value if value is not None else current.value,
            kind=kind or current.kind, span=current.span,
            source_ref=current.source_ref, section_id=current.section_id,
            quote=current.quote, origin=current.origin,
            note=current.note if note is None else note)
        self.db.execute(
            "UPDATE claims SET subject=?, kind=?, predicate=?, value=?, "
            "unit=?, number=?, note=?, key=? WHERE id=?",
            (fresh.subject, fresh.kind, fresh.predicate, fresh.value,
             fresh.unit, fresh.number, fresh.note, fresh.key, claim_id))
        self._journal(claim_id, "revised",
                      f"{current.subject}: {current.predicate} = "
                      f"{current.value}")
        self.db.commit()
        fresh.id = claim_id
        fresh.state = PROPOSED
        return fresh

    def correct(self, old_id: int, new_claim: Claim,
                note: str = "") -> Claim:
        """The claim was WRONG. Not superseded — wrong.

        The old one is REJECTED rather than superseded, so `reconsider`
        does not go looking through the manuscript for passages that
        depend on a value the manuscript may never have contained. It is
        kept and linked, because a ledger that forgets its own mistakes
        cannot be audited for them, and because "why is this claim
        rejected" is a question with an answer worth storing.

        THE EVIDENCE IS INHERITED, not re-invented. A correction changes
        the READING of a passage, never the passage: the span, the quote,
        the source reference and the section come across unless the caller
        supplied their own. An author who retypes a quote has changed what
        the document is recorded as saying, which is the one edit this
        store must not offer.
        """
        old = self.get(old_id)
        if old is None:
            raise ValueError(f"no claim #{old_id}")
        if not new_claim.span and old.span:
            new_claim.span = old.span
        for field in ("source_ref", "section_id", "quote"):
            if not getattr(new_claim, field, ""):
                setattr(new_claim, field, getattr(old, field, ""))
        new_claim.origin = "author"
        new_claim.state = PROPOSED
        added = self.add(new_claim, dedupe=False)
        #: An accepted claim's correction is accepted: the author is not
        #: proposing a reading, they are asserting the right one in place
        #: of a wrong one they had already agreed to. A proposed claim's
        #: correction stays proposed, and would normally have gone through
        #: `revise` instead.
        if old.state in (ACCEPTED, SUPERSEDED):
            self.accept(added.id, note or f"corrects #{old_id}")
            added.state = ACCEPTED
        self.db.execute(
            "UPDATE claims SET state=?, replaced_by=? WHERE id=?",
            (REJECTED, added.id, old_id))
        self._journal(old_id, "corrected",
                      note or f"was “{old.subject}: {old.predicate} = "
                              f"{old.value}”; replaced by #{added.id}")
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
        superseded_by=row["superseded_by"] or 0, note=row["note"] or "",
        replaced_by=_column(row, "replaced_by"))


def _column(row: sqlite3.Row, name: str, default: int = 0):
    """A column an older database may not have. `_migrate` adds it on
    open, so this is belt and braces for a store opened read-only or by a
    caller that built its own connection."""
    try:
        return row[name] or default
    except (IndexError, KeyError):
        return default
