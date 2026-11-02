"""Ship's Logs — the four ship_computer.db tables in one tabbed panel.

These were four separate left-nav buttons in the retired Enterprise Bridge
window. They are all the same generic ``TableBrowser`` pointed at a different
table, so one tab strip replaces a whole mini-app.

Browsers are built when their tab is first selected: ``documents`` can be large,
and opening the panel should not pay for all four queries up front.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

# (tab label, ship_computer.db table name)
LOG_TABLES: List[Tuple[str, str]] = [
    ("Captains Log", "captains_log"),
    ("Agents Queue", "agent_queue"),
    ("Documents", "documents"),
    ("Quarantine", "quarantine"),
]


def _message(text: str) -> QWidget:
    page = QWidget()
    lay = QVBoxLayout(page)
    label = QLabel(text)
    label.setWordWrap(True)
    lay.addWidget(label)
    lay.addStretch()
    return page


class ShipsLogsPanel(QWidget):
    """Tabbed browser over captains_log, agent_queue, documents, quarantine."""

    def __init__(self, theme: Dict[str, str], db_path: str, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.db_path = db_path
        self._db = None
        self._loaded: Dict[int, QWidget] = {}

        lay = QVBoxLayout(self)
        tip = QLabel(
            "<b>Ship's Logs</b>: browse <code>ship_computer.db</code>. Search or "
            "filter a table, then Preview (or double-click a path cell) to open "
            "the source file."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.tabs = QTabWidget()
        for label, _table in LOG_TABLES:
            self.tabs.addTab(_message(f"Loading {label}…"), label)
        self.tabs.currentChanged.connect(self._ensure_tab)
        lay.addWidget(self.tabs, 1)

        # Open on Documents (can be large; lazy-load still applies).
        docs_index = next(
            (i for i, (_label, table) in enumerate(LOG_TABLES) if table == "documents"),
            0,
        )
        self.tabs.setCurrentIndex(docs_index)
        self._ensure_tab(docs_index)

    def _ensure_db(self) -> bool:
        if self._db is not None:
            return True
        from db_browser import DatabaseManager

        try:
            self._db = DatabaseManager(self.db_path)
        except Exception:
            self._db = None
            return False
        return True

    def _ensure_tab(self, index: int) -> None:
        if index < 0 or index >= len(LOG_TABLES) or index in self._loaded:
            return
        label, table = LOG_TABLES[index]
        widget = self._build_browser(label, table)
        self._loaded[index] = widget
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, widget, label)
        self.tabs.setCurrentIndex(index)

    def _build_browser(self, label: str, table: str) -> QWidget:
        if not self._ensure_db():
            return _message(f"Could not open the database:\n{self.db_path}")
        from db_browser import TableBrowser

        try:
            return TableBrowser(self._db, table, self.theme)
        except Exception as e:
            return _message(f"Could not open table <b>{table}</b>:<br>{e}")

    def browser(self, table: str) -> Optional[QWidget]:
        """Loaded browser for a table name, or None if that tab is untouched."""
        for index, (_label, name) in enumerate(LOG_TABLES):
            if name == table:
                return self._loaded.get(index)
        return None

    def documents_path_filter(self) -> str:
        """Path: field on the Documents table browser (empty if not loaded)."""
        browser = self.browser("documents")
        if browser is None:
            return ""
        filt = getattr(browser, "filter_input", None)
        if filt is None:
            return ""
        return str(filt.text() or "").strip()

    def select_table(self, table: str) -> None:
        """Switch to a log table tab (lazy-builds the browser)."""
        for index, (_label, name) in enumerate(LOG_TABLES):
            if name == table:
                self.tabs.setCurrentIndex(index)
                self._ensure_tab(index)
                return


def build_ships_logs_panel(
    theme: Dict[str, str], db_path: str, parent=None
) -> ShipsLogsPanel:
    return ShipsLogsPanel(theme, db_path, parent=parent)
