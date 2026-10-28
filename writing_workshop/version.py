# SPDX-License-Identifier: Apache-2.0
"""One place the version lives. `pyproject.toml` reads it from here."""

#: 1.2.0 — the Codex gained `author`, `revise` and `correct`, and with
#: `correct` a new column, so `Codex._migrate` runs on every open. A schema
#: that grows is exactly what a version number is for: a host that opens a
#: 1.2 Codex with 1.1 code reads `replaced_by` as missing rather than as
#: zero, and the difference between "no correction" and "the column is not
#: there" is the difference between a right answer and a traceback.
#:
#: 1.3.0 — the 2026-10-28 review. The Codex is shared across threads and
#: decides once (`add_many(new_only=)`, `for_sweep`); finding keys are
#: version 2 (`findings.KEY_VERSION`) and honour version-1 dismissals by
#: title; side files keep a damaged copy rather than overwriting it
#: (`Store.problems`, `Project.problems`, `Versions.problem`); craft reports
#: say which checks had nothing to say (`CraftReport.quiet`). ATK requires
#: this version (`atk.core.writing.MIN_ENGINE`).
#:
#: 1.4.0 — what was left to build. Lyrics are first-class: the `suno` and
#: `voice_locks` checks (voice types read from the host's record, never
#: guessed), `lyric_alignment`, tags with descriptors; `codex.spec_sheet`;
#: `fingerprint.speaker_report`; read-aloud passages end at a paragraph;
#: "I Will Email You" is no longer section "I". ATK's new pages call these,
#: so ATK requires this version.
__version__ = "1.4.0"
