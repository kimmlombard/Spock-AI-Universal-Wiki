"""Modal dialog to maintain scan_roots (Spock Console / scan_config.json)."""

from __future__ import annotations

import json
from typing import List

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from spock_wiki_adapter.paths import ROOT, SCAN_CONFIG, SHIP_COMPUTER_DB


class ScanRootsDialog(QDialog):
    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.config_path = str(SCAN_CONFIG)
        self.db_path = SHIP_COMPUTER_DB
        self.setWindowTitle("Update Scan Roots")
        self.setMinimumSize(550, 400)
        self.setModal(True)
        self.roots = self._load_roots()
        self._build()

    def _load_roots(self) -> List[str]:
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            roots = settings_store.get(self.db_path, "scan.scan_roots")
            if roots:
                return [str(r) for r in roots]
        except Exception:
            pass
        try:
            with open(self.config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            return list(cfg.get("scan_roots", []))
        except Exception:
            return [str(ROOT)]

    def _save_roots(self) -> None:
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            settings_store.set(
                self.db_path, "scan.scan_roots", self.roots, by="maintenance"
            )
        except Exception:
            pass
        try:
            with open(self.config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg["scan_roots"] = self.roots
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("SCAN ROOTS — FOLDERS TO INDEX")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Consolas", 10))
        for root in self.roots:
            self.list_widget.addItem(root)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Folder...")
        add_btn.setMinimumHeight(30)
        add_btn.clicked.connect(self._add_root)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("Delete Selected")
        del_btn.setMinimumHeight(30)
        del_btn.clicked.connect(self._delete_root)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        save_btn = QPushButton("Save")
        save_btn.setMinimumHeight(30)
        save_btn.setMinimumWidth(80)
        save_btn.clicked.connect(self._save_and_close)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(30)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _add_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Scan Root Folder")
        if folder:
            from db_maintenance import normalize_scan_root_path

            folder = normalize_scan_root_path(folder)
            if folder not in self.roots:
                self.roots.append(folder)
                self.list_widget.addItem(folder)
                self.status_label.setText(f"Added: {folder}")
            else:
                self.status_label.setText("Already in scan roots")

    def _delete_root(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            self.status_label.setText("Select a root to delete")
            return
        removed = self.list_widget.item(row).text()
        self.list_widget.takeItem(row)
        self.roots = [r for r in self.roots if r != removed]
        self.status_label.setText(f"Removed: {removed}")

    def _save_and_close(self) -> None:
        self._save_roots()
        QMessageBox.information(
            self,
            "Saved",
            "Scan roots saved.\n\nRestart Wiki Scan if the agent is already running.",
        )
        self.accept()
