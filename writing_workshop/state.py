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
"""

from __future__ import annotations

import json
import os
from pathlib import Path
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


class Store:
    """A folder of small JSON documents, read and written by name.

    Every read is total: a missing file, an unreadable one and a corrupt
    one all return the default. That is deliberate — none of this data is
    the book, so losing it must degrade a feature and never block the
    author from opening their manuscript.
    """

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)

    def path(self, name: str) -> Path:
        return self.dir / name

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def read(self, name: str, default: Any = None) -> Any:
        path = self.path(name)
        if not path.exists():
            return {} if default is None else default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {} if default is None else default

    def write(self, name: str, data: Any) -> Path:
        """Write atomically. Returns the path, or raises OSError."""
        self.dir.mkdir(parents=True, exist_ok=True)
        target = self.path(name)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, target)
        return target

    def update(self, name: str, changes: dict) -> Any:
        data = self.read(name, {})
        if not isinstance(data, dict):
            data = {}
        data.update(changes)
        self.write(name, data)
        return data
