# SPDX-License-Identifier: Apache-2.0
"""Document types, and how a project declares one this package never met.

The original decision was right and is not being reversed: **one
workspace, both document types**. The spine — structure, claims,
continuity, fingerprint, versions — really is identical for a manual and
a novel, and splitting the UI would have doubled it for nothing.

What was wrong is that the type was a bare string in a tuple, so the third
and fourth kinds of document had no way in at all. A screenplay wants the
fiction checks minus the prose ones; an academic paper wants the technical
checks plus citation rules; a corpus of release notes wants three of the
twenty. None of those is a fork of the engine, and every one of them was.

So a document type is a **profile**: a base to inherit checks from, checks
to add or drop, thresholds, and a language. Three ship built in and the
rest live in `.workshop/doctypes.json` or in a `house.json` above the
project, which means a team can define one once for a shelf.

**A profile cannot invent a check.** It selects from the ones that exist,
by name. A type that could carry executable code would be a plugin system,
and a plugin system is how a package with zero dependencies and a boundary
test acquires both. The extensible half that authors actually ask for is
`writing_workshop.rules`, which is declarative and cannot hallucinate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import DOCTYPES as DOCTYPES_FILE, Store
from .types import DOC_TYPES, FICTION, LYRICS, TECHNICAL


@dataclass(frozen=True)
class DocType:
    """One kind of document, and which measurements it wants."""

    key: str
    label: str = ""
    #: Whose checks to inherit. "" means none — start from `add` alone.
    base: str = TECHNICAL
    add: tuple[str, ...] = ()
    drop: tuple[str, ...] = ()
    options: dict = field(default_factory=dict)
    exports: tuple[str, ...] = ("plain",)
    blurb: str = ""
    builtin: bool = False

    @property
    def name(self) -> str:
        return self.label or self.key.replace("-", " ").title()


BUILTIN: dict[str, DocType] = {
    TECHNICAL: DocType(
        TECHNICAL, "Technical document", base=TECHNICAL, builtin=True,
        exports=("numbered", "plain"),
        blurb="Manuals, specifications, procedures. Cross-references, "
              "terminology, units and step integrity."),
    FICTION: DocType(
        FICTION, "Fiction", base=FICTION, builtin=True,
        exports=("shunn", "plain"),
        blurb="Novels and stories. Pacing, dialogue, viewpoint, "
              "character presence."),
    LYRICS: DocType(
        LYRICS, "Lyrics or libretto", base=LYRICS, builtin=True,
        exports=("plain",),
        blurb="Words meant to be sung. Syllables per line, refrains that "
              "drifted, rhyme scheme."),
}


def parse(data, *, builtin: bool = False) -> dict[str, DocType]:
    """A doctypes document into profiles. Never raises on bad input."""
    if isinstance(data, dict):
        data = data.get("doctypes", data)
    rows = data if isinstance(data, list) else []
    out: dict[str, DocType] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip().lower()
        if not key or key in BUILTIN:
            continue
        base = str(raw.get("base") or TECHNICAL).strip().lower()
        if base and base not in DOC_TYPES:
            base = TECHNICAL
        out[key] = DocType(
            key=key, label=str(raw.get("label") or ""), base=base,
            add=tuple(raw.get("add") or ()),
            drop=tuple(raw.get("drop") or ()),
            options=dict(raw.get("options") or {}),
            exports=tuple(raw.get("exports") or ("plain",)),
            blurb=str(raw.get("blurb") or ""), builtin=builtin)
    return out


def load(store: Store | None = None, house_data=None) -> dict[str, DocType]:
    """Every type available here: the built-ins, the house's, the
    project's — later wins, and a project may not shadow a built-in."""
    out = dict(BUILTIN)
    out.update(parse(house_data))
    if store is not None:
        out.update(parse(store.read(DOCTYPES_FILE, None)))
    return out


def to_json(types) -> dict:
    """Profiles back into the shape `parse` reads. Round-trips.

    **BUILT-INS ARE NEVER WRITTEN.** `parse` refuses a key that shadows one
    and `load` puts them in first, so writing them out would produce a file
    of three entries that are ignored on the next read — a file that lies
    about what it controls.
    """
    out = []
    for profile in types:
        if profile.builtin or profile.key in BUILTIN:
            continue
        row = {"key": profile.key, "base": profile.base}
        if profile.label:
            row["label"] = profile.label
        for name in ("add", "drop", "exports"):
            value = tuple(getattr(profile, name) or ())
            if value and (name != "exports" or value != ("plain",)):
                row[name] = list(value)
        if profile.options:
            row["options"] = dict(profile.options)
        if profile.blurb:
            row["blurb"] = profile.blurb
        out.append(row)
    return {"doctypes": out}


def get(key: str, known: dict[str, DocType] | None = None) -> DocType:
    """The profile for a key, or a plain one standing for an unknown type.

    Never None. A project whose `doctypes.json` was deleted still opens,
    still measures, and falls back to the technical checks rather than to
    a traceback — the file is a convenience and the book is not.
    """
    table = known if known is not None else BUILTIN
    key = (key or TECHNICAL).strip().lower()
    if key in table:
        return table[key]
    return DocType(key=key, base=TECHNICAL,
                   blurb="Not a type this project declares; measured with "
                         "the technical checks.")
