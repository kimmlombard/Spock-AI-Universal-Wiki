"""SQLite grid browsing for ship_computer.db, with a file preview dialog.

Extracted from the retired Spock-to-bridge monolith. Enterprise Bridge uses
`DatabaseManager` + `TableBrowser` for its four data grids; `PreviewDialog`
opens whatever file a row points at.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from deep_dive import build_documents_filter_clause
from WarpCore.preview import is_image_file, is_rich_file, preview_file
from WarpCore.theme import THEMES

__all__ = ["DatabaseManager", "PreviewDialog", "TableBrowser"]


def _running_under_wsl() -> bool:
    """True when this process is inside WSL (WSLg alternate rows paint badly)."""
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(
            encoding="utf-8", errors="ignore"
        ).lower()
    except Exception:
        return False


# SQL keywords that must not be mistaken for column names in a filter clause.
_SQL_WORDS = {
    "and", "or", "not", "like", "lower", "upper", "null", "is", "in",
    "between", "exists", "case", "when", "then", "else", "end",
    "true", "false", "cast", "length",
}


class _SortableTableItem(QTableWidgetItem):
    """Sorts by the UserRole key when set (numbers), else by casefolded text."""

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        if other is None:
            return False
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if left is not None and right is not None:
            try:
                return left < right
            except TypeError:
                pass
        return (self.text() or "").casefold() < (other.text() or "").casefold()


class DatabaseManager:
    """Manages SQLite database connections and queries."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        self.connect()

    def connect(self):
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            raise

    def close(self):
        if self.connection:
            self.connection.close()

    def get_tables(self) -> List[str]:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_table_columns(self, table_name: str) -> List[str]:
        cursor = self.connection.cursor()
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        return [row[1] for row in cursor.fetchall()]

    def get_table_data(
        self, table_name: str, filter_clause: str = "", limit: int = 1000
    ) -> Tuple[List, List[str]]:
        cursor = self.connection.cursor()
        columns = self.get_table_columns(table_name)

        # Refuse filters that reference missing columns (e.g. a Documents path
        # filter applied to captains_log / agent_queue).
        query = f'SELECT * FROM "{table_name}"'
        if filter_clause:
            if self._filter_columns_ok(columns, filter_clause):
                query += f" WHERE {filter_clause}"
            else:
                print(
                    f"Query warning: filter references columns not in {table_name}; "
                    "ignoring filter for this table."
                )
        query += f" LIMIT {limit}"

        try:
            cursor.execute(query)
            return cursor.fetchall(), columns
        except sqlite3.Error as e:
            print(f"Query error: {e}")
            return [], columns

    @staticmethod
    def _filter_columns_ok(columns: List[str], filter_clause: str) -> bool:
        """True if every identifier used like a column exists on the table."""
        if not filter_clause or not filter_clause.strip():
            return True
        colset = {c.lower() for c in columns}
        # Drop string literals so path fragments inside LIKE '…' are ignored
        stripped = re.sub(r"'[^']*'|\"[^\"]*\"", " ", filter_clause)
        for token in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", stripped):
            low = token.lower()
            if low in _SQL_WORDS:
                continue
            if low not in colset:
                return False
        return True

    def get_table_row_count(self, table_name: str) -> int:
        cursor = self.connection.cursor()
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            result = cursor.fetchone()
            return result[0] if result else 0
        except sqlite3.Error as e:
            print(f"Row count error for {table_name}: {e}")
            return 0

    def execute_query(self, query: str) -> List:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Query error: {e}")
            return []


try:
    from PyQt6.QtWebEngineCore import QWebEnginePage

    class _QuietWebPage(QWebEnginePage):
        """Swallow noisy JS console output from previewed HTML."""

        def javaScriptConsoleMessage(self, level, message, line, source):
            pass

except ImportError:
    _QuietWebPage = None


class PreviewDialog(QDialog):
    """Modal dialog for previewing file contents."""

    def __init__(self, file_path: str, parent=None, theme: Optional[dict] = None):
        super().__init__(parent)
        self.file_path = file_path
        self.theme = theme or THEMES["dark"]
        self._preview_server = None
        self._preview_server_thread = None
        self.setWindowTitle(f"Preview - {os.path.basename(file_path)}")
        self.setMinimumSize(900, 650)
        self.setModal(True)
        self.init_ui()
        self.load_preview()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.path_label = QLabel(self.file_path)
        self.path_label.setStyleSheet(
            "font-family: monospace; color: #aaa; padding: 4px;"
        )
        self.path_label.setWordWrap(True)
        header.addWidget(self.path_label, 1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setFixedWidth(160)
        self.search_input.returnPressed.connect(self.on_find_next)
        header.addWidget(self.search_input)

        find_btn = QPushButton("Find")
        find_btn.setFixedWidth(50)
        find_btn.clicked.connect(self.on_find_next)
        header.addWidget(find_btn)

        copy_btn = QPushButton("Copy Path")
        copy_btn.setFixedWidth(90)
        copy_btn.clicked.connect(self.on_copy_path)
        header.addWidget(copy_btn)

        open_btn = QPushButton("Open in Explorer")
        open_btn.setFixedWidth(130)
        open_btn.clicked.connect(self.on_open_in_explorer)
        header.addWidget(open_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(70)
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        header.addWidget(close_btn)

        layout.addLayout(header)

        self.content_stack = QVBoxLayout()
        self.text_view = None
        self.image_view = None
        self.web_view = None
        layout.addLayout(self.content_stack, 1)

        self.status_bar = QLabel()
        self.status_bar.setStyleSheet(
            "border-top: 1px solid #444; padding: 4px; color: #aaa;"
        )
        layout.addWidget(self.status_bar)

        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {self.theme['bg']};
                color: {self.theme['fg']};
            }}
            QLabel {{
                color: {self.theme['fg']};
            }}
            QLineEdit {{
                background-color: {self.theme['panel_bg']};
                color: {self.theme['fg']};
                border: 1px solid {self.theme['border']};
                padding: 5px;
                border-radius: 4px;
            }}
            QPushButton {{
                background-color: {self.theme['accent']};
                color: {self.theme['fg']};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.theme['accent_hover']};
            }}
            QTextEdit {{
                background-color: {self.theme['panel_bg']};
                color: {self.theme['fg']};
                border: 1px solid {self.theme['border']};
                border-radius: 4px;
            }}
            QScrollArea {{
                border: none;
                background-color: {self.theme['panel_bg']};
            }}
            """
        )

    def load_preview(self):
        if not os.path.exists(self.file_path):
            self._show_text(f"[File not found] {self.file_path}")
            self.status_bar.setText("File not found")
            return

        ext = os.path.splitext(self.file_path)[1].lower()
        file_size = os.path.getsize(self.file_path)

        if is_image_file(self.file_path):
            self._show_image(file_size)
        elif is_rich_file(self.file_path):
            self._show_web(file_size, ext)
        elif ext == ".md":
            self._show_markdown(file_size)
        else:
            self._show_text_from_previewer(file_size)

    def _show_markdown(self, file_size: int):
        """Render Markdown with QTextBrowser (same path Ask AI uses)."""
        from WarpCore.preview import preview_file

        content = preview_file(self.file_path)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        try:
            browser.setMarkdown(content)
        except Exception:
            browser.setPlainText(content)
        self.text_view = browser
        self.content_stack.addWidget(browser)
        self.status_bar.setText(
            f"{self._format_size(file_size)} · markdown (rendered)"
        )

    def _show_text_from_previewer(self, file_size: int):
        content = preview_file(self.file_path)
        self._show_text(content)
        line_count = content.count("\n") + 1 if content else 0
        self.status_bar.setText(
            f"{line_count} lines \u00b7 {self._format_size(file_size)} \u00b7 text"
        )

    def _show_text(self, content: str):
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Consolas", 10))
        self.text_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.text_view.setPlainText(content)
        self.content_stack.addWidget(self.text_view)

    def _show_image(self, file_size: int):
        pixmap = QPixmap(self.file_path)
        if pixmap.isNull():
            self._show_text(f"[Failed to load image] {self.file_path}")
            self.status_bar.setText("Failed to load image")
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        image_label = QLabel()
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(image_label)

        self.image_view = scroll
        self.content_stack.addWidget(scroll)
        self.status_bar.setText(
            f"{pixmap.width()}x{pixmap.height()} pixels \u00b7 "
            f"{self._format_size(file_size)} \u00b7 image"
        )

    def _show_web(self, file_size: int, ext: str):
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            self._show_text_from_previewer(file_size)
            return
        try:
            web_view = QWebEngineView()
            if _QuietWebPage is not None:
                web_view.setPage(_QuietWebPage(web_view))
        except Exception:
            self._show_text_from_previewer(file_size)
            return
        if ext in (".html", ".htm"):
            self._load_html_via_http(web_view)
        else:
            web_view.load(QUrl.fromLocalFile(self.file_path))
        self.web_view = web_view
        self.content_stack.addWidget(web_view)

        fmt = "HTML" if ext in (".html", ".htm") else "PDF"
        self.status_bar.setText(
            f"{self._format_size(file_size)} \u00b7 {fmt} (rendered)"
        )

    def _cleanup_preview_server(self):
        if self._preview_server:
            self._preview_server.shutdown()
            self._preview_server.server_close()
            self._preview_server = None
            self._preview_server_thread = None

    def _load_html_via_http(self, web_view):
        """Serve the file over loopback so relative assets and CORS behave."""
        import socket
        import threading
        from functools import partial
        from http.server import HTTPServer, SimpleHTTPRequestHandler

        abs_path = os.path.abspath(self.file_path)
        serve_dir = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)
        self._cleanup_preview_server()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        class _QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

        handler = partial(_QuietHandler, directory=serve_dir)
        server = HTTPServer(("127.0.0.1", port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._preview_server = server
        self._preview_server_thread = thread
        web_view.load(QUrl(f"http://127.0.0.1:{port}/{filename}"))

    def on_find_next(self):
        text = self.search_input.text()
        if not text or not self.text_view:
            return
        if not self.text_view.find(text):
            cursor = self.text_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.text_view.setTextCursor(cursor)
            self.text_view.find(text)

    def on_copy_path(self):
        from PyQt6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.file_path)
        self.status_bar.setText("Path copied to clipboard")

    def on_open_in_explorer(self):
        folder = str(Path(self.file_path).parent)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def closeEvent(self, event):
        self._cleanup_preview_server()
        super().closeEvent(event)

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"


class TableBrowser(QWidget):
    """Schema-aware table browser with search and filter."""

    filter_changed = pyqtSignal(str)

    # Column that holds a file path, per table
    PATH_COLUMNS = {
        "captains_log": "target_path",
        "agent_queue": "payload_json",
        "documents": "path",
        "quarantine": "path",
    }

    def __init__(self, db_manager: DatabaseManager, table_name: str, theme: dict):
        super().__init__()
        self.db_manager = db_manager
        self.table_name = table_name
        self.theme = theme
        self.current_filter = ""
        self.path_col_index = self._resolve_path_column()
        self.init_ui()
        self.load_data()

    def _resolve_path_column(self) -> int:
        target = self.PATH_COLUMNS.get(self.table_name, "path")
        columns = self.db_manager.get_table_columns(self.table_name)
        col_lower = [c.lower() for c in columns]
        if target.lower() in col_lower:
            return col_lower.index(target.lower())
        return -1

    def _extract_path_from_row(self, row: int) -> str:
        """Get a file-system path from the selected row.

        Most tables store a direct path; agent_queue stores a JSON blob whose
        'path' or 'target_path' key holds it.
        """
        if self.path_col_index < 0:
            return ""
        item = self.table_widget.item(row, self.path_col_index)
        if not item:
            return ""
        raw = item.text().strip()
        if not raw:
            return ""
        if self.table_name == "agent_queue":
            try:
                data = json.loads(raw)
                return data.get("path") or data.get("target_path") or ""
            except (json.JSONDecodeError, TypeError, AttributeError):
                return ""
        return raw

    def init_ui(self):
        layout = QVBoxLayout()

        row_count = self.db_manager.get_table_row_count(self.table_name)
        columns = self.db_manager.get_table_columns(self.table_name)

        header_label = QLabel(
            f"Table: {self.table_name} | Rows: {row_count:,} | "
            f"Columns: {len(columns)}"
        )
        header_font = QFont()
        header_font.setPointSize(10)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        self.search_input.returnPressed.connect(self.on_search)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.on_search)
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_button)
        layout.addLayout(search_layout)

        filter_layout = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText(
            "Path or folder; semicolon for several (e.g. Spock-Universal-AI-Wiki; LLMFIT)"
        )
        self.filter_input.setToolTip(
            "Path fragment or folder. Semicolon separates roots, so "
            "'Spock-Universal-AI-Wiki; LLMFIT' shows documents from both."
        )
        filter_layout.addWidget(QLabel("Path:"))
        filter_layout.addWidget(self.filter_input, stretch=1)

        filter_layout.addWidget(QLabel("Ext:"))
        self.ext_combo = QComboBox()
        self.ext_combo.setEditable(True)
        # Multi-language code presets (not Python-only). Comma = OR include;
        # leading ! = exclude (e.g. !.md,!.txt).
        self.ext_combo.addItems(
            [
                "*",
                ".py,.ts,.tsx,.js,.jsx,.rs,.go",
                ".py",
                ".ts,.tsx",
                ".js,.jsx",
                ".rs",
                ".go",
                ".java,.kt",
                ".cs",
                ".cpp,.c,.h",
                ".vue,.svelte",
                ".sql",
                ".json,.toml,.yaml,.yml",
                ".md",
                ".txt",
                "!.md,!.txt",
                "!.md,!.txt,!.rst",
            ]
        )
        self.ext_combo.setCurrentText(".py,.ts,.tsx,.js,.jsx,.rs,.go")
        self.ext_combo.setMinimumWidth(160)
        self.ext_combo.setToolTip(
            "File extension filter AND'd with path.\n"
            "Comma list = match any (OR). Prefix with ! to exclude "
            "(e.g. !.md,!.txt). Ship's Logs defaults to common code, not *.py only."
        )
        filter_layout.addWidget(self.ext_combo)

        folder_code_btn = QPushButton("Folder's Code")
        folder_code_btn.setToolTip(
            "Preset: current path + multi-language source "
            "(.py/.ts/.js/.rs/.go/…) — not Python-only"
        )
        folder_code_btn.clicked.connect(self.on_folder_code_preset)
        filter_layout.addWidget(folder_code_btn)

        folder_py_btn = QPushButton("Folder's Python")
        folder_py_btn.setToolTip(
            "Preset: current path filter + .py only (recursive tree via path LIKE)"
        )
        folder_py_btn.clicked.connect(self.on_folder_python_preset)
        filter_layout.addWidget(folder_py_btn)

        apply_filter_button = QPushButton("Apply Filter")
        apply_filter_button.clicked.connect(self.on_apply_filter)
        clear_filter_button = QPushButton("Clear Filter")
        clear_filter_button.clicked.connect(self.on_clear_filter)
        filter_layout.addWidget(apply_filter_button)
        filter_layout.addWidget(clear_filter_button)
        layout.addLayout(filter_layout)

        self.table_widget = QTableWidget()
        # WSLg paints Qt's default alternate rows as harsh black/white — suppress
        # there. On Windows/macOS keep striping with theme-tinted QSS colors.
        self.table_widget.setAlternatingRowColors(not _running_under_wsl())
        self.table_widget.setSortingEnabled(True)
        self.table_widget.cellDoubleClicked.connect(self.on_cell_double_clicked)
        layout.addWidget(self.table_widget)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.preview_button = QPushButton("Preview")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self.on_preview)
        self.table_widget.itemSelectionChanged.connect(self._on_selection_changed)
        button_layout.addWidget(self.preview_button)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.on_refresh)
        button_layout.addWidget(refresh_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.on_close)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {self.theme['bg']};
                color: {self.theme['fg']};
            }}
            QTableWidget {{
                background-color: {self.theme['panel_bg']};
                alternate-background-color: {self.theme.get('bg', self.theme['panel_bg'])};
                color: {self.theme['fg']};
                border: 1px solid {self.theme['border']};
                gridline-color: {self.theme['border']};
            }}
            QTableWidget::item {{
                padding: 4px;
                background-color: transparent;
                color: {self.theme['fg']};
            }}
            QTableWidget::item:selected {{
                background-color: {self.theme['accent']};
                color: {self.theme['fg']};
            }}
            QHeaderView::section {{
                background-color: {self.theme['panel_bg']};
                color: {self.theme['fg']};
                border: 1px solid {self.theme['border']};
                padding: 4px;
                font-weight: bold;
            }}
            QLineEdit {{
                background-color: {self.theme['panel_bg']};
                color: {self.theme['fg']};
                border: 1px solid {self.theme['border']};
                padding: 5px;
                border-radius: 4px;
            }}
            QComboBox {{
                background-color: {self.theme['panel_bg']};
                color: {self.theme['fg']};
                border: 1px solid {self.theme['border']};
                padding: 4px;
                border-radius: 4px;
            }}
            QPushButton {{
                background-color: {self.theme['accent']};
                color: {self.theme['fg']};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.theme['accent_hover']};
            }}
            QLabel {{
                color: {self.theme['fg']};
            }}
            """
        )

    def load_data(self, filter_clause: str = ""):
        data, columns = self.db_manager.get_table_data(
            self.table_name, filter_clause, 1000
        )

        # Qt re-sorts on every setItem() while sorting is live, which shuffles
        # rows out from under the loop and leaves cells blank. Fill first, then
        # hand sorting back — Qt re-applies the header's sort indicator.
        sorting = self.table_widget.isSortingEnabled()
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(len(data))
        self.table_widget.setColumnCount(len(columns))
        self.table_widget.setHorizontalHeaderLabels(columns)

        for row_idx, row_data in enumerate(data):
            for col_idx, value in enumerate(row_data):
                if isinstance(value, bytes):
                    text = f"[BLOB {len(value):,} bytes]"
                else:
                    text = str(value) if value is not None else ""
                if len(text) > 500:
                    text = text[:500] + "..."
                item = _SortableTableItem(text)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    # UserRole sort key keeps id / file_size / mtime numeric
                    # instead of ordering "9" above "60".
                    item.setData(Qt.ItemDataRole.UserRole, value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table_widget.setItem(row_idx, col_idx, item)

        self.table_widget.setSortingEnabled(sorting)
        self.table_widget.resizeColumnsToContents()

    def on_search(self):
        search_term = self.search_input.text().strip()
        if not search_term:
            self.load_data(self.current_filter)
            return
        columns = self.db_manager.get_table_columns(self.table_name)
        search_parts = [f'"{col}" LIKE \'%{search_term}%\'' for col in columns]
        search_clause = " OR ".join(search_parts)
        if self.current_filter:
            filter_clause = f"({self.current_filter}) AND ({search_clause})"
        else:
            filter_clause = search_clause
        self.load_data(filter_clause)

    def on_folder_code_preset(self):
        if not self.filter_input.text().strip():
            QMessageBox.information(
                self,
                "Folder's Code",
                "Enter a path fragment or folder first "
                "(e.g. Spock-UIE-Wiki-KB or tools/llmfit).",
            )
            return
        self.ext_combo.setCurrentText(".py,.ts,.tsx,.js,.jsx,.rs,.go")
        self.on_apply_filter()

    def on_folder_python_preset(self):
        if not self.filter_input.text().strip():
            QMessageBox.information(
                self,
                "Folder's Python",
                "Enter a path fragment or folder first "
                "(e.g. AI-QBE-Python or D:\\AI-QBE-Python).",
            )
            return
        self.ext_combo.setCurrentText(".py")
        self.on_apply_filter()

    def restore_filter(self, path_text: str, ext_text: str, filter_clause: str = ""):
        """Re-apply a persisted Documents filter when reopening the grid."""
        self.filter_input.setText(path_text or "")
        self.ext_combo.setCurrentText(ext_text or "*")
        clause = filter_clause or build_documents_filter_clause(
            path_text or "", ext_text or "*", exclude_generated=False
        )
        self.current_filter = clause
        self.load_data(clause)

    def clear_filter_silent(self):
        """Clear UI + data without emitting; the host owns persistence."""
        self.current_filter = ""
        self.filter_input.clear()
        self.search_input.clear()
        self.ext_combo.setCurrentText("*")
        self.load_data()

    def on_apply_filter(self):
        if self.table_name != "documents":
            QMessageBox.information(
                self,
                "Filter",
                "Path / extension filters only apply to the documents table.\n"
                f"Current table: {self.table_name}",
            )
            return
        raw = self.filter_input.text().strip()
        ext = self.ext_combo.currentText().strip()
        if not raw and (not ext or ext in ("*", "Any", "any")):
            self.on_clear_filter()
            return
        self.current_filter = build_documents_filter_clause(
            raw, ext, exclude_generated=False
        )
        if not self.current_filter:
            self.on_clear_filter()
            return
        try:
            n = self.db_manager.execute_query(
                f'SELECT COUNT(*) FROM "{self.table_name}" WHERE {self.current_filter}'
            )
            count = int(n[0][0]) if n else 0
        except Exception:
            count = -1
        self.load_data(self.current_filter)
        self.filter_changed.emit(self.current_filter)
        if count == 0:
            QMessageBox.warning(
                self,
                "Filter matches nothing",
                f"No documents match:\n{self.current_filter}\n\n"
                "Ask AI / Deep Dive will search an empty set until you Clear Filter.\n"
                "Tip: try a path fragment that exists (e.g. AI-QBE, not QI-QBE).",
            )
        elif count > 0:
            QMessageBox.information(
                self,
                "Filter applied",
                f"{count} document(s) match:\n{self.current_filter}\n\n"
                "Ask AI stays scoped to them. Use Deep Dive for multi-file analysis.\n"
                "Filter persists until Clear Filter or Ask AI → Clear.",
            )

    def on_clear_filter(self):
        self.clear_filter_silent()
        self.filter_changed.emit("")

    def on_refresh(self):
        self.load_data(self.current_filter)
        row_count = self.db_manager.get_table_row_count(self.table_name)
        QMessageBox.information(self, "Refresh", f"Table refreshed.\nRows: {row_count}")

    def _on_selection_changed(self):
        if self.path_col_index < 0:
            self.preview_button.setEnabled(False)
            return
        row = self.table_widget.currentRow()
        if row < 0:
            self.preview_button.setEnabled(False)
            return
        path = self._extract_path_from_row(row)
        self.preview_button.setEnabled(bool(path) and os.path.exists(path))

    def on_cell_double_clicked(self, row: int, column: int):
        if column == self.path_col_index:
            path = self._extract_path_from_row(row)
            if path and os.path.exists(path):
                self._open_preview(path)

    def on_preview(self):
        row = self.table_widget.currentRow()
        if row < 0:
            return
        path = self._extract_path_from_row(row)
        if path:
            self._open_preview(path)

    def _open_preview(self, file_path: str):
        PreviewDialog(file_path, parent=self, theme=self.theme).exec()

    def on_close(self):
        main_window = self.window()
        if hasattr(main_window, "show_home"):
            main_window.show_home()
        elif hasattr(main_window, "show_home_page"):
            main_window.show_home_page()
        elif main_window is not None and main_window is not self:
            # Standalone ``python db_browser.py`` window — Close exits the app.
            main_window.close()


def _default_db_path() -> Path:
    try:
        from spock_shell.paths import SHIP_COMPUTER_DB

        return Path(SHIP_COMPUTER_DB)
    except Exception:
        return Path(__file__).resolve().parent / "ship_computer.db"


def _standalone_main(argv: Optional[List[str]] = None) -> int:
    """Open a standalone SQLite grid window over ``ship_computer.db``."""
    import argparse
    import sys

    from PyQt6.QtWidgets import (
        QApplication,
        QComboBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QVBoxLayout,
        QWidget,
    )

    parser = argparse.ArgumentParser(
        description="Browse Spock ship_computer.db (standalone TableBrowser)."
    )
    parser.add_argument(
        "db",
        nargs="?",
        default=None,
        help="Path to SQLite DB (default: install-root ship_computer.db)",
    )
    parser.add_argument(
        "--table",
        default="",
        help="Initial table (default: documents if present, else first table)",
    )
    parser.add_argument(
        "--theme",
        default="dark",
        choices=sorted(THEMES.keys()),
        help="WarpCore theme name",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db).expanduser() if args.db else _default_db_path()
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2

    app = QApplication.instance() or QApplication(sys.argv)
    theme = THEMES.get(args.theme) or THEMES["dark"]

    try:
        db = DatabaseManager(str(db_path))
    except Exception as exc:
        QMessageBox.critical(None, "Spock DB Browser", f"Could not open:\n{db_path}\n\n{exc}")
        return 1

    tables = db.get_tables()
    if not tables:
        QMessageBox.warning(None, "Spock DB Browser", f"No tables in:\n{db_path}")
        return 1

    preferred = (args.table or "documents").strip()
    initial = preferred if preferred in tables else tables[0]

    win = QMainWindow()
    win.setWindowTitle(f"Spock DB Browser — {db_path.name}")
    win.resize(1100, 720)

    central = QWidget()
    lay = QVBoxLayout(central)
    header = QHBoxLayout()
    header.addWidget(QLabel(f"<b>{db_path}</b>"))
    header.addStretch(1)
    table_pick = QComboBox()
    table_pick.addItems(tables)
    table_pick.setCurrentText(initial)
    header.addWidget(QLabel("Table:"))
    header.addWidget(table_pick)
    lay.addLayout(header)

    body = QVBoxLayout()
    body_host = QWidget()
    body_host.setLayout(body)
    lay.addWidget(body_host, 1)

    browser_holder: dict = {"widget": None}

    def show_table(name: str) -> None:
        old = browser_holder["widget"]
        if old is not None:
            body.removeWidget(old)
            old.deleteLater()
        try:
            browser = TableBrowser(db, name, theme)
        except Exception as exc:
            browser = QLabel(f"Could not open table <b>{name}</b>:<br>{exc}")
            browser.setWordWrap(True)
        browser_holder["widget"] = browser
        body.addWidget(browser)
        win.setWindowTitle(f"Spock DB Browser — {db_path.name} / {name}")

    table_pick.currentTextChanged.connect(show_table)
    show_table(initial)

    win.setCentralWidget(central)
    win.show()
    code = app.exec()
    db.close()
    return int(code) if isinstance(code, int) else 0


if __name__ == "__main__":
    raise SystemExit(_standalone_main())
