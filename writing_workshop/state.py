# SPDX-License-Identifier: Apache-2.0
"""The one module that writes the workshop's own side files.

Everything this package learns about a project lives in `.workshop/` and
NOTHING it learns lives in the manuscript. Dismissed findings, the keys of
the last run, which passages came out of The Room — every one of those is
a fact about the author's decisions, and every one of them would be a
temptation to annotate the prose with.

**Why one module rather than a file per feature.** `tests/test_boundary.py`
fails the build if anything outside a short named list opens a file for
writing, and that list is the whole guarantee that the author's editor is
the only thing that touches the book. A guard whose allow-list grows by
one entry per feature stops being a guard. So features get a `Store` and
the allow-list stays at five.

Writes are atomic — a temporary file beside the target, then a replace —
because the alternative is a half-written `dismissed.json` after a power
cut, and the failure mode of that is every dismissal the author ever made
coming back at once.

**A file that does not parse is kept, never overwritten.** These files are
documented as human-readable and people do open them; one trailing comma
used to make `dismissed.json` read as empty, and the next dismissal wrote
a one-entry file over the author's four hundred. Now a trailing comma is
forgiven on read, anything worse is reported in `Store.problems`, and the
first write after that copies the damaged file to
`<name>.corrupt-<time>` before replacing it.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

#: `.workshop/` file names, named here so nothing else spells them.
DISMISSED = "dismissed.json"
LAST_RUN = "last-run.json"
INFLUENCE = "influence.json"
RULES = "rules.json"
#: Spelled here as well as in `doctypes.DOCTYPES_FILE`, which predates this
#: module's rule that nothing else spells a file name. `doctypes` imports it
#: from here now, so there is one spelling and a rename cannot half-happen.
DOCTYPES = "doctypes.json"
HOUSE = "house.json"


def _without_trailing_commas(text: str) -> str:
    """`[1, 2,]` → `[1, 2]`, outside strings only. The one hand-editing
    slip JSON refuses that a person would never call an error."""
    out: list[str] = []
    in_string = escaped = False
    pending = ""
    for ch in text:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if pending:
            if ch.isspace():
                pending += ch
                continue
            if ch in "}]":
                pending = pending[1:]           # drop the comma, keep space
            out.append(pending)
            pending = ""
        if ch == ",":
            pending = ","
            continue
        if ch == '"':
            in_string = True
        out.append(ch)
    out.append(pending)
    return "".join(out)


def parse_json(text: str) -> tuple[Any, str]:
    """(data, note). Raises ValueError when it is not JSON even forgiven.

    `note` is "" for clean JSON and says what was forgiven otherwise."""
    try:
        return json.loads(text), ""
    except json.JSONDecodeError as first:
        repaired = _without_trailing_commas(text)
        if repaired != text:
            try:
                return json.loads(repaired), "read with a trailing comma " \
                    "ignored"
            except json.JSONDecodeError:
                pass
        raise ValueError(f"{first.msg} at line {first.lineno} column "
                         f"{first.colno}") from first


def _parses(path: Path) -> bool:
    try:
        parse_json(path.read_text(encoding="utf-8-sig"))
        return True
    except (ValueError, UnicodeDecodeError):
        return False
    except OSError:
        return True          # unreadable: nothing to copy, nothing to lose


def keep_damaged(path: Path) -> Path | None:
    """Copy `path` aside if it exists and is not JSON. Returns the copy.

    Called before anything replaces a side file, so the one thing a
    damaged file can still be — the author's data, a keystroke away from
    readable — is never what the replace destroys."""
    path = Path(path)
    if not path.exists() or _parses(path):
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.corrupt-{stamp}")
    n = 2
    while dest.exists():
        dest = path.with_name(f"{path.name}.corrupt-{stamp}-{n}")
        n += 1
    shutil.copy2(path, dest)
    return dest


def write_atomic(target: Path, text: str) -> Path:
    """Write `text` to `target` through a uniquely named temporary file.

    Unique because two writers sharing `<name>.tmp` interleave: the second
    truncates the first's half-written file and both replaces land the
    same torn bytes."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return target


class Store:
    """A folder of small JSON documents, read and written by name.

    Every read is total: a missing file, an unreadable one and a corrupt
    one all return the default. That is deliberate — none of this data is
    the book, so losing it must degrade a feature and never block the
    author from opening their manuscript.
    """

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)
        #: name -> what went wrong reading or replacing it. A host shows
        #: these; a feature that quietly started empty is a lie.
        self.problems: dict[str, str] = {}

    def path(self, name: str) -> Path:
        return self.dir / name

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def read(self, name: str, default: Any = None) -> Any:
        path = self.path(name)
        if not path.exists():
            return {} if default is None else default
        try:
            # `utf-8-sig`: a file saved by older Notepad starts with a BOM,
            # which JSON refuses — every dismissal "vanished" until the
            # author found an invisible character.
            data, note = parse_json(path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            self.problems[name] = (
                f"{name} could not be read ({exc}). It is left exactly as "
                f"it is; until it is fixed this starts empty, and the next "
                f"save keeps a copy as {name}.corrupt-<time> first.")
            return {} if default is None else default
        if note:
            self.problems[name] = f"{name} was {note}."
        else:
            self.problems.pop(name, None)
        return data

    def write(self, name: str, data: Any) -> Path:
        """Write atomically. Returns the path, or raises OSError."""
        target = self.path(name)
        kept = keep_damaged(target)
        write_atomic(target, json.dumps(data, indent=2, ensure_ascii=False))
        if kept is not None:
            self.problems[name] = (
                f"{name} could not be read, so it was replaced — the "
                f"damaged file is kept as {kept.name}.")
        else:
            self.problems.pop(name, None)
        return target

    def update(self, name: str, changes: dict) -> Any:
        data = self.read(name, {})
        if not isinstance(data, dict):
            data = {}
        data.update(changes)
        self.write(name, data)
        return data
