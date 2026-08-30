# SPDX-License-Identifier: Apache-2.0
"""The project: a folder of manuscript files plus one folder of our own.

Everything the workshop knows lives in `<root>/.workshop/`. Everything the
AUTHOR wrote lives beside it as plain `.md`. Delete `.workshop` and you
still have the book; that is the test this layout has to pass, and it is
why nothing here ever writes into a manuscript file.

`document_type` is the one setting with teeth. It selects which craft
checks run and which exports appear, and it is a project-level choice
rather than two workspaces because the spine — structure, claims,
continuity, fingerprint, versions — is identical for a manual and a novel.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re

from .document import Manuscript
from .errors import ProjectError
from .types import FICTION, TECHNICAL

WORKSHOP_DIR = ".workshop"
PROJECT_FILE = "project.json"


def _slug(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9]+", "-", name.strip().lower()).strip("-")
    return out or "untitled"


@dataclass
class Targets:
    """The session ritual. Small, slightly embarrassing, and the feature
    working writers actually open the app for."""

    daily_words: int = 0
    session_words: int = 0
    session_minutes: int = 0
    streak: int = 0
    last_day: str = ""
    history: dict[str, int] = field(default_factory=dict)


@dataclass
class Project:
    root: Path
    name: str = ""
    document_type: str = TECHNICAL
    #: Band 0 of the context assembler. The author's own words about how
    #: this document is written; never generated, never edited by the tool.
    style_card: str = ""
    #: Band 0 as well: house rules, register, the things a reviewer would
    #: send back. For a manual this is the style guide nobody reads.
    document_rules: str = ""
    #: Names the workshop should treat as characters (fiction) or as terms
    #: of art (technical). Seeded by the author, extended by proposal.
    cast: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    #: Section titles that hold definitions, for the undefined-term check.
    glossary_titles: list[str] = field(
        default_factory=lambda: ["glossary", "definitions", "terms",
                                 "terminology", "abbreviations",
                                 "acronyms", "nomenclature"])
    targets: Targets = field(default_factory=Targets)
    settings: dict = field(default_factory=dict)

    # -- paths ------------------------------------------------------------

    @property
    def dir(self) -> Path:
        return self.root / WORKSHOP_DIR

    @property
    def versions_dir(self) -> Path:
        return self.dir / "versions"

    @property
    def codex_db(self) -> Path:
        """Our own database FILE. A second file beside ATK's state.db is
        fine; a second schema inside it is not — the rule Cognitive Coder
        settled and the reason a project stays portable."""
        return self.dir / "codex.db"

    @property
    def fingerprint_file(self) -> Path:
        return self.dir / "fingerprint.json"

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    # -- lifecycle --------------------------------------------------------

    @classmethod
    def open(cls, root: str | Path, create: bool = True) -> "Project":
        root = Path(root)
        if not root.exists():
            if not create:
                raise ProjectError(f"no project folder at {root}")
            root.mkdir(parents=True, exist_ok=True)
        if root.is_file():
            root = root.parent
        proj = cls(root=root, name=root.name)
        path = root / WORKSHOP_DIR / PROJECT_FILE
        if path.exists():
            proj._apply(json.loads(path.read_text(encoding="utf-8")))
        elif create:
            proj.save()
        return proj

    def _apply(self, data: dict) -> None:
        self.name = data.get("name") or self.root.name
        self.document_type = (data.get("document_type") or TECHNICAL)
        if self.document_type not in (TECHNICAL, FICTION):
            self.document_type = TECHNICAL
        self.style_card = data.get("style_card", "")
        self.document_rules = data.get("document_rules", "")
        self.cast = list(data.get("cast") or [])
        self.terms = list(data.get("terms") or [])
        if data.get("glossary_titles"):
            self.glossary_titles = list(data["glossary_titles"])
        self.targets = Targets(**(data.get("targets") or {}))
        self.settings = dict(data.get("settings") or {})

    def save(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / PROJECT_FILE
        payload = {
            "name": self.name, "document_type": self.document_type,
            "style_card": self.style_card,
            "document_rules": self.document_rules,
            "cast": self.cast, "terms": self.terms,
            "glossary_titles": self.glossary_titles,
            "targets": asdict(self.targets), "settings": self.settings,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path

    # -- the manuscript ---------------------------------------------------

    def manuscript(self) -> Manuscript:
        """Re-read from disk every time, on purpose.

        The author is editing these files in another window — possibly in
        another program entirely — and a cached manuscript is a workshop
        reporting on a book that no longer exists. Reading forty files is
        milliseconds; being wrong about them is the whole product.
        """
        return Manuscript.load(self.root)

    @property
    def is_fiction(self) -> bool:
        return self.document_type == FICTION

    def invariant(self) -> list[tuple[str, str]]:
        """Band 0 material, as (reason, text) pairs."""
        out = []
        if self.style_card.strip():
            out.append(("style card", self.style_card.strip()))
        if self.document_rules.strip():
            out.append(("document rules", self.document_rules.strip()))
        return out

    # -- ritual -----------------------------------------------------------

    def record_words(self, day: str, words: int) -> Targets:
        """Update the streak. `day` is an ISO date the host supplies, so a
        test can drive a week in a millisecond and nothing here reads the
        clock behind the caller's back."""
        t = self.targets
        t.history[day] = words
        t.last_day = day
        days = sorted(t.history)
        streak = 0
        prev = None
        import datetime as _dt
        for d in days:
            if t.history[d] <= 0:
                streak = 0
                prev = None
                continue
            cur = _dt.date.fromisoformat(d)
            streak = streak + 1 if prev and (cur - prev).days == 1 else 1
            prev = cur
        t.streak = streak
        return t
