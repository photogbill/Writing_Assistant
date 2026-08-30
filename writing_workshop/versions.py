# SPDX-License-Identifier: Apache-2.0
"""Named drafts, visible on disk, in the author's own words.

The plan this replaces wanted version control that ran "invisibly to the
user". That is the wrong instinct and it is worth saying why: **hidden
version control is a data-loss trap.** When it goes wrong the author has no
model of what happened and no vocabulary to ask about it. So versions are
named — "the version where she leaves", "draft for legal review" — not
`a3f91c2`, and they are folders of plain files you can open in anything.

Restoring writes into the manuscript, which is the one place in this
package that does. It takes an explicit act, and it snapshots the current
state first, so the undo exists before the thing it undoes.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
import shutil

from . import textio as T
from .document import SKIP_DIRS, SUFFIXES
from .errors import ProjectError
from .types import VersionInfo

INDEX = "versions.json"


def _slug(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", name.strip().lower()).strip("-")
    base = base[:48] or "draft"
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


class Versions:
    def __init__(self, project, clock=None) -> None:
        self.project = project
        self.root = project.versions_dir
        self._clock = clock

    def _now(self) -> str:
        if self._clock is not None:
            return self._clock.now()
        import datetime as _dt
        return _dt.datetime.now().replace(microsecond=0).isoformat(" ")

    # -- index ------------------------------------------------------------

    @property
    def index_path(self) -> Path:
        return self.root / INDEX

    def list(self) -> list[VersionInfo]:
        if not self.index_path.exists():
            return []
        try:
            rows = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [VersionInfo(**row) for row in rows if isinstance(row, dict)]

    def _write_index(self, rows: list[VersionInfo]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps([asdict(r) for r in rows], indent=2,
                       ensure_ascii=False), encoding="utf-8")

    def get(self, version_id: str) -> VersionInfo | None:
        for row in self.list():
            if row.id == version_id:
                return row
        return None

    # -- saving -----------------------------------------------------------

    def save(self, name: str, note: str = "") -> VersionInfo:
        """Copy every manuscript file into a named folder."""
        rows = self.list()
        version_id = _slug(name, {r.id for r in rows})
        dest = self.root / version_id
        dest.mkdir(parents=True, exist_ok=True)
        files = 0
        words = 0
        for path in self._manuscript_files():
            rel = path.relative_to(self.project.root)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            files += 1
            try:
                words += len(T.word_list(
                    T.prose_of(path.read_text(encoding="utf-8"))))
            except (OSError, UnicodeDecodeError):
                pass
        info = VersionInfo(id=version_id, name=name.strip() or version_id,
                           created=self._now(), note=note, files=files,
                           words=words)
        rows.append(info)
        self._write_index(rows)
        return info

    def _manuscript_files(self) -> list[Path]:
        root = self.project.root
        return sorted(
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in SUFFIXES
            and not any(part in SKIP_DIRS or part.startswith(".")
                        for part in p.relative_to(root).parts))

    def delete(self, version_id: str) -> bool:
        rows = self.list()
        keep = [r for r in rows if r.id != version_id]
        if len(keep) == len(rows):
            return False
        shutil.rmtree(self.root / version_id, ignore_errors=True)
        self._write_index(keep)
        return True

    def rename(self, version_id: str, name: str, note: str | None = None
               ) -> VersionInfo | None:
        rows = self.list()
        for row in rows:
            if row.id == version_id:
                row.name = name
                if note is not None:
                    row.note = note
                self._write_index(rows)
                return row
        return None

    # -- reading ----------------------------------------------------------

    def files_in(self, version_id: str) -> list[str]:
        base = self.root / version_id
        if not base.exists():
            return []
        return sorted(str(p.relative_to(base)).replace("\\", "/")
                      for p in base.rglob("*")
                      if p.is_file() and p.suffix.lower() in SUFFIXES)

    def text(self, version_id: str, rel: str) -> str:
        path = self.root / version_id / rel
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def current_text(self, rel: str) -> str:
        path = self.project.root / rel
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def diff(self, version_id: str, rel: str = "",
             against: str = "") -> dict[str, list]:
        """Sentence-level hunks per file, this version against another
        (or against what is on disk now)."""
        from . import diff as D
        out: dict[str, list] = {}
        names = [rel] if rel else sorted(
            set(self.files_in(version_id))
            | set(self.files_in(against) if against else
                  [str(p.relative_to(self.project.root)).replace("\\", "/")
                   for p in self._manuscript_files()]))
        for name in names:
            old = self.text(version_id, name)
            new = (self.text(against, name) if against
                   else self.current_text(name))
            if old == new:
                continue
            out[name] = D.diff(old, new)
        return out

    # -- restoring --------------------------------------------------------

    def restore(self, version_id: str, *, confirm: bool = False,
                snapshot_name: str = "") -> VersionInfo:
        """Put a named version back. Snapshots the present first.

        The snapshot is not optional and not a setting. This is the only
        method in the package that overwrites the author's files, and the
        undo has to exist BEFORE the thing it undoes rather than being
        offered afterwards.
        """
        info = self.get(version_id)
        if info is None:
            raise ProjectError(f"no version named {version_id!r}")
        if not confirm:
            raise ProjectError(
                f"restoring “{info.name}” overwrites the manuscript on "
                f"disk. Call restore(confirm=True) once the author has "
                f"said so.")
        self.save(snapshot_name or f"before restoring {info.name}",
                  note="automatic snapshot taken before a restore")
        base = self.root / version_id
        for rel in self.files_in(version_id):
            target = self.project.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base / rel, target)
        return info
