"""Spock-themed UIEG capture workspace (repo fetch vs website crawl).

Provenance: D:\\Spock-To-Bridge-UIEG-Scanner
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Literal, Optional

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QIntValidator, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage
except ImportError:
    QWebEngineView = None
    QWebEnginePage = None

from LongRangeSensors.uieg_crawler import crawl_url_to_disk
from LongRangeSensors.uieg_database import (
    clear_database,
    count_captures,
    format_file_size,
    get_capture_content,
    get_capture_row,
    init_db,
    list_captures,
)
from LongRangeSensors.uieg_import import copy_local_file_to_capture, import_captured_files
from LongRangeSensors.uieg_paths import (
    CHANNEL_CRAWL,
    CHANNEL_REPO,
    default_crawl_folder,
    default_repo_folder,
    ensure_capture_folder,
    merge_uieg_config,
    migrate_legacy_db,
    resolve_repo_capture_folder,
)
from LongRangeSensors.uieg_preview import start_preview_server, write_temp_preview
from LongRangeSensors.uieg_promote import promote_captures
from LongRangeSensors.uieg_repo_fetch import fetch_repo_to_capture, parse_github_repo


def _panel_stylesheet(theme: dict) -> str:
    return f"""
        QWidget {{
            background-color: {theme['bg']};
            color: {theme['fg']};
        }}
        QLabel {{
            color: {theme['fg']};
        }}
        QTextEdit, QTableWidget, QLineEdit, QComboBox, QSpinBox, QTabWidget::pane {{
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
        QTabBar::tab {{
            background-color: {theme['panel_bg']};
            color: {theme['fg']};
            padding: 6px 12px;
            border: 1px solid {theme['border']};
        }}
        QTabBar::tab:selected {{
            background-color: {theme['accent']};
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


def _action_btn(text: str, bg: str, fg: str = "#FFFFFF") -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(
        f"QPushButton {{ background-color: {bg}; color: {fg}; "
        f"border: none; padding: 6px 12px; font-weight: bold; }}"
        f"QPushButton:hover {{ opacity: 0.9; }}"
    )
    return btn


class _SizeTableItem(QTableWidgetItem):
    """Display human size; sort by raw byte count."""

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        a = self.data(Qt.ItemDataRole.EditRole)
        b = other.data(Qt.ItemDataRole.EditRole) if other is not None else None
        try:
            ai = int(a) if a is not None else -1
        except (TypeError, ValueError):
            ai = -1
        try:
            bi = int(b) if b is not None else -1
        except (TypeError, ValueError):
            bi = -1
        return ai < bi


if QWebEnginePage is not None:

    class _QuietWebPage(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            pass


class _Worker(QThread):
    log_line = pyqtSignal(str)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn(lambda m: self.log_line.emit(str(m)))
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class UiegCapturePanel(QWidget):
    """Channel-scoped capture workspace (repo fetch or website crawl)."""

    def __init__(
        self,
        theme: dict,
        uieg_cfg: Optional[Dict[str, Any]] = None,
        mode: Literal["repo", "crawl"] = "crawl",
        source_hint: str = "1) GitHub",
        query_hint: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.mode = mode
        self.channel = CHANNEL_REPO if mode == "repo" else CHANNEL_CRAWL
        self.cfg = merge_uieg_config(uieg_cfg)
        self._worker: Optional[_Worker] = None
        self._preview_server = None
        self._preview_port = None
        self._temp_dir = os.path.join(self.cfg["capture_folder"], "_preview_tmp")
        self.channel_folder = (
            default_repo_folder(self.cfg["capture_folder"])
            if mode == "repo"
            else default_crawl_folder(self.cfg["capture_folder"])
        )

        ensure_capture_folder(self.cfg["capture_folder"])
        migrated, msg = migrate_legacy_db(self.cfg["database_path"])
        init_db(self.cfg["database_path"])

        root = QVBoxLayout(self)
        if mode == "repo":
            title = QLabel("1 Repo / GitHub Fetch")
            hint = QLabel(
                f"Source: GitHub owner/repo or URL. "
                f"Destination: {self.channel_folder}/<owner>_<repo>/ "
                f"(temp clones under _repos/). "
                f"Fetch → Then Import to DB → Browse / Preview. "
                f"Prefer this path for .md / .py source truth. "
                f"DB: {self.cfg['database_path']}"
            )
        else:
            title = QLabel("2 Crawl — Website / Import")
            hint = QLabel(
                f"Source: website URL (requests + BeautifulSoup, not full browser JS). "
                f"Destination: {self.channel_folder}/ (flat crawl files). "
                f"Crawl → Import → Browse / Preview. "
                f"For GitHub code, use nav step 1 Repo / GitHub Fetch instead. "
                f"DB: {self.cfg['database_path']}"
            )
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        root.addWidget(title)
        hint.setWordWrap(True)
        root.addWidget(hint)

        bar = QHBoxLayout()
        self.refresh_btn = _action_btn("Refresh DB", "#5C6BC0")
        self.refresh_btn.clicked.connect(self.refresh_db_view)
        bar.addWidget(self.refresh_btn)
        self.promote_btn = _action_btn("Promote to Ship's Computer", "#2E7D32")
        self.promote_btn.setToolTip(
            "Copy selected research captures into promoted_research/ and ingest "
            "into ship_computer.db (Ask AI). Research-only captures stay in uieg until you Promote."
        )
        self.promote_btn.clicked.connect(self._promote_selected)
        bar.addWidget(self.promote_btn)
        self.open_folder_btn = _action_btn("Open channel folder", "#78909C")
        self.open_folder_btn.setToolTip(f"Open {self.channel_folder}")
        self.open_folder_btn.clicked.connect(self._open_capture_folder)
        bar.addWidget(self.open_folder_btn)
        self.clear_btn = _action_btn("Clear Data", "#C44A4A")
        self.clear_btn.clicked.connect(self._clear_data)
        bar.addWidget(self.clear_btn)
        bar.addStretch()
        self.status_lbl = QLabel("")
        bar.addWidget(self.status_lbl)
        root.addLayout(bar)

        self.tabs = QTabWidget()
        self._preview_tab_index = 0
        if mode == "repo":
            self.tabs.addTab(self._build_repo_tab(source_hint, query_hint), "Repo")
            self.tabs.addTab(self._build_browse_tab(), "Browse")
            self.tabs.addTab(self._build_preview_tab(), "Preview")
            self._preview_tab_index = 2
        else:
            self.tabs.addTab(self._build_open_url_tab(source_hint, query_hint), "Crawl")
            self.tabs.addTab(self._build_import_tab(), "Import")
            self.tabs.addTab(self._build_browse_tab(), "Browse")
            self.tabs.addTab(self._build_preview_tab(), "Preview")
            self._preview_tab_index = 3
        root.addWidget(self.tabs, stretch=1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.setFont(QFont("Consolas", 9))
        root.addWidget(self.log)

        self.apply_theme()
        if migrated:
            self._append_log(msg)
        self.refresh_db_view()

    # ── Tabs ────────────────────────────────────────────────────────────

    def _build_browse_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel(
            f"Research memory ({self.channel} channel in uieg_capture.db). "
            "Select rows → Promote to Ship's Computer when you want Ask AI / Deep Dive to see them. "
            "Click column headers to sort. "
            "Tiny text files (< 64 B) skip Preview on click (time saver)."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        # Find (any column) — same idea as Documents Search
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("Find:"))
        self.browse_find_input = QLineEdit()
        self.browse_find_input.setPlaceholderText(
            "Search filename, path, type, source, size, promoted…"
        )
        self.browse_find_input.returnPressed.connect(self._on_browse_find)
        find_row.addWidget(self.browse_find_input, stretch=1)
        find_btn = _action_btn("Find", "#1565C0")
        find_btn.clicked.connect(self._on_browse_find)
        find_row.addWidget(find_btn)
        lay.addLayout(find_row)

        # Filter — path/name + type (Documents Path/Ext style)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Path:"))
        self.browse_filter_input = QLineEdit()
        self.browse_filter_input.setPlaceholderText(
            "Path or filename contains (e.g. github, README, .py)"
        )
        filter_row.addWidget(self.browse_filter_input, stretch=1)
        filter_row.addWidget(QLabel("Type:"))
        self.browse_type_combo = QComboBox()
        self.browse_type_combo.setEditable(True)
        self.browse_type_combo.addItems(
            ["*", "html", "htm", "md", "py", "txt", "json", "png", "jpg"]
        )
        self.browse_type_combo.setCurrentText("*")
        self.browse_type_combo.setMinimumWidth(80)
        filter_row.addWidget(self.browse_type_combo)
        apply_btn = _action_btn("Apply Filter", "#2E7D32")
        apply_btn.clicked.connect(self._on_browse_apply_filter)
        filter_row.addWidget(apply_btn)
        clear_btn = _action_btn("Clear Filter", "#78909C")
        clear_btn.clicked.connect(self._on_browse_clear_filter)
        filter_row.addWidget(clear_btn)
        lay.addLayout(filter_row)

        self._browse_rows: list = []
        self._browse_find = ""
        self._browse_path_filter = ""
        self._browse_type_filter = "*"
        # Skip Preview for tiny text/code files (bytes)
        self._tiny_preview_bytes = 64

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "File Name",
                "Type",
                "Size",
                "Captured",
                "Source kind",
                "Promoted",
                "Path",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.cellClicked.connect(self._on_row_clicked)
        lay.addWidget(self.table)
        return w

    def _build_preview_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.preview_meta = QLabel("Select a row in Browse to preview.")
        lay.addWidget(self.preview_meta)

        self._web_view = QWebEngineView() if QWebEngineView is not None else None
        if self._web_view is not None and QWebEnginePage is not None:
            self._web_view.setPage(_QuietWebPage(self._web_view))
        self.image_view = QLabel()
        self.image_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_view.setScaledContents(False)
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Consolas", 10))

        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.text_view)  # 0
        self.preview_stack.addWidget(self.image_view)  # 1
        if self._web_view is not None:
            self.preview_stack.addWidget(self._web_view)  # 2
        lay.addWidget(self.preview_stack, stretch=1)
        return w

    def _build_open_url_tab(self, source_hint: str, query_hint: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel(
            "Fetches HTML with requests (no browser extension). "
            "JS-heavy sites (e.g. Kaggle) may return only the shell page — "
            "use nav step 1 Repo / GitHub Fetch for code repos."
        )
        tip.setWordWrap(True)
        tip.setToolTip(tip.text())
        lay.addWidget(tip)

        row = QHBoxLayout()
        row.addWidget(QLabel("URL:"))
        self.url_edit = QLineEdit()
        default_url = self._default_url_for_source(source_hint, query_hint)
        self.url_edit.setText(default_url)
        self.url_edit.setPlaceholderText("https://github.com/owner/repo")
        row.addWidget(self.url_edit, stretch=1)
        lay.addLayout(row)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Page limit:"))
        self.link_limit = QLineEdit()
        self.link_limit.setText(str(int(self.cfg.get("crawl_link_limit", 10))))
        self.link_limit.setPlaceholderText("1–100 HTML pages")
        self.link_limit.setValidator(QIntValidator(1, 100, self))
        self.link_limit.setMaximumWidth(72)
        self.link_limit.setToolTip("Maximum HTML pages to save (including start URL). Type any value 1–100.")
        opts.addWidget(self.link_limit)
        opts.addWidget(QLabel("Levels:"))
        self.crawl_levels = QLineEdit()
        self.crawl_levels.setText(str(int(self.cfg.get("crawl_levels", 2))))
        self.crawl_levels.setPlaceholderText("1–10")
        self.crawl_levels.setValidator(QIntValidator(1, 10, self))
        self.crawl_levels.setMaximumWidth(48)
        self.crawl_levels.setToolTip(
            "Link depth: 1 = start URL only; 2 = start + linked pages; 3 = one more hop, etc."
        )
        opts.addWidget(self.crawl_levels)
        self.fetch_code_cb = QComboBox()
        self.fetch_code_cb.addItems(["Also fetch linked .py/.md", "HTML pages only"])
        opts.addWidget(self.fetch_code_cb)
        opts.addStretch()
        lay.addLayout(opts)

        btn_row = QHBoxLayout()
        self.crawl_btn = _action_btn("Crawl → crawl/", "#2E7D32")
        self.crawl_btn.setToolTip(f"Write files under {self.channel_folder}")
        self.crawl_btn.clicked.connect(self._start_crawl)
        btn_row.addWidget(self.crawl_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addStretch()
        return w

    def _build_import_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel(
            f"Import files from {self.channel_folder}/ into uieg_capture.db "
            "(recursive, allowlisted extensions). Typical flow: Crawl → Import."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Folder:"))
        self.import_folder_edit = QLineEdit()
        self.import_folder_edit.setText(self.channel_folder)
        self.import_folder_edit.setPlaceholderText("Folder tree to import…")
        folder_row.addWidget(self.import_folder_edit, stretch=1)
        self.pick_folder_btn = _action_btn("Browse…", "#78909C")
        self.pick_folder_btn.clicked.connect(self._pick_import_folder)
        folder_row.addWidget(self.pick_folder_btn)
        lay.addLayout(folder_row)

        btn_row = QHBoxLayout()
        self.import_btn = _action_btn("Import folder tree → DB", "#1565C0")
        self.import_btn.setToolTip(
            "Scan the Folder path recursively and insert new files into uieg_capture.db"
        )
        self.import_btn.clicked.connect(self._start_import)
        btn_row.addWidget(self.import_btn)
        self.reset_folder_btn = _action_btn("Use crawl/", "#5C6BC0")
        self.reset_folder_btn.clicked.connect(self._reset_import_folder)
        btn_row.addWidget(self.reset_folder_btn)
        self.pick_html_btn = _action_btn("Pick file → captured_files", "#00838F")
        self.pick_html_btn.clicked.connect(self._pick_file_to_capture)
        btn_row.addWidget(self.pick_html_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addStretch()
        return w

    def _build_repo_tab(self, source_hint: str, query_hint: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel(
            "Clone (git --depth 1) or download GitHub zip; copy allowlisted "
            f"extensions into {self.channel_folder}/<owner>_<repo>/. "
            "If you pick a drive root (e.g. D:\\), Spock creates D:\\captured_files\\repos\\."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        row = QHBoxLayout()
        row.addWidget(QLabel("owner/repo or URL:"))
        self.repo_edit = QLineEdit()
        if "GitHub" in (source_hint or "") and query_hint.strip():
            self.repo_edit.setText(query_hint.strip())
        elif parse_github_repo(query_hint):
            self.repo_edit.setText(query_hint.strip())
        self.repo_edit.setPlaceholderText("owner/repo or https://github.com/owner/repo")
        row.addWidget(self.repo_edit, stretch=1)
        lay.addLayout(row)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Dest folder:"))
        self.repo_dest_edit = QLineEdit()
        self.repo_dest_edit.setText(self.channel_folder)
        self.repo_dest_edit.setPlaceholderText("Where to write owner_repo files…")
        dest_row.addWidget(self.repo_dest_edit, stretch=1)
        self.repo_pick_dest_btn = _action_btn("Browse…", "#78909C")
        self.repo_pick_dest_btn.clicked.connect(self._pick_repo_dest_folder)
        dest_row.addWidget(self.repo_pick_dest_btn)
        self.repo_reset_dest_btn = _action_btn("Use repos/", "#5C6BC0")
        self.repo_reset_dest_btn.clicked.connect(self._reset_repo_dest_folder)
        dest_row.addWidget(self.repo_reset_dest_btn)
        lay.addLayout(dest_row)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Method:"))
        self.repo_method = QComboBox()
        self.repo_method.addItems(["auto (git then zip)", "git", "zip"])
        opts.addWidget(self.repo_method)
        opts.addStretch()
        lay.addLayout(opts)

        btn_row = QHBoxLayout()
        self.repo_btn = _action_btn("Fetch repo → capture folder", "#6A1B9A")
        self.repo_btn.setToolTip(
            "Writes under Dest folder/<owner>_<repo>/. "
            "Drive root picks create <drive>\\captured_files first."
        )
        self.repo_btn.clicked.connect(self._start_repo_fetch)
        btn_row.addWidget(self.repo_btn)
        self.repo_import_btn = _action_btn("Then Import to DB", "#1565C0")
        self.repo_import_btn.clicked.connect(self._start_import_from_repo_dest)
        btn_row.addWidget(self.repo_import_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addStretch()
        return w

    # ── Actions ─────────────────────────────────────────────────────────

    def _default_url_for_source(self, source_hint: str, query_hint: str) -> str:
        q = (query_hint or "").strip()
        if q.startswith("http://") or q.startswith("https://"):
            return q
        if "GitHub" in (source_hint or ""):
            if parse_github_repo(q):
                owner, repo, _ref = parse_github_repo(q)
                return f"https://github.com/{owner}/{repo}"
            return "https://github.com/"
        if "HuggingFace" in (source_hint or "") or "Hugging Face" in (source_hint or ""):
            return f"https://huggingface.co/{q}" if q else "https://huggingface.co/"
        if "Kaggle" in (source_hint or ""):
            return f"https://www.kaggle.com/{q}" if q else "https://www.kaggle.com/"
        return q or "https://github.com/"

    def _append_log(self, text: str):
        self.log.append(text.rstrip())

    def _set_busy(self, busy: bool):
        for b in (
            getattr(self, "crawl_btn", None),
            getattr(self, "import_btn", None),
            getattr(self, "repo_btn", None),
            self.refresh_btn,
            self.clear_btn,
            getattr(self, "pick_html_btn", None),
            getattr(self, "promote_btn", None),
            getattr(self, "pick_folder_btn", None),
            getattr(self, "reset_folder_btn", None),
            getattr(self, "repo_import_btn", None),
            getattr(self, "repo_pick_dest_btn", None),
            getattr(self, "repo_reset_dest_btn", None),
        ):
            if b is not None:
                b.setEnabled(not busy)

    def refresh_db_view(self):
        self._browse_rows = list(
            list_captures(self.cfg["database_path"], channel=self.channel)
        )
        self._populate_browse_table()

    def _on_browse_find(self):
        self._browse_find = (self.browse_find_input.text() or "").strip()
        self._populate_browse_table()

    def _on_browse_apply_filter(self):
        self._browse_path_filter = (self.browse_filter_input.text() or "").strip()
        self._browse_type_filter = (
            self.browse_type_combo.currentText() or "*"
        ).strip() or "*"
        self._populate_browse_table()

    def _on_browse_clear_filter(self):
        self.browse_find_input.clear()
        self.browse_filter_input.clear()
        self.browse_type_combo.setCurrentText("*")
        self._browse_find = ""
        self._browse_path_filter = ""
        self._browse_type_filter = "*"
        self._populate_browse_table()

    def _filtered_browse_rows(self) -> list:
        rows = list(self._browse_rows or [])
        path_f = (self._browse_path_filter or "").lower()
        type_f = (self._browse_type_filter or "*").lower().lstrip(".")
        find_f = (self._browse_find or "").lower()

        out = []
        for row in rows:
            # id, filename, filepath, filetype, captured_at, source_url, source_kind,
            # promoted_at, promoted_path, file_size
            filename = str(row[1] or "")
            filepath = str(row[2] or "")
            filetype = str(row[3] or "")
            captured = str(row[4] or "")
            source_url = str(row[5] or "") if len(row) > 5 else ""
            source_kind = str(row[6] or "") if len(row) > 6 else ""
            promoted = str(row[7] or "") if len(row) > 7 else ""
            promoted_path = str(row[8] or "") if len(row) > 8 else ""
            file_size = row[9] if len(row) > 9 else None

            if type_f and type_f != "*":
                ft = filetype.lower().lstrip(".")
                if ft != type_f and not filename.lower().endswith(f".{type_f}"):
                    continue

            if path_f:
                blob = f"{filename} {filepath}".lower()
                if path_f not in blob:
                    continue

            if find_f:
                hay = " ".join(
                    [
                        filename,
                        filepath,
                        filetype,
                        captured,
                        source_url,
                        source_kind,
                        promoted,
                        promoted_path,
                        str(row[0]),
                        format_file_size(file_size),
                        str(file_size or ""),
                    ]
                ).lower()
                if find_f not in hay:
                    continue

            out.append(row)
        return out

    def _populate_browse_table(self):
        rows = self._filtered_browse_rows()
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            promoted = str(row[7] or "") if len(row) > 7 else ""
            file_size = row[9] if len(row) > 9 else None
            try:
                size_n = int(file_size) if file_size is not None else -1
            except (TypeError, ValueError):
                size_n = -1
            vals = [
                ("id", row[0]),
                ("text", str(row[1] or "")),
                ("text", str(row[3] or "")),
                ("size", size_n),
                ("text", str(row[4] or "")),
                ("text", str(row[6] or "")),
                ("text", promoted or "—"),
                ("text", str(row[2] or "")),
            ]
            for c, (kind, v) in enumerate(vals):
                item = QTableWidgetItem()
                if kind == "id":
                    try:
                        cid = int(v)
                    except (TypeError, ValueError):
                        cid = 0
                    item.setData(Qt.ItemDataRole.DisplayRole, cid)
                    item.setData(Qt.ItemDataRole.UserRole, cid)
                elif kind == "size":
                    item = _SizeTableItem(format_file_size(v if v >= 0 else None))
                    item.setData(Qt.ItemDataRole.EditRole, v if v >= 0 else -1)
                    item.setToolTip(f"{v} bytes" if v >= 0 else "")
                    self.table.setItem(r, c, item)
                    continue
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, v)
                if c == 6 and promoted:
                    item.setToolTip(str(row[8] if len(row) > 8 else promoted))
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(sorting)

        total = count_captures(self.cfg["database_path"], channel=self.channel)
        all_total = count_captures(self.cfg["database_path"])
        shown = len(rows)
        bits = [f"{total} {self.channel} capture(s)"]
        if all_total != total:
            bits.append(f"{all_total} total in DB")
        if shown != total:
            bits.append(f"showing {shown}")
        if self._browse_find:
            bits.append(f"find={self._browse_find!r}")
        if self._browse_path_filter or (
            self._browse_type_filter and self._browse_type_filter != "*"
        ):
            bits.append(
                f"filter path={self._browse_path_filter!r} type={self._browse_type_filter}"
            )
        self.status_lbl.setText(" · ".join(bits))

    def _on_row_clicked(self, row: int, _col: int):
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        capture_id = id_item.data(Qt.ItemDataRole.UserRole)
        if capture_id is None:
            try:
                capture_id = int(id_item.text())
            except ValueError:
                return
        capture_id = int(capture_id)
        # Skip Preview for tiny text/code — size is the time saver
        db_row = get_capture_row(self.cfg["database_path"], capture_id)
        if db_row is not None:
            filetype = str(db_row[3] or "").lower().lstrip(".")
            file_size = db_row[9] if len(db_row) > 9 else None
            try:
                size_n = int(file_size) if file_size is not None else None
            except (TypeError, ValueError):
                size_n = None
            textish = {
                "md",
                "py",
                "txt",
                "rst",
                "json",
                "toml",
                "yml",
                "yaml",
                "css",
                "js",
                "html",
                "htm",
                "sql",
            }
            thresh = int(getattr(self, "_tiny_preview_bytes", 64))
            if filetype in textish and size_n is not None and size_n < thresh:
                self._append_log(
                    f"Skip Preview #{capture_id} ({db_row[1]}): "
                    f"{format_file_size(size_n)} < {thresh} B — tiny text file"
                )
                self.status_lbl.setText(
                    f"Skipped tiny preview: #{capture_id} {format_file_size(size_n)}"
                )
                return
        self._preview_capture(capture_id)
        self.tabs.setCurrentIndex(self._preview_tab_index)

    def _preview_capture(self, capture_id: int):
        row = get_capture_row(self.cfg["database_path"], capture_id)
        content = get_capture_content(self.cfg["database_path"], capture_id)
        if not row or content is None:
            self.preview_meta.setText("No content.")
            return
        filename, filetype = row[1], (row[3] or "").lower()
        size = row[9] if len(row) > 9 else None
        size_txt = format_file_size(size)
        self.preview_meta.setText(
            f"#{capture_id}  {filename}  ({filetype})  ·  {size_txt}"
        )
        ext = f".{filetype}" if filetype and not filetype.startswith(".") else (filetype or ".bin")
        path = write_temp_preview(content, capture_id, ext, self._temp_dir)
        self._show_preview_path(path, filetype)

    def _show_preview_path(self, path: str, filetype: str):
        ft = (filetype or "").lower().lstrip(".")
        if ft in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
            pix = QPixmap(path)
            self.image_view.setPixmap(
                pix.scaled(
                    900,
                    700,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.preview_stack.setCurrentIndex(1)
            return
        if ft in ("html", "htm") and self._web_view is not None:
            try:
                self._ensure_preview_server()
                name = os.path.basename(path)
                # Serve from temp dir
                url = QUrl(f"http://127.0.0.1:{self._preview_port}/{name}")
                self._web_view.setUrl(url)
                self.preview_stack.setCurrentIndex(2)
                return
            except Exception as e:
                self._append_log(f"HTML preview fallback: {e}")
        # Text fallback
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                self.text_view.setPlainText(f.read())
        except OSError:
            self.text_view.setPlainText(repr(path))
        self.preview_stack.setCurrentIndex(0)

    def _ensure_preview_server(self):
        if self._preview_server is not None:
            return
        os.makedirs(self._temp_dir, exist_ok=True)
        httpd, port, _thread = start_preview_server(self._temp_dir)
        self._preview_server = httpd
        self._preview_port = port

    def _open_capture_folder(self):
        path = self.channel_folder
        ensure_capture_folder(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _clear_data(self):
        n = count_captures(self.cfg["database_path"], channel=self.channel)
        all_n = count_captures(self.cfg["database_path"])
        if self.mode == "repo":
            msg = (
                f"Delete all {all_n} row(s) and batch history from uieg_capture.db?\n"
                f"({n} are repo channel — Clear wipes the whole DB.)\n"
                "(Does not delete files on disk.)"
            )
        else:
            msg = (
                f"Delete all {all_n} row(s) and batch history from uieg_capture.db?\n"
                f"({n} are crawl channel — Clear wipes the whole DB.)\n"
                "(Does not delete files on disk.)"
            )
        reply = QMessageBox.question(self, "Clear Data", msg)
        if reply != QMessageBox.StandardButton.Yes:
            return
        clear_database(self.cfg["database_path"])
        self._append_log("Database cleared.")
        self.refresh_db_view()

    def _selected_capture_ids(self) -> list:
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            item = self.table.item(idx.row(), 0)
            if not item:
                continue
            cid = item.data(Qt.ItemDataRole.UserRole)
            if cid is None:
                try:
                    cid = int(item.text())
                except ValueError:
                    continue
            ids.append(int(cid))
        return ids

    def _promote_selected(self):
        ids = self._selected_capture_ids()
        if not ids:
            QMessageBox.information(
                self,
                "Promote",
                "Select one or more Browse rows first.",
            )
            return
        reply = QMessageBox.question(
            self,
            "Promote to Ship's Computer",
            f"Promote {len(ids)} capture(s) into ship_computer.db?\n\n"
            "Files are written under promoted_research/ and ingested with the "
            "universal extractor (embeddings required for RAG).\n"
            "Ask AI / Deep Dive will see them after a successful ingest.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db_path = self.cfg["database_path"]
        promoted_folder = self.cfg.get("promoted_folder") or ""

        def work(log):
            return promote_captures(
                db_path,
                ids,
                promoted_folder,
                log=log,
            )

        def done(result):
            ok_n, fail_n, _msgs = result if result else (0, 0, [])
            self.refresh_db_view()
            self._append_log(f"Promote done: {ok_n} ok, {fail_n} failed.")
            if fail_n:
                QMessageBox.warning(
                    self,
                    "Promote",
                    f"Promoted {ok_n}; {fail_n} failed. See log for details.",
                )
            else:
                QMessageBox.information(
                    self,
                    "Promote",
                    f"Promoted {ok_n} capture(s) to Ship's Computer.",
                )

        self._run_worker(work, on_ok=done)

    def _start_crawl(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Open URL", "Enter a URL.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        link_limit = int((self.link_limit.text() or "10").strip() or "10")
        crawl_levels = int((self.crawl_levels.text() or "2").strip() or "2")
        fetch_code = self.fetch_code_cb.currentIndex() == 0
        capture_folder = self.channel_folder
        timeout = int(self.cfg.get("crawl_timeout_sec", 15))

        def work(log):
            return crawl_url_to_disk(
                url,
                capture_folder,
                link_limit=link_limit,
                crawl_levels=crawl_levels,
                timeout_sec=timeout,
                fetch_code_links=fetch_code,
                log=log,
            )

        def done(paths):
            self._append_log(
                f"Crawl wrote {len(paths or [])} file(s) under {capture_folder}. "
                "Use Import to load DB."
            )
            if getattr(self, "import_folder_edit", None) is not None:
                self.import_folder_edit.setText(capture_folder)

        self._run_worker(work, on_ok=done)

    def _pick_import_folder(self):
        start = (self.import_folder_edit.text() or "").strip() or self.channel_folder
        if not os.path.isdir(start):
            start = self.channel_folder
        path = QFileDialog.getExistingDirectory(
            self,
            "Pick folder to import",
            start,
        )
        if path:
            self.import_folder_edit.setText(path)
            self._append_log(f"Import folder set: {path}")

    def _reset_import_folder(self):
        self.import_folder_edit.setText(self.channel_folder)
        self._append_log(f"Import folder reset to crawl/: {self.channel_folder}")

    def _start_import(
        self,
        *,
        folder: Optional[str] = None,
        batch_label: Optional[str] = None,
        source_url: Optional[str] = None,
    ):
        if not folder and getattr(self, "import_folder_edit", None) is not None:
            folder = self.import_folder_edit.text().strip()
        if not folder:
            folder = self.channel_folder
        if not os.path.isdir(folder):
            QMessageBox.warning(
                self,
                "Import",
                f"Folder not found:\n{folder}\n\nUse Browse… to pick a folder.",
            )
            return
        db_path = self.cfg["database_path"]
        kind = "manual_import" if self.mode == "crawl" else "repo_file"
        label = batch_label
        if not label:
            if self.mode == "crawl" and getattr(self, "url_edit", None) is not None:
                label = (self.url_edit.text() or "").strip() or "crawl import"
            elif self.mode == "repo" and getattr(self, "repo_edit", None) is not None:
                label = (self.repo_edit.text() or "").strip() or "repo import"
            else:
                label = os.path.basename(folder.rstrip("\\/")) or self.channel

        def work(log):
            return import_captured_files(
                folder,
                db_path,
                channel=self.channel,
                batch_label=label,
                source_kind=kind,
                source_url=source_url or label,
                log=log,
            )

        def done(n):
            self.refresh_db_view()
            self._append_log(f"Imported {n} file(s) from {folder}")

        self._run_worker(work, on_ok=done)

    def _pick_file_to_capture(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pick file to capture",
            "",
            "Web/Text (*.html *.htm *.md *.py *.txt);;All (*.*)",
        )
        if not path:
            return
        dest = copy_local_file_to_capture(
            path, self.channel_folder, log=self._append_log
        )
        if dest:
            QMessageBox.information(
                self,
                "Captured",
                f"Copied to:\n{dest}\n\nUse Import to load into the DB.",
            )

    def _pick_repo_dest_folder(self):
        start = (self.repo_dest_edit.text() or "").strip() or self.channel_folder
        if not os.path.isdir(start):
            drive, _ = os.path.splitdrive(os.path.abspath(start))
            start = (drive + os.sep) if drive else self.channel_folder
        path = QFileDialog.getExistingDirectory(
            self,
            "Pick destination folder for repo fetch",
            start,
        )
        if not path:
            return
        resolved = resolve_repo_capture_folder(path)
        self.repo_dest_edit.setText(resolved)
        if os.path.normcase(os.path.abspath(path)) != os.path.normcase(resolved):
            self._append_log(
                f"Drive root selected ({path}) — using {resolved}"
            )
        else:
            self._append_log(f"Repo dest folder: {resolved}")

    def _reset_repo_dest_folder(self):
        self.repo_dest_edit.setText(self.channel_folder)
        self._append_log(f"Repo dest reset to repos/: {self.channel_folder}")

    def _resolved_repo_dest(self) -> str:
        raw = ""
        if getattr(self, "repo_dest_edit", None) is not None:
            raw = self.repo_dest_edit.text().strip()
        if not raw:
            raw = self.channel_folder
        resolved = resolve_repo_capture_folder(raw)
        if getattr(self, "repo_dest_edit", None) is not None:
            self.repo_dest_edit.setText(resolved)
        return resolved

    def _start_repo_fetch(self):
        spec = self.repo_edit.text().strip()
        if not spec:
            QMessageBox.warning(self, "Repo", "Enter owner/repo or GitHub URL.")
            return
        method_map = {0: "auto", 1: "git", 2: "zip"}
        method = method_map.get(self.repo_method.currentIndex(), "auto")
        capture_folder = self._resolved_repo_dest()
        exts = self.cfg.get("repo_extensions") or None

        def work(log):
            return fetch_repo_to_capture(
                spec,
                capture_folder,
                method=method,
                extensions=exts,
                log=log,
            )

        def done(paths):
            n = len(paths or [])
            self._append_log(
                f"Repo fetch wrote {n} file(s) under {capture_folder}. "
                "Use Then Import to DB (or Import tab) to load."
            )
            # Point Import folder at the same dest for one-click follow-up
            if getattr(self, "import_folder_edit", None) is not None:
                self.import_folder_edit.setText(capture_folder)

        self._run_worker(work, on_ok=done)

    def _start_import_from_repo_dest(self):
        """Import from the Repo dest folder (after fetch)."""
        folder = self._resolved_repo_dest()
        spec = (self.repo_edit.text() or "").strip() if getattr(self, "repo_edit", None) else ""
        self._start_import(
            folder=folder,
            batch_label=spec or "repo import",
            source_url=spec or None,
        )

    def _run_worker(self, fn, on_ok=None):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "Busy", "A capture job is already running.")
            return
        self._set_busy(True)
        self._worker = _Worker(fn, self)
        self._worker.log_line.connect(self._append_log)
        self._worker.failed.connect(self._on_worker_fail)
        if on_ok:
            self._worker.finished_ok.connect(on_ok)
        self._worker.finished.connect(lambda: self._set_busy(False))
        self._worker.start()

    def _on_worker_fail(self, err: str):
        self._append_log(f"ERROR: {err}")
        QMessageBox.critical(self, "Capture failed", err)

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))

    def prepare_shutdown(self):
        if self._preview_server is not None:
            try:
                self._preview_server.shutdown()
            except Exception:
                pass
            self._preview_server = None
