"""Offer to copy Ship's Logs Path filter into Ask AI Path."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, MutableSet, Optional

from PyQt6.QtWidgets import QMessageBox, QWidget


def ships_logs_path_filter(logs: Any) -> str:
    """Current Documents-tab Path: text from Ship's Logs, or empty."""
    getter = getattr(logs, "documents_path_filter", None)
    if callable(getter):
        return str(getter() or "").strip()
    browser = None
    if hasattr(logs, "browser") and callable(logs.browser):
        browser = logs.browser("documents")
    if browser is None:
        return ""
    filt = getattr(browser, "filter_input", None)
    if filt is None:
        return ""
    return str(filt.text() or "").strip()


def path_filter_match_count(db_path: str | Path, path_filter: str) -> int:
    """How many documents match this path filter (extension unrestricted)."""
    raw = (path_filter or "").strip()
    if not raw:
        return 0
    try:
        from deep_dive import build_documents_filter_clause

        clause = build_documents_filter_clause(raw, "*", exclude_generated=False)
    except Exception:
        return 0
    if not clause:
        return 0
    db = Path(db_path)
    if not db.is_file():
        return 0
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        try:
            row = conn.execute(
                f"SELECT COUNT(*) FROM documents WHERE {clause}"
            ).fetchone()
            return int(row[0] or 0) if row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def offer_copy_ships_path_to_ask(
    parent: QWidget,
    *,
    logs: Any,
    ask: Any,
    db_path: str | Path,
    offered: Optional[MutableSet[str]] = None,
) -> bool:
    """Ask once per filter value whether to copy Ship's Logs Path → Ask AI Path.

    Returns True if the Ask AI path was updated.
    """
    path = ships_logs_path_filter(logs)
    if not path:
        return False
    get_ask = getattr(ask, "path_filter", None)
    current = str(get_ask() if callable(get_ask) else "").strip()
    if current == path:
        return False
    if offered is not None and path in offered:
        return False

    count = path_filter_match_count(db_path, path)
    if count <= 0:
        return False

    if offered is not None:
        offered.add(path)

    reply = QMessageBox.question(
        parent,
        "Copy path filter to Ask AI?",
        f"Ship's Logs Path filter is set to:\n\n{path}\n\n"
        f"{count} document(s) match in ship_computer.db.\n\n"
        "Copy this filter to Ask AI Path?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return False
    setter = getattr(ask, "set_path_filter", None)
    if callable(setter):
        setter(path)
        return True
    path_edit = getattr(ask, "path_edit", None)
    if path_edit is not None and hasattr(path_edit, "setText"):
        path_edit.setText(path)
        return True
    return False
