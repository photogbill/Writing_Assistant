# SPDX-License-Identifier: Apache-2.0
"""ATK's Writing Workshop pages. Destination: `atk/ui/writing_panel.py`.

**This is the only file in the adapter that imports Qt**, which is what
keeps `writing_host.py` testable without a QApplication and the engine
testable without either.

Six pages, in the order the work happens — Manuscript, Codex, Continuity,
Craft, The Room, Versions — exposed as `PAGES` so `panels.py` can host them
in a `BasePanel` and get ATK's sub-tab bar and detach contract for free.

ATK's UI doctrine, honoured rather than reinvented:

* **Every hint is a `_WrapLabel` and every tall page scrolls.** A wrapped
  QLabel reports a one-line sizeHint, layouts believe it, and the rest of
  the text paints over the widgets below — and the text that gets covered
  is disproportionately the text explaining a failure.
* **The GUI thread never blocks.** Craft, continuity and every model call
  run on `atk.core.workers`. A forty-section sweep is seconds to minutes,
  and a frozen window during it reads as a crash.
* **A missing subsystem SAYS SO.** No model, no O.W.L. and no Piper voice
  are all supported states here; an empty page that could mean "off" or
  "broken" is the worst outcome this panel has.

And one rule from the engine that the UI has to carry rather than
describe: **nothing writes into the manuscript but the author.** The Room
produces suggestions on a diff surface; the Save button on the Manuscript
page is the only widget in this file that writes prose to disk.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from atk.core.workers import Worker, submit
from atk.ui.theme import MONO, PALETTE

# The engine. Absent on a fresh clone without the module, which is a state
# the panel has to survive rather than a bug — hence the guard.
try:
    from writing_workshop import Project
    from writing_workshop import codex as CX
    from writing_workshop import context as CT
    from writing_workshop import continuity as CN
    from writing_workshop import diff as DF
    from writing_workshop import export as EX
    from writing_workshop import fingerprint as FP
    from writing_workshop import readaloud as RA
    from writing_workshop import room as RM
    from writing_workshop.craft import REGISTRY as CRAFT_CHECKS
    from writing_workshop.craft import run as run_craft
    from writing_workshop.errors import WorkshopError
    from writing_workshop.types import ACCEPTED, FICTION, TECHNICAL
    from writing_workshop.versions import Versions
    ENGINE_ERROR = ""
except Exception as _exc:                             # noqa: BLE001
    ENGINE_ERROR = f"{type(_exc).__name__}: {_exc}"

SEVERITY_COLOUR = {"defect": PALETTE["error"], "warn": PALETTE["warn"],
                   "note": PALETTE["text_dim"]}
SEVERITY_MARK = {"defect": "!!", "warn": " !", "note": "  "}


class _WrapLabel(QLabel):
    """A word-wrapped label that reserves the height its text really needs.

    See `music_panel._WrapLabel` for the full account. In short: a wrapped
    QLabel reports a one-line sizeHint, layouts believe it, and the
    remaining lines are painted over the widgets below.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)

    def _fit(self) -> None:
        width = self.width()
        if width <= 1:
            return
        height = self.heightForWidth(width)
        if height > 0 and height != self.minimumHeight():
            self.setMinimumHeight(height)
            self.updateGeometry()

    def resizeEvent(self, event):                     # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._fit()

    def setText(self, text):                          # noqa: N802 (Qt API)
        super().setText(text)
        self._fit()


def _hint(text: str) -> _WrapLabel:
    label = _WrapLabel(text)
    label.setStyleSheet(f"color:{PALETTE['text_muted']};")
    return label


def _scroll(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(inner)
    return area


def _mono(widget):
    font = QFont()
    font.setFamilies([f.strip(' "') for f in MONO.split(",")])
    widget.setFont(font)
    return widget


# ===========================================================================
# shared state
# ===========================================================================


class WorkshopState(QObject):
    """One project, shared by all six pages.

    The manuscript is RE-READ from disk on every request rather than
    cached. The author is editing these files in another window — possibly
    in another program — and a cached manuscript is a workshop reporting on
    a book that no longer exists. Reading forty files is milliseconds;
    being wrong about them is the whole product.
    """

    changed = Signal()
    status = Signal(str)

    def __init__(self, ctx, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.project = None
        self.host = None
        self._codex = None
        self.fingerprint = None
        self.current_section_id = ""
        self._counter = None

    # -- opening ----------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.project is not None

    def open(self, path: str) -> str:
        from atk.core.writing_host import build_host
        try:
            self.close()
            self.project = Project.open(path)
            self.host = build_host(self.ctx,
                                   project_name=self.project.name)
            self.fingerprint = FP.load(self.project.fingerprint_file)
            self._counter = None
            self.current_section_id = ""
            self._remember(path)
        except Exception as exc:                      # noqa: BLE001
            self.project = None
            return f"{type(exc).__name__}: {exc}"
        self.changed.emit()
        return ""

    def close(self) -> None:
        if self._codex is not None:
            self._codex.close()
            self._codex = None

    def _remember(self, path: str) -> None:
        try:
            settings = getattr(self.ctx, "settings", None)
            if isinstance(settings, dict):
                block = settings.setdefault("writing", {})
                recent = [p for p in block.get("recent", [])
                          if p != path][:9]
                block["recent"] = [path, *recent]
                block["last"] = path
        except Exception:                             # noqa: BLE001
            pass

    def recent(self) -> list[str]:
        settings = getattr(self.ctx, "settings", None) or {}
        return list((settings.get("writing") or {}).get("recent") or [])

    # -- handles ----------------------------------------------------------

    def manuscript(self):
        return self.project.manuscript() if self.project else None

    @property
    def codex(self):
        if self._codex is None and self.project is not None:
            self._codex = CX.Codex(self.project.codex_db)
        return self._codex

    def budget(self):
        info = self.host.llm.info() if self.host else None
        return CT.from_model(info)

    def counter(self):
        """The loaded model's own tokeniser when it has one.

        Cached: the assembler prices the same outline and the same style
        card on every request in a session, and a tokeniser call per
        candidate per keystroke is how a good idea becomes a slow one.
        """
        if self._counter is None and self.host is not None:
            self._counter = CT.TokenCounter(self.host.llm)
        return self._counter

    def section(self, doc, sid: str = ""):
        sid = sid or self.current_section_id
        return doc.section(sid) if (doc and sid) else (
            doc.sections[0] if doc and doc.sections else None)


class _Page(QWidget):
    """Common wiring: a state handle, a status line, and one background
    task at a time."""

    def __init__(self, state: WorkshopState, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.status = _WrapLabel("")
        self._worker = None
        state.changed.connect(self.on_project_changed)

    def on_project_changed(self) -> None:
        return None

    def say(self, message: str) -> None:
        self.status.setText(message)

    def run_task(self, fn, done, *, label: str, kind: str = "inference",
                 **kwargs) -> None:
        """One task at a time per page, and every failure lands on screen.

        A background job whose exception only reaches the log is a button
        that does nothing — the exact complaint that took a day out of
        ATK's TTS work.
        """
        if self._worker is not None:
            self.say("Still working on the last one.")
            return
        self.say(label + "…")
        worker = Worker(fn, description=label, kind=kind, **kwargs)
        worker.signals.result.connect(done)
        worker.signals.progress.connect(self.say)
        worker.signals.error.connect(
            lambda text: self.say(text.strip().splitlines()[-1]
                                  if text.strip() else "failed"))
        worker.signals.finished.connect(self._clear_worker)
        self._worker = worker
        submit(worker)

    def _clear_worker(self) -> None:
        self._worker = None


# ===========================================================================
# 1. Manuscript
# ===========================================================================


class ManuscriptPage(_Page):
    """The editor, the derived structure, and the budget meter.

    The tree is built from the headings in the files and is never stored.
    Reorganise the manuscript in any editor and the tree follows; there is
    nothing to get out of sync and nothing of ours inside the author's
    prose.
    """

    LABEL = "Manuscript"

    def __init__(self, state: WorkshopState, parent=None) -> None:
        super().__init__(state, parent)
        root = QVBoxLayout(self)
        root.addWidget(self._build_open_row())

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Section", "Words"])
        self.tree.setColumnWidth(0, 240)
        self.tree.itemSelectionChanged.connect(self._select)
        lay.addWidget(self.tree)
        self.doc_stats = _hint("")
        lay.addWidget(self.doc_stats)
        split.addWidget(left)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        self.editor = _mono(QPlainTextEdit())
        self.editor.setPlaceholderText(
            "Open a project folder of .md files. The workshop never moves "
            "your manuscript into a database — these are the files on disk.")
        self.editor.textChanged.connect(self._dirty)
        rlay.addWidget(self.editor, 1)

        row = QHBoxLayout()
        self.save_btn = QPushButton("Save file")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.clicked.connect(lambda: self._load_current(True))
        self.words_label = QLabel("")
        row.addWidget(self.save_btn)
        row.addWidget(self.revert_btn)
        row.addStretch(1)
        row.addWidget(self.words_label)
        rlay.addLayout(row)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 1)

        self.meter = _WrapLabel("")
        self.meter.setStyleSheet(f"color:{PALETTE['text_dim']};")
        root.addWidget(self.meter)
        root.addWidget(self.status)
        self._file = ""

    # -- opening ----------------------------------------------------------

    def _build_open_row(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        self.recent = QComboBox()
        self.recent.setEditable(True)
        self.recent.setMinimumWidth(340)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        open_btn = QPushButton("Open project")
        open_btn.clicked.connect(self._open)
        self.type_box = QComboBox()
        self.type_box.addItems(["Technical document", "Fiction"])
        self.type_box.currentIndexChanged.connect(self._set_type)
        row.addWidget(QLabel("Project folder"))
        row.addWidget(self.recent, 1)
        row.addWidget(browse)
        row.addWidget(open_btn)
        row.addWidget(QLabel("Type"))
        row.addWidget(self.type_box)
        return box

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Project folder")
        if path:
            self.recent.setEditText(path)
            self._open()

    def _open(self) -> None:
        path = self.recent.currentText().strip()
        if not path:
            self.say("Pick a folder of .md files first.")
            return
        problem = self.state.open(path)
        self.say(problem or f"Opened {Path(path).name}.")

    def _set_type(self) -> None:
        project = self.state.project
        if project is None:
            return
        project.document_type = (FICTION if self.type_box.currentIndex()
                                 else TECHNICAL)
        project.save()
        self.state.changed.emit()

    # -- the tree ---------------------------------------------------------

    def on_project_changed(self) -> None:
        project = self.state.project
        self.recent.clear()
        self.recent.addItems(self.state.recent())
        if project is None:
            return
        self.recent.setEditText(str(project.root))
        self.type_box.blockSignals(True)
        self.type_box.setCurrentIndex(1 if project.is_fiction else 0)
        self.type_box.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        doc = self.state.manuscript()
        self.tree.clear()
        if doc is None:
            return
        items: dict[str, QTreeWidgetItem] = {}
        for sec in doc.sections:
            parent = items.get(sec.parent_id)
            label = doc.label(sec)
            item = QTreeWidgetItem(parent or self.tree,
                                   [label, f"{sec.words:,}"])
            item.setData(0, Qt.UserRole, sec.id)
            items[sec.id] = item
        self.tree.expandToDepth(1)
        self.doc_stats.setText(
            f"{len(doc.files)} files · {len(doc.sections)} sections · "
            f"{doc.words:,} words")
        self._show_meter(doc)
        if doc.sections and not self.state.current_section_id:
            self.state.current_section_id = doc.sections[0].id
            self._load_current(True)

    def _show_meter(self, doc) -> None:
        project = self.state.project
        if doc is None or project is None:
            return
        budget = self.state.budget()
        try:
            section = self.state.section(doc)
            assembly = CT.build(doc, section, request="(a draft request)",
                                budget=budget, counter=self.state.counter(),
                                style_card=project.style_card,
                                document_rules=project.document_rules)
            lines = CT.meter(budget, assembly)
        except WorkshopError as exc:
            lines = [*budget.meter_lines(), str(exc)]
        self.meter.setText("\n".join(lines))

    def _select(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        self.state.current_section_id = items[0].data(0, Qt.UserRole) or ""
        self._load_current(True)

    def _load_current(self, force: bool = False) -> None:
        doc = self.state.manuscript()
        section = self.state.section(doc)
        if doc is None or section is None:
            return
        src = doc.file(section.path)
        if src is None:
            return
        self._file = str(src.path)
        self.editor.blockSignals(True)
        self.editor.setPlainText(src.text)
        self.editor.blockSignals(False)
        self.save_btn.setEnabled(False)
        self.words_label.setText(f"{src.rel} · {section.words:,} words in "
                                 f"this section")

    def _dirty(self) -> None:
        self.save_btn.setEnabled(bool(self._file))

    def _save(self) -> None:
        """The ONLY widget in this workspace that writes prose to a file."""
        if not self._file:
            return
        try:
            Path(self._file).write_text(self.editor.toPlainText(),
                                        encoding="utf-8")
        except OSError as exc:
            self.say(f"Could not save: {exc}")
            return
        self.save_btn.setEnabled(False)
        self.say(f"Saved {Path(self._file).name}.")
        self.refresh()


# ===========================================================================
# 2. Craft
# ===========================================================================


class CraftPage(_Page):
    """The measurements. No model, and no ability to invent a finding."""

    LABEL = "Craft"

    def __init__(self, state: WorkshopState, parent=None) -> None:
        super().__init__(state, parent)
        root = QVBoxLayout(self)
        root.addWidget(_hint(
            "Arithmetic over the text: fast, offline, and incapable of "
            "inventing a finding. Nothing here needs a model loaded."))
        row = QHBoxLayout()
        self.run_btn = QPushButton("Measure the manuscript")
        self.run_btn.clicked.connect(self._run)
        self.only_box = QComboBox()
        self.only_box.addItem("every check", "")
        self.problems_only = QCheckBox("Problems only")
        self.problems_only.setChecked(True)
        self.problems_only.stateChanged.connect(self._render)
        row.addWidget(self.run_btn)
        row.addWidget(self.only_box, 1)
        row.addWidget(self.problems_only)
        root.addLayout(row)

        split = QSplitter(Qt.Horizontal)
        self.findings = QTreeWidget()
        self.findings.setHeaderLabels(["Finding", "Where"])
        self.findings.setColumnWidth(0, 460)
        self.findings.itemSelectionChanged.connect(self._show_detail)
        split.addWidget(self.findings)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        root.addWidget(split, 1)
        self.metrics = _mono(QTextEdit())
        self.metrics.setReadOnly(True)
        self.metrics.setMaximumHeight(150)
        root.addWidget(self.metrics)
        root.addWidget(self.status)
        self._report = None

    def on_project_changed(self) -> None:
        project = self.state.project
        self.only_box.clear()
        self.only_box.addItem("every check", "")
        if project is None:
            return
        for name, reg in sorted(CRAFT_CHECKS.items()):
            if project.document_type in reg.applies:
                self.only_box.addItem(reg.label, name)

    def _run(self) -> None:
        project = self.state.project
        if project is None:
            self.say("Open a project first.")
            return
        doc = self.state.manuscript()
        only = self.only_box.currentData() or ""

        def job():
            return run_craft(doc, project.document_type,
                             only=[only] if only else None,
                             cast=project.cast, terms=project.terms,
                             glossary_titles=project.glossary_titles)

        self.run_task(job, self._done, label="Measuring", kind="io")

    def _done(self, report) -> None:
        self._report = report
        self._render()
        problems = len(report.problems())
        self.say(f"{len(report.ran)} checks ran · {problems} to look at"
                 + (f" · skipped {len(report.skipped)}"
                    if report.skipped else ""))

    def _render(self) -> None:
        self.findings.clear()
        report = self._report
        if report is None:
            return
        groups: dict[str, QTreeWidgetItem] = {}
        doc = self.state.manuscript()
        wanted = (report.problems() if self.problems_only.isChecked()
                  else report.findings)
        for finding in sorted(wanted, key=lambda f: (
                {"defect": 0, "warn": 1}.get(f.severity, 2), f.check)):
            head = groups.get(finding.check)
            if head is None:
                label = CRAFT_CHECKS[finding.check].label \
                    if finding.check in CRAFT_CHECKS else finding.check
                head = QTreeWidgetItem(self.findings, [label, ""])
                groups[finding.check] = head
            section = doc.section(finding.section_id) if doc else None
            where = doc.label(section) if (doc and section) else ""
            item = QTreeWidgetItem(
                head, [f"{SEVERITY_MARK[finding.severity]} {finding.title}",
                       where])
            item.setForeground(0, QColor(SEVERITY_COLOUR[finding.severity]))
            item.setData(0, Qt.UserRole, finding)
        self.findings.expandAll()
        self.metrics.setPlainText(_pretty(report.metrics))

    def _show_detail(self) -> None:
        items = self.findings.selectedItems()
        finding = items[0].data(0, Qt.UserRole) if items else None
        if finding is None:
            self.detail.clear()
            return
        parts = [f"<b>{finding.title}</b>", finding.detail or ""]
        for quote in finding.evidence:
            parts.append(f"<blockquote>{quote}</blockquote>")
        if finding.data:
            parts.append(f"<pre>{_pretty(finding.data)}</pre>")
        self.detail.setHtml("<br>".join(p for p in parts if p))


def _pretty(data) -> str:
    import json
    try:
        return json.dumps(data, indent=2, default=str)[:6000]
    except Exception:                                 # noqa: BLE001
        return str(data)[:6000]


# ===========================================================================
# 3. Codex
# ===========================================================================


class CodexPage(_Page):
    """Typed claims with provenance. Every one arrives PROPOSED.

    The two buttons are deliberately different colours of operation.
    *Read what can be read* needs no model and produces claims that are
    arithmetic — a named quantity with a value, a weekday, a stated
    relationship. *Ask the model* produces readings, and they land in
    exactly the same proposed state, so nothing enters the Codex without
    the author having said yes to it.
    """

    LABEL = "Codex"

    def __init__(self, state: WorkshopState, parent=None) -> None:
        super().__init__(state, parent)
        root = QVBoxLayout(self)
        root.addWidget(_hint(
            "A story bible that is also an evidence ledger. Nothing here is "
            "a fact until you accept it — including everything a model "
            "read."))
        row = QHBoxLayout()
        self.read_btn = QPushButton("Read what can be read")
        self.read_btn.clicked.connect(self._deterministic)
        self.ask_btn = QPushButton("Ask the model to propose more")
        self.ask_btn.clicked.connect(self._propose)
        self.filter_box = QComboBox()
        self.filter_box.addItems(["proposed", "accepted", "superseded",
                                  "rejected", "everything"])
        self.filter_box.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.read_btn)
        row.addWidget(self.ask_btn)
        row.addStretch(1)
        row.addWidget(QLabel("Show"))
        row.addWidget(self.filter_box)
        root.addLayout(row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "State", "Kind", "Subject", "Says", "Where"])
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        for label, slot in (("Accept", self._accept),
                            ("Reject", self._reject),
                            ("Supersede…", self._supersede),
                            ("Reconsider", self._reconsider),
                            ("Mirror accepted into O.W.L.", self._mirror)):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            actions.addWidget(btn)
        actions.addStretch(1)
        self.counts = QLabel("")
        actions.addWidget(self.counts)
        root.addLayout(actions)

        self.dependents = QTextEdit()
        self.dependents.setReadOnly(True)
        self.dependents.setMaximumHeight(220)
        root.addWidget(self.dependents)
        root.addWidget(self.status)

    def on_project_changed(self) -> None:
        self.refresh()

    # -- reading ----------------------------------------------------------

    def refresh(self) -> None:
        self.table.setRowCount(0)
        if not self.state.is_open:
            return
        store = self.state.codex
        wanted = self.filter_box.currentText()
        rows = store.all(state=None if wanted == "everything" else wanted)
        self.table.setRowCount(len(rows))
        for i, claim in enumerate(rows):
            cells = [str(claim.id), claim.state, claim.kind, claim.subject,
                     f"{claim.predicate} = {claim.value}", claim.source_ref]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.UserRole, claim.id)
                if claim.state == "superseded":
                    item.setForeground(QColor(PALETTE["text_muted"]))
                elif claim.origin == "extracted":
                    item.setForeground(QColor(PALETTE["violet"]))
                self.table.setItem(i, col, item)
        self.counts.setText(" · ".join(f"{k} {v}" for k, v in
                                       store.counts().items()))

    def _selected_id(self) -> int:
        rows = self.table.selectionModel().selectedRows() \
            if self.table.selectionModel() else []
        if not rows:
            return 0
        item = self.table.item(rows[0].row(), 0)
        return int(item.data(Qt.UserRole)) if item else 0

    # -- proposing --------------------------------------------------------

    def _deterministic(self) -> None:
        if not self.state.is_open:
            self.say("Open a project first.")
            return
        project = self.state.project
        doc = self.state.manuscript()
        store = self.state.codex

        def job():
            claims = CX.deterministic(doc, terms=project.terms,
                                      subjects=project.cast or None)
            return len(store.add_many(claims))

        self.run_task(job, self._proposed, label="Reading claims",
                      kind="io")

    def _propose(self) -> None:
        if not self.state.is_open:
            self.say("Open a project first.")
            return
        doc = self.state.manuscript()
        section = self.state.section(doc)
        if section is None:
            self.say("Select a section on the Manuscript page first.")
            return
        host = self.state.host
        store = self.state.codex
        project = self.state.project

        def job(progress=None):
            say = progress or (lambda _m: None)
            say(f"Reading {doc.label(section)}…")
            claims = CX.propose(
                host, doc, section,
                context=project.style_card[:400])
            return len(store.add_many(claims))

        self.run_task(job, self._proposed, inject_progress=True,
                      label="Asking the model")

    def _proposed(self, n: int) -> None:
        self.refresh()
        self.say(f"{n} claims proposed. Nothing is a fact until you accept "
                 f"it.")

    # -- deciding ---------------------------------------------------------

    def _accept(self) -> None:
        claim_id = self._selected_id()
        if not claim_id:
            self.say("Select a claim.")
            return
        self.state.codex.accept(claim_id)
        self.refresh()
        self.say(f"Claim #{claim_id} accepted.")

    def _reject(self) -> None:
        claim_id = self._selected_id()
        if not claim_id:
            self.say("Select a claim.")
            return
        self.state.codex.reject(claim_id)
        self.refresh()

    def _supersede(self) -> None:
        """The fact changed. The old claim is kept, marked and linked —
        which is the entire basis for Reconsider."""
        store = self.state.codex
        claim_id = self._selected_id()
        old = store.get(claim_id) if claim_id else None
        if old is None:
            self.say("Select the claim whose fact has changed.")
            return
        # QInputDialog rather than a QMessageBox with a field bolted into
        # its grid: `box.layout()` is typed as QLayout in the bindings, so
        # the three-argument addWidget raises TypeError at the moment the
        # operator presses the button — a dead button with a traceback
        # behind it, which is the failure mode this codebase keeps paying
        # for.
        value, ok = QInputDialog.getText(
            self, "Supersede",
            f"{old.subject}: {old.predicate} is currently “{old.value}”.\n"
            f"The old claim is kept and linked, so Reconsider can find "
            f"what depended on it.\n\nNew value:", text=old.value)
        value = (value or "").strip()
        if not ok or not value or value == old.value:
            return
        new = CX.make(old.subject, old.predicate, value, kind=old.kind,
                      origin="author")
        added = store.supersede(claim_id, new)
        self.refresh()
        self.say(f"#{claim_id} superseded by #{added.id}. Press Reconsider "
                 f"to see what still depends on “{old.value}”.")
        self._show_dependents(old, added)

    def _reconsider(self) -> None:
        """*What did I write that depended on the old fact?*"""
        store = self.state.codex
        claim_id = self._selected_id()
        claim = store.get(claim_id) if claim_id else None
        if claim is None:
            self.say("Select a claim.")
            return
        newer = (store.get(claim.superseded_by)
                 if claim.superseded_by else None)
        self._show_dependents(claim, newer)

    def _show_dependents(self, claim, newer) -> None:
        doc = self.state.manuscript()
        found = CX.for_claim(doc, claim, newer)
        if not found:
            self.dependents.setPlainText(
                f"Nothing else in the manuscript mentions "
                f"{claim.subject}.")
            return
        head = (f"{claim.subject}: “{claim.value}”"
                + (f" → “{newer.value}”" if newer else "")
                + f" — {len(found)} passages to look at")
        lines = [f"<b>{head}</b>"]
        for dep in found:
            colour = (PALETTE["error"] if dep.certain
                      else PALETTE["text_dim"])
            lines.append(
                f"<p style='color:{colour}'><b>{dep.section_label}</b> — "
                f"{dep.why}<br>{dep.quote}</p>")
        self.dependents.setHtml("".join(lines))
        self.say(f"{len(found)} passages may depend on the old value.")

    def _mirror(self) -> None:
        host = self.state.host
        store = self.state.codex
        if host is None or not host.ledger.available():
            self.say("O.W.L. is off or not installed — the Codex works as a "
                     "plain list without it.")
            return
        sent = store.mirror(host.ledger)
        self.say(f"{sent} accepted claims mirrored into O.W.L. Proposed "
                 f"claims are never mirrored.")


# ===========================================================================
# 4. Continuity
# ===========================================================================


class ContinuityPage(_Page):
    """Contradictions, dropped threads, names and the timeline.

    Runs with no model. The deterministic findings are stated flatly; the
    candidates quote both passages and let the author adjudicate.
    """

    LABEL = "Continuity"

    def __init__(self, state: WorkshopState, parent=None) -> None:
        super().__init__(state, parent)
        root = QVBoxLayout(self)
        root.addWidget(_hint(
            "A whole-document pass, section by section — the window stops "
            "being a ceiling on document size. No model required."))
        row = QHBoxLayout()
        self.run_btn = QPushButton("Sweep the manuscript")
        self.run_btn.clicked.connect(self._run)
        self.use_codex = QCheckBox("Include accepted Codex claims")
        self.use_codex.setChecked(True)
        row.addWidget(self.run_btn)
        row.addWidget(self.use_codex)
        row.addStretch(1)
        root.addLayout(row)

        split = QSplitter(Qt.Horizontal)
        self.findings = QListWidget()
        self.findings.currentRowChanged.connect(self._show)
        split.addWidget(self.findings)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 2)
        root.addWidget(split, 1)
        self.timeline = _mono(QTextEdit())
        self.timeline.setReadOnly(True)
        self.timeline.setMaximumHeight(150)
        root.addWidget(self.timeline)
        root.addWidget(self.status)
        self._sweep = None

    def _run(self) -> None:
        if not self.state.is_open:
            self.say("Open a project first.")
            return
        project = self.state.project
        doc = self.state.manuscript()
        store = self.state.codex
        include = self.use_codex.isChecked()

        def job(progress=None, should_cancel=None):
            claims = CX.deterministic(doc, terms=project.terms,
                                      subjects=project.cast or None)
            if include:
                claims.extend(store.all(state=ACCEPTED))
            events = _ProgressEvents(progress)
            return CN.sweep(doc, claims, cast=project.cast,
                            terms=project.terms, events=events,
                            cancel=_CancelAdapter(should_cancel))

        self.run_task(job, self._done, inject_progress=True,
                      inject_cancel=True, label="Sweeping", kind="io")

    def _done(self, sweep) -> None:
        self._sweep = sweep
        self.findings.clear()
        for finding in sweep.findings:
            item = QListWidgetItem(
                f"{SEVERITY_MARK[finding.severity]} {finding.title}")
            item.setForeground(QColor(SEVERITY_COLOUR[finding.severity]))
            item.setData(Qt.UserRole, finding)
            self.findings.addItem(item)
        lines = [f"{m.order:>3}  {m.section_label:<28} {m.kind:<9} {m.text}"
                 for m in sweep.moments[:200]]
        self.timeline.setPlainText("\n".join(lines) or
                                   "No time markers found.")
        self.say(_pretty(sweep.metrics).replace("\n", " ").replace('"', ""))

    def _show(self, row: int) -> None:
        item = self.findings.item(row) if row >= 0 else None
        finding = item.data(Qt.UserRole) if item else None
        if finding is None:
            self.detail.clear()
            return
        parts = [f"<b>{finding.title}</b>", finding.detail or ""]
        for quote in finding.evidence:
            parts.append(f"<blockquote>{quote}</blockquote>")
        self.detail.setHtml("<br>".join(p for p in parts if p))


class _ProgressEvents:
    """The engine's Events port, wired to a Worker's progress signal."""

    def __init__(self, progress) -> None:
        self.progress = progress or (lambda _m: None)

    def emit(self, kind: str, message: str, **data) -> None:
        if data.get("n"):
            self.progress(f"{message} ({data.get('i', 0)}/{data['n']})")
        else:
            self.progress(message)


class _CancelAdapter:
    """`should_cancel()` from a Worker, as the engine's CancelToken."""

    def __init__(self, should_cancel) -> None:
        self._fn = should_cancel

    def is_set(self) -> bool:
        return bool(self._fn and self._fn())


# ===========================================================================
# 5. The Room
# ===========================================================================


class RoomPage(_Page):
    """Critics and rewrites, non-destructively.

    Two properties of this page are structural rather than cosmetic:

    * A rewriting persona's output lands in a DIFF, sentence by sentence,
      with Accept per hunk. There is no "apply all" and no path from a
      model's text into a file that does not go through the author.
    * Every suggestion carries its drift score, attached and quiet — the
      defence against the slow convergence on the model's voice that
      nothing else in this category admits to.
    """

    LABEL = "The Room"

    def __init__(self, state: WorkshopState, parent=None) -> None:
        super().__init__(state, parent)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.persona_box = QComboBox()
        self.persona_box.currentIndexChanged.connect(self._describe)
        self.ask_btn = QPushButton("Ask")
        self.ask_btn.clicked.connect(self._ask)
        self.fit_btn = QPushButton("Fit my style baseline")
        self.fit_btn.clicked.connect(self._fit)
        row.addWidget(QLabel("Reader"))
        row.addWidget(self.persona_box, 1)
        row.addWidget(self.ask_btn)
        row.addWidget(self.fit_btn)
        root.addLayout(row)
        self.blurb = _hint("")
        root.addWidget(self.blurb)

        split = QSplitter(Qt.Vertical)
        top = QWidget()
        tlay = QVBoxLayout(top)
        tlay.setContentsMargins(0, 0, 0, 0)
        tlay.addWidget(QLabel("Passage"))
        self.passage = _mono(QPlainTextEdit())
        tlay.addWidget(self.passage)
        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("Notes / beats"))
        self.notes = QLineEdit()
        notes_row.addWidget(self.notes, 1)
        load = QPushButton("Load selected section")
        load.clicked.connect(self._load_section)
        notes_row.addWidget(load)
        tlay.addLayout(notes_row)
        split.addWidget(top)

        bottom = QWidget()
        blay = QVBoxLayout(bottom)
        blay.setContentsMargins(0, 0, 0, 0)
        self.drift = _WrapLabel("")
        blay.addWidget(self.drift)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        blay.addWidget(self.result, 1)
        hunk_row = QHBoxLayout()
        self.hunks = QListWidget()
        self.hunks.setSelectionMode(QAbstractItemView.MultiSelection)
        hunk_row.addWidget(self.hunks, 1)
        buttons = QVBoxLayout()
        self.apply_btn = QPushButton("Take the ticked changes")
        self.apply_btn.clicked.connect(self._apply)
        self.speak_btn = QPushButton("Read the passage aloud")
        self.speak_btn.clicked.connect(self._speak)
        buttons.addWidget(self.apply_btn)
        buttons.addWidget(self.speak_btn)
        buttons.addStretch(1)
        hunk_row.addLayout(buttons)
        blay.addLayout(hunk_row, 1)
        split.addWidget(bottom)
        root.addWidget(split, 1)
        root.addWidget(self.status)
        self._suggestion = None
        self._hunks: list = []

    def on_project_changed(self) -> None:
        project = self.state.project
        self.persona_box.clear()
        if project is None:
            return
        for persona in RM.for_document(project.document_type):
            self.persona_box.addItem(persona.label, persona.key)
        self._describe()
        fp = self.state.fingerprint
        if fp is None:
            self.drift.setText(
                "No style baseline yet — press “Fit my style baseline” "
                "once you have prose you are happy with.")
        else:
            thin = "" if fp.trustworthy else (
                " — thin, so treat the scores as indicative")
            self.drift.setText(
                f"Style baseline: {fp.n_words:,} words{thin}.")

    def _describe(self) -> None:
        project = self.state.project
        if project is None:
            return
        persona = RM.get(self.persona_box.currentData() or "",
                         project.document_type)
        self.blurb.setText(persona.blurb if persona else "")

    def _load_section(self) -> None:
        doc = self.state.manuscript()
        section = self.state.section(doc)
        if section is None:
            self.say("Select a section on the Manuscript page.")
            return
        self.passage.setPlainText(doc.prose(section).strip())
        self.say(f"Loaded {doc.label(section)}.")

    # -- fitting ----------------------------------------------------------

    def _fit(self) -> None:
        """Fit on writing the author has ALREADY ACCEPTED.

        Fitting on a draft that already contains the model's rewrites bakes
        the drift into the baseline, and the tool then reports that
        everything matches beautifully — the exact failure it exists to
        prevent. Nothing here can enforce that; the button says it.
        """
        if not self.state.is_open:
            self.say("Open a project first.")
            return
        doc = self.state.manuscript()
        project = self.state.project

        def job():
            fp = FP.from_manuscript(doc)
            FP.save(fp, project.fingerprint_file)
            return fp

        self.run_task(job, self._fitted, label="Fitting your baseline",
                      kind="io")

    def _fitted(self, fp) -> None:
        self.state.fingerprint = fp
        self.drift.setText(
            f"Style baseline fitted on {fp.n_words:,} words"
            + ("." if fp.trustworthy else " — thin; treat scores as "
                                          "indicative rather than firm."))

    # -- asking -----------------------------------------------------------

    def _ask(self) -> None:
        project = self.state.project
        if project is None:
            self.say("Open a project first.")
            return
        persona = RM.get(self.persona_box.currentData() or "",
                         project.document_type)
        text = self.passage.toPlainText().strip()
        if persona is None or not text:
            self.say("Load a passage first.")
            return
        doc = self.state.manuscript()
        section = self.state.section(doc)
        store = self.state.codex
        host = self.state.host
        fingerprint = self.state.fingerprint
        notes = self.notes.text()
        budget = self.state.budget()
        counter = self.state.counter()

        def job(progress=None):
            say = progress or (lambda _m: None)
            claims = store.governing(section.id if section else "",
                                     subjects=project.cast) \
                if persona.wants_claims else []
            assembly = CT.build(doc, section, request="",
                                style_card=project.style_card,
                                document_rules=project.document_rules,
                                claims=claims, budget=budget,
                                counter=counter, include_prior=False)
            say(assembly.manifest())
            room = RM.Room(host, fingerprint)
            if persona.returns_text:
                return ("text", room.rewrite(
                    persona, text, context=assembly.text, claims=claims,
                    notes=notes, section=section))
            return ("notes", room.critique(
                persona, text, context=assembly.text, claims=claims,
                notes=notes))

        self.run_task(job, self._answered, inject_progress=True,
                      label=f"Asking {persona.label}")

    def _answered(self, payload) -> None:
        kind, result = payload
        self.hunks.clear()
        self._hunks = []
        if kind == "notes":
            self._suggestion = None
            if result.clean:
                self.result.setPlainText("Nothing to report.")
            else:
                self.result.setHtml("<br>".join(
                    f"• {note}" for note in result.notes))
            self.drift.setText("A reading, not a rewrite — there is nothing "
                               "here to apply.")
            return
        self._suggestion = result
        self._hunks = DF.diff(self.passage.toPlainText(), result.text)
        for hunk in self._hunks:
            if not hunk.changed:
                continue
            item = QListWidgetItem(
                DF.render([hunk]).replace("\n", "  ⏎  ")[:220])
            item.setData(Qt.UserRole, hunk.id)
            self.hunks.addItem(item)
        self.result.setPlainText(result.text)
        score = result.drift_score
        colour = (PALETTE["warn"] if score >= 1.5 else PALETTE["text_dim"])
        self.drift.setStyleSheet(f"color:{colour};")
        self.drift.setText(
            (f"drift {score} — " if score else "")
            + (result.note or "No style baseline fitted, so this suggestion "
                              "has not been scored against your voice."))
        self.say(f"{len(self.hunks)} sentence changes. Tick the ones you "
                 f"want; nothing is applied until you do.")

    def _apply(self) -> None:
        """Puts the accepted sentences in the editable box — never on disk.

        The author still saves the file themselves on the Manuscript page.
        Two deliberate keystrokes between a model's sentence and the book.
        """
        if not self._hunks:
            return
        taken = {self.hunks.item(i).data(Qt.UserRole)
                 for i in range(self.hunks.count())
                 if self.hunks.item(i).isSelected()}
        if not taken:
            self.say("Tick at least one change.")
            return
        merged = DF.apply(self.passage.toPlainText(), self._hunks, taken)
        self.passage.setPlainText(merged)
        self.say(f"{len(taken)} changes taken into the passage box. Copy "
                 f"them into the manuscript on the Manuscript page — "
                 f"nothing writes to your files but you.")

    def _speak(self) -> None:
        host = self.state.host
        text = self.passage.toPlainText().strip()
        if host is None or not text:
            return
        if not host.speech.available():
            self.say("No Piper voice installed — run fetch_models --piper.")
            return
        line = RA.Line(text=text[:2000], span=None)

        def job():
            return RA.speak(host, line)

        self.run_task(job, lambda path: self.say(
            f"Spoken: {path}" if path else "Speech failed — see the log."),
            label="Speaking", kind="io")


# ===========================================================================
# 6. Versions
# ===========================================================================


class VersionsPage(_Page):
    """Named drafts, sentence-level diffs, and export.

    Named in the author's own words — "the version where she leaves" — and
    visible as folders of plain files. Hidden version control is a
    data-loss trap: when it goes wrong the author has no model of what
    happened and no vocabulary to ask about it.
    """

    LABEL = "Versions"

    def __init__(self, state: WorkshopState, parent=None) -> None:
        super().__init__(state, parent)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText(
            "name this draft in your own words — “before the legal pass”")
        save = QPushButton("Save a version")
        save.clicked.connect(self._save)
        row.addWidget(self.name, 1)
        row.addWidget(save)
        root.addLayout(row)

        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._diff)
        split.addWidget(self.list)
        self.diff_view = _mono(QTextEdit())
        self.diff_view.setReadOnly(True)
        split.addWidget(self.diff_view)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 1)

        actions = QHBoxLayout()
        restore = QPushButton("Restore this version…")
        restore.clicked.connect(self._restore)
        actions.addWidget(restore)
        actions.addStretch(1)
        actions.addWidget(QLabel("Export"))
        self.export_box = QComboBox()
        self.export_box.addItem("Plain markdown", "plain")
        self.export_box.addItem("Numbered sections + contents", "numbered")
        self.export_box.addItem("Shunn manuscript format", "shunn")
        actions.addWidget(self.export_box)
        export = QPushButton("Export…")
        export.clicked.connect(self._export)
        actions.addWidget(export)
        root.addLayout(actions)
        root.addWidget(self.status)

    def on_project_changed(self) -> None:
        self.refresh()

    def _versions(self):
        return Versions(self.state.project) if self.state.is_open else None

    def refresh(self) -> None:
        self.list.clear()
        versions = self._versions()
        if versions is None:
            return
        for info in reversed(versions.list()):
            item = QListWidgetItem(
                f"{info.name}\n{info.created} · {info.words:,} words")
            item.setData(Qt.UserRole, info.id)
            self.list.addItem(item)

    def _save(self) -> None:
        versions = self._versions()
        if versions is None:
            self.say("Open a project first.")
            return
        name = self.name.text().strip()
        if not name:
            self.say("Give the version a name you will recognise later.")
            return
        info = versions.save(name)
        self.name.clear()
        self.refresh()
        self.say(f"Saved “{info.name}” — {info.files} files, "
                 f"{info.words:,} words.")

    def _diff(self, row: int) -> None:
        versions = self._versions()
        item = self.list.item(row) if row >= 0 else None
        if versions is None or item is None:
            return
        version_id = item.data(Qt.UserRole)
        blocks = versions.diff(version_id)
        if not blocks:
            self.diff_view.setPlainText(
                "Identical to the manuscript on disk.")
            return
        parts = []
        for rel, hunks in blocks.items():
            parts.append(f"--- {rel}")
            parts.append(DF.render(hunks))
        self.diff_view.setPlainText("\n".join(parts))

    def _restore(self) -> None:
        versions = self._versions()
        item = self.list.currentItem()
        if versions is None or item is None:
            return
        version_id = item.data(Qt.UserRole)
        info = versions.get(version_id)
        if info is None:
            self.say("That version is no longer on disk.")
            return
        answer = QMessageBox.question(
            self, "Restore",
            f"Restore “{info.name}”?\n\nThis overwrites the manuscript "
            f"files on disk. A snapshot of what is there now is taken "
            f"first, automatically, so this is reversible.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        versions.restore(version_id, confirm=True)
        self.refresh()
        self.state.changed.emit()
        self.say(f"Restored “{info.name}”. The previous state was saved "
                 f"as its own version first.")

    def _export(self) -> None:
        project = self.state.project
        if project is None:
            return
        doc = self.state.manuscript()
        fmt = self.export_box.currentData()
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export", str(project.root / f"{project.name}.md"),
            "Markdown (*.md)")
        if not path:
            return
        if fmt == "shunn":
            spec = EX.shunn_spec(doc, title=project.name)
            text = EX.shunn_markdown(spec)
        elif fmt == "numbered":
            text = EX.numbered_markdown(doc, title=project.name)
        else:
            text = EX.plain_markdown(doc)
        Path(path).write_text(text, encoding="utf-8")
        self.say(f"Wrote {Path(path).name}. For .docx, ATK's report "
                 f"exporter reads this markdown as-is.")


# ===========================================================================
# what panels.py hosts
# ===========================================================================

#: Order matters — it is the order the work happens in, and it is also the
#: order of trust: measurement before the model speaks.
PAGES = (ManuscriptPage, CodexPage, ContinuityPage, CraftPage, RoomPage,
         VersionsPage)

SUB_TABS = [page.LABEL for page in PAGES]


def build_pages(ctx) -> tuple[WorkshopState, list[QWidget]]:
    """Build the six pages against one shared state. Used by `panels.py`."""
    state = WorkshopState(ctx)
    pages = [page(state) for page in PAGES]
    last = getattr(ctx, "settings", {}) or {}
    remembered = (last.get("writing") or {}).get("last", "")
    if remembered and Path(remembered).exists():
        state.open(remembered)
    return state, pages
