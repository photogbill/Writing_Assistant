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

from . import doctypes as DT
from . import rules as R
from . import state as ST
from .document import Manuscript
from .errors import ProjectError
from .types import FICTION, TECHNICAL

WORKSHOP_DIR = ".workshop"
PROJECT_FILE = "project.json"

#: How far up from the project root to look for a `house.json`. Four is
#: `books/fantasy/the-bronze-sword/` plus a shelf above it, and stopping
#: is the point: a search that walks to the filesystem root eventually
#: finds somebody else's house file and applies it silently.
HOUSE_DEPTH = 4

DEFAULT_LANGUAGE = "en"


@dataclass
class House:
    """Style shared by every project on a shelf.

    An author with twelve manuals under one house style keeps twelve
    copies of it, and twelve copies drift — which is the defect
    `terminology` exists to find, one level up. So the style card, the
    rules, the terms and the craft settings may live once, above the
    projects, and a project inherits them.

    **Inherited, never copied in.** The house values are held separately
    and merged on read, so `project.json` never acquires a snapshot of
    them: change the house file and every project follows, which is the
    whole reason to have one.
    """

    path: Path | None = None
    name: str = ""
    style_card: str = ""
    document_rules: str = ""
    terms: list[str] = field(default_factory=list)
    glossary_titles: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    rules: list = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.path is not None

    @classmethod
    def load(cls, root: Path) -> House:
        """The nearest `house.json` at or above `root`, if there is one."""
        here = Path(root).resolve()
        for parent in [here, *list(here.parents)[:HOUSE_DEPTH]]:
            candidate = parent / ST.HOUSE
            if candidate.exists():
                store = ST.Store(parent)
                data = store.read(ST.HOUSE, {})
                if not isinstance(data, dict):
                    continue
                return cls(
                    path=candidate, name=str(data.get("name") or ""),
                    style_card=str(data.get("style_card") or ""),
                    document_rules=str(data.get("document_rules") or ""),
                    terms=list(data.get("terms") or []),
                    glossary_titles=list(data.get("glossary_titles") or []),
                    settings=dict(data.get("settings") or {}),
                    rules=R.parse(data.get("rules"), source="house"))
        return cls()


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
    #: What language this manuscript is WRITTEN in, as an ISO code.
    #:
    #: It exists because almost every measurement in this package is
    #: English — the common-word list, the syllable heuristic, the filter
    #: words, the subordinators, the `-ly` adverb rule, the participle
    #: list, Flesch-Kincaid — and until now nothing recorded that or
    #: refused. Point a German manuscript at it and every check ran and
    #: every answer was confidently wrong: no word is "common", so every
    #: sentence is an echo and the rarity score is 1.0. That is rule 3
    #: inverted, in the one place the degradation cannot be seen from the
    #: output. Now a check declares the languages it is valid for and the
    #: rest are skipped WITH A REASON.
    language: str = DEFAULT_LANGUAGE
    _house: House | None = field(default=None, repr=False)

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
    def open(cls, root: str | Path, create: bool = True) -> Project:
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
        self.document_type = str(
            data.get("document_type") or TECHNICAL).strip().lower()
        self.style_card = data.get("style_card", "")
        self.document_rules = data.get("document_rules", "")
        self.cast = list(data.get("cast") or [])
        self.terms = list(data.get("terms") or [])
        if data.get("glossary_titles"):
            self.glossary_titles = list(data["glossary_titles"])
        self.targets = Targets(**(data.get("targets") or {}))
        self.settings = dict(data.get("settings") or {})
        self.language = str(data.get("language")
                            or DEFAULT_LANGUAGE).strip().lower() or \
            DEFAULT_LANGUAGE

    def save(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / PROJECT_FILE
        payload = {
            "name": self.name, "document_type": self.document_type,
            "style_card": self.style_card,
            "document_rules": self.document_rules,
            "cast": self.cast, "terms": self.terms,
            "glossary_titles": self.glossary_titles,
            "language": self.language,
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

    # -- the workshop's own side files ------------------------------------

    @property
    def store(self) -> ST.Store:
        """Where dismissals, the last run and influence spans live."""
        return ST.Store(self.dir)

    @property
    def house(self) -> House:
        if self._house is None:
            self._house = House.load(self.root)
        return self._house

    # -- what a caller should actually pass to the checks -----------------
    #
    # Every one of these is "the house, then this project on top". They
    # exist because the alternative -- copying the house values into
    # `project.json` at open time -- makes the house file a template
    # rather than a source, and the twelve copies drift again.

    def effective_style_card(self) -> str:
        parts = [p for p in (self.house.style_card.strip(),
                             self.style_card.strip()) if p]
        return "\n\n".join(parts)

    def effective_document_rules(self) -> str:
        parts = [p for p in (self.house.document_rules.strip(),
                             self.document_rules.strip()) if p]
        return "\n\n".join(parts)

    def effective_terms(self) -> list[str]:
        return list(dict.fromkeys([*self.house.terms, *self.terms]))

    def effective_glossary_titles(self) -> list[str]:
        return list(dict.fromkeys(
            [*self.house.glossary_titles, *self.glossary_titles]))

    def craft_options(self) -> dict:
        """Thresholds for the craft checks — house first, project over it.

        `Ctx.opt` has always read these and `craft.run` has always
        accepted them; until this existed nothing passed them, so
        `echo_window`, `target_grade`, `step_words_warn` and five others
        were reachable in code and unreachable in practice. A threshold
        nobody can set is a complaint rather than a setting.
        """
        merged = dict(self.house.settings.get("craft") or {})
        merged.update(self.settings.get("craft") or {})
        return merged

    def doctypes(self) -> dict:
        """Every document type this project may use."""
        return DT.load(self.store, self.house.settings.get("doctypes"))

    def profile(self):
        """The profile for THIS project's document type. Never None."""
        return DT.get(self.document_type, self.doctypes())

    def rules(self) -> list:
        """The project's own craft rules, with the house's underneath."""
        mine = R.parse(self.store.read(ST.RULES, None), source="project")
        return R.merge(self.house.rules, mine)

    def write_example_rules(self) -> Path:
        """Put a starter rules file in place, if there is not one."""
        if self.store.exists(ST.RULES):
            return self.store.path(ST.RULES)
        return self.store.write(ST.RULES, {"rules": R.example()})

    def invariant(self) -> list[tuple[str, str]]:
        """Band 0 material, as (reason, text) pairs."""
        out = []
        if self.effective_style_card().strip():
            out.append(("style card", self.effective_style_card().strip()))
        if self.effective_document_rules().strip():
            out.append(("document rules",
                        self.effective_document_rules().strip()))
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
