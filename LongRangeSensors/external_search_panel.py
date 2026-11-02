"""External Search results panel — GitHub / Brave API → Capture / Clone via UIEG.

Opened from right-dock Run Search. Does not write ship_computer.db.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from LongRangeSensors.uieg_crawler import crawl_url_to_disk
from LongRangeSensors.uieg_paths import (
    default_crawl_folder,
    default_repo_folder,
    ensure_capture_folder,
    merge_uieg_config,
)
from LongRangeSensors.uieg_repo_fetch import fetch_repo_to_capture, parse_github_repo
from LongRangeSensors.web_search_clients import run_external_search


def _panel_stylesheet(theme: dict) -> str:
    return f"""
        QWidget {{
            background-color: {theme['bg']};
            color: {theme['fg']};
        }}
        QLabel {{ color: {theme['fg']}; }}
        QTextEdit, QTableWidget {{
            background-color: {theme['panel_bg']};
            color: {theme['fg']};
            border: 1px solid {theme['border']};
        }}
        QHeaderView::section {{
            background-color: {theme['accent']};
            color: {theme['fg']};
            padding: 4px;
            border: none;
        }}
        QTableWidget::item:selected {{
            background-color: {theme['accent_hover']};
        }}
        QPushButton {{
            background-color: {theme['accent']};
            color: {theme['fg']};
            border: 1px solid {theme['border']};
            padding: 6px 10px;
        }}
        QPushButton:hover {{
            background-color: {theme['accent_hover']};
        }}
    """


class _SearchWorker(QThread):
    finished_ok = pyqtSignal(list, str)
    finished_err = pyqtSignal(str)

    def __init__(
        self,
        source: str,
        query: str,
        limit: int,
        search_cfg: dict,
        parent=None,
    ):
        super().__init__(parent)
        self.source = source
        self.query = query
        self.limit = limit
        self.search_cfg = search_cfg

    def run(self):
        try:
            items, note = run_external_search(
                self.source,
                self.query,
                limit=self.limit,
                search_cfg=self.search_cfg,
            )
            # Real failures only (do not treat "no token / 0 repos" as a modal error)
            low = (note or "").lower()
            if not items and note and (
                "missing" in low
                or "stub" in low
                or "request failed" in low
                or "json error" in low
                or "unknown search source" in low
                or "auth failed" in low
                or "rate limited" in low
                or low.startswith("github http")
                or low.startswith("brave http")
                or low == "empty query"
            ):
                self.finished_err.emit(note)
                return
            self.finished_ok.emit(items, note)
        except Exception as e:
            self.finished_err.emit(str(e))


class _ActionWorker(QThread):
    log_line = pyqtSignal(str)
    finished_ok = pyqtSignal(object)
    finished_err = pyqtSignal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn(lambda m: self.log_line.emit(str(m)))
            self.finished_ok.emit(result)
        except Exception as e:
            self.finished_err.emit(str(e))


class ExternalSearchPanel(QWidget):
    """Central panel: API search results + Capture URL / Clone repo."""

    def __init__(
        self,
        theme: dict,
        *,
        source: str,
        query: str,
        limit: int = 10,
        uieg_cfg: Optional[dict] = None,
        search_cfg: Optional[dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme or {}
        self.source = source
        self.query = query
        self.limit = int(limit or 10)
        self.cfg = merge_uieg_config(uieg_cfg)
        self.search_cfg = search_cfg or {}
        self._results: List[Dict[str, Any]] = []
        self._worker: Optional[QThread] = None

        ensure_capture_folder(self.cfg["capture_folder"])
        self._build_ui()
        self.apply_theme()
        self._start_search()

    def _build_ui(self):
        root = QVBoxLayout(self)
        title = QLabel("External Search — GitHub / Brave")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        root.addWidget(title)

        self.meta_lbl = QLabel(
            f"Source: {self.source}  ·  Query: {self.query}  ·  Limit: {self.limit}"
        )
        self.meta_lbl.setWordWrap(True)
        root.addWidget(self.meta_lbl)

        hint = QLabel(
            "Research stays on disk until you Import (Search + Save). "
            "Promote to Ship's Computer is a separate Browse action — Ask AI will not "
            "see these until you Promote."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.status_lbl = QLabel("Searching…")
        root.addWidget(self.status_lbl)

        bar = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(self._on_open)
        bar.addWidget(self.open_btn)
        self.capture_btn = QPushButton("Capture URL")
        self.capture_btn.clicked.connect(self._on_capture)
        bar.addWidget(self.capture_btn)
        self.clone_btn = QPushButton("Clone / Zip repo")
        self.clone_btn.clicked.connect(self._on_clone)
        bar.addWidget(self.clone_btn)
        self.retry_btn = QPushButton("Retry search")
        self.retry_btn.clicked.connect(self._start_search)
        bar.addWidget(self.retry_btn)
        bar.addStretch()
        root.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Title", "URL", "Snippet", "Meta"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(lambda *_: self._on_open())
        root.addWidget(self.table, stretch=1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.setFont(QFont("Consolas", 9))
        root.addWidget(self.log)

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))

    def _append_log(self, text: str):
        self.log.append(text.rstrip())

    def _set_busy(self, busy: bool):
        for b in (
            self.open_btn,
            self.capture_btn,
            self.clone_btn,
            self.retry_btn,
        ):
            b.setEnabled(not busy)

    def _selected_item(self) -> Optional[Dict[str, Any]]:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        idx = rows[0].row()
        if idx < 0 or idx >= len(self._results):
            return None
        return self._results[idx]

    def _start_search(self):
        if self._worker and self._worker.isRunning():
            return
        self._set_busy(True)
        self.status_lbl.setText("Searching…")
        self.table.setRowCount(0)
        self._results = []
        w = _SearchWorker(
            self.source, self.query, self.limit, self.search_cfg, parent=self
        )
        w.finished_ok.connect(self._on_search_ok)
        w.finished_err.connect(self._on_search_err)
        w.finished.connect(lambda: self._set_busy(False))
        self._worker = w
        w.start()

    def _on_search_ok(self, items: list, note: str):
        self._results = list(items or [])
        self.table.setRowCount(0)
        for item in self._results:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [
                str(item.get("title", "")),
                str(item.get("url", "")),
                str(item.get("snippet", ""))[:300],
                str(item.get("meta", "")),
            ]
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.status_lbl.setText(note or f"{len(self._results)} result(s)")
        self._append_log(note or "Search complete.")

    def _on_search_err(self, err: str):
        self.status_lbl.setText(err)
        self._append_log(err)
        QMessageBox.warning(self, "External Search", err)

    def _on_open(self):
        item = self._selected_item()
        if not item or not item.get("url"):
            QMessageBox.information(self, "Open", "Select a result row first.")
            return
        QDesktopServices.openUrl(QUrl(item["url"]))

    def _on_capture(self):
        item = self._selected_item()
        if not item or not item.get("url"):
            QMessageBox.information(self, "Capture URL", "Select a result row first.")
            return
        url = item["url"]
        capture_folder = default_crawl_folder(self.cfg["capture_folder"])
        link_limit = int(self.cfg.get("crawl_link_limit", 10))
        timeout = int(self.cfg.get("crawl_timeout_sec", 15))

        def work(log):
            return crawl_url_to_disk(
                url,
                capture_folder,
                link_limit=link_limit,
                timeout_sec=timeout,
                fetch_code_links=True,
                log=log,
            )

        self._run_action(
            work,
            on_ok=lambda paths: self._append_log(
                f"Capture wrote {len(paths or [])} file(s) under {capture_folder}. "
                "Use UIEG nav 2 Crawl — Website / Import to load uieg_capture.db."
            ),
        )

    def _on_clone(self):
        item = self._selected_item()
        if not item:
            QMessageBox.information(self, "Clone / Zip", "Select a result row first.")
            return
        url = item.get("url") or ""
        if item.get("kind") != "github_repo" and not parse_github_repo(url):
            QMessageBox.information(
                self,
                "Clone / Zip",
                "Clone / Zip is for GitHub repository results.\n"
                "Use Capture URL for web pages.",
            )
            return
        capture_folder = default_repo_folder(self.cfg["capture_folder"])
        exts = set(self.cfg.get("repo_extensions") or [])

        def work(log):
            return fetch_repo_to_capture(
                url,
                capture_folder,
                extensions=exts or None,
                log=log,
            )

        self._run_action(
            work,
            on_ok=lambda paths: self._append_log(
                f"Repo fetch wrote {len(paths or [])} file(s). "
                "Use UIEG nav 1 Repo / GitHub Fetch → Then Import to load the DB."
            ),
        )

    def _run_action(self, fn: Callable, on_ok: Optional[Callable] = None):
        if self._worker and self._worker.isRunning():
            return
        self._set_busy(True)
        w = _ActionWorker(fn, parent=self)
        w.log_line.connect(self._append_log)
        if on_ok:
            w.finished_ok.connect(on_ok)
        w.finished_err.connect(
            lambda e: (
                self._append_log(f"Error: {e}"),
                QMessageBox.warning(self, "Action failed", e),
            )
        )
        w.finished.connect(lambda: self._set_busy(False))
        self._worker = w
        w.start()
