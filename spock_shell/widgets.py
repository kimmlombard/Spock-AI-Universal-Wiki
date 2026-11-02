"""Reusable shell widgets (from pyqt6-skeleton-v2)."""

from __future__ import annotations

from typing import Callable, Dict

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class ModernButton(QPushButton):
    def __init__(self, text: str, theme: Dict[str, str]):
        super().__init__(text)
        self.theme = theme
        self.apply_theme()

    def apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {self.theme['accent']};
                color: {self.theme['fg']};
                border: none;
                padding: 12px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {self.theme['accent_hover']};
            }}
            QPushButton:pressed {{
                background-color: {self.theme['accent']};
            }}
            QPushButton:checked {{
                border: 2px solid {self.theme['fg']};
            }}
            """
        )


class SidePanel(QWidget):
    def __init__(self, title: str, theme: Dict[str, str]):
        super().__init__()
        self.theme = theme
        self.layout = QVBoxLayout(self)
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        self.layout.addWidget(title_label)
        self.layout.addSpacing(10)
        self.apply_theme()

    def add_button(self, text: str, callback: Callable) -> ModernButton:
        btn = ModernButton(text, self.theme)
        btn.clicked.connect(callback)
        self.layout.addWidget(btn)
        return btn

    def apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {self.theme['panel_bg']};
                color: {self.theme['fg']};
            }}
            QLabel {{ color: {self.theme['fg']}; }}
            """
        )
