# SPDX-License-Identifier: Apache-2.0
"""One place the version lives. `pyproject.toml` reads it from here."""

#: 1.2.0 — the Codex gained `author`, `revise` and `correct`, and with
#: `correct` a new column, so `Codex._migrate` runs on every open. A schema
#: that grows is exactly what a version number is for: a host that opens a
#: 1.2 Codex with 1.1 code reads `replaced_by` as missing rather than as
#: zero, and the difference between "no correction" and "the column is not
#: there" is the difference between a right answer and a traceback.
__version__ = "1.2.0"
