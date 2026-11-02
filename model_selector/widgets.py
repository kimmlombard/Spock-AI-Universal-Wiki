"""Shared chrome helpers for model selector panels."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QTableWidgetItem


def _action_btn(text: str, color: str, text_color: str = "#111111") -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {color};
            color: {text_color};
            border: none;
            padding: 8px 14px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 11px;
        }}
        QPushButton:hover {{ opacity: 0.9; }}
        QPushButton:checked {{
            border: 2px solid #FFFFFF;
            padding: 6px 12px;
        }}
        QPushButton:disabled {{
            background-color: #444444;
            color: #888888;
        }}
        """
    )
    return btn


class _SortableTableItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by UserRole when set (numbers), else casefold text."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
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


def _panel_stylesheet(theme: dict) -> str:
    return f"""
        QWidget {{
            background-color: {theme['bg']};
            color: {theme['fg']};
        }}
        QLabel {{
            color: {theme['fg']};
        }}
        QTextEdit, QTableWidget, QLineEdit, QComboBox {{
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
        QProgressBar {{
            border: 1px solid {theme['border']};
            background-color: {theme['panel_bg']};
            text-align: center;
            color: {theme['fg']};
        }}
        QProgressBar::chunk {{
            background-color: {theme['accent']};
        }}
    """
