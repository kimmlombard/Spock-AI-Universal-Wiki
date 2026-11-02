"""UIEG Status center pane — overview + database maintenance."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from LongRangeSensors.uieg_database import format_uieg_status_report
from LongRangeSensors.uieg_maintenance import (
    auto_backup_before_reset,
    backup_db,
    list_backups,
    reindex_db,
    reset_all,
    reset_channel,
    restore_db,
)
from LongRangeSensors.uieg_paths import CHANNEL_CRAWL, CHANNEL_REPO, merge_uieg_config


class UiegStatusPanel(QWidget):
    """Tabbed UIEG DB status + maintenance (mirrors Maintenance → Database tab)."""

    def __init__(
        self,
        theme: Dict[str, str],
        *,
        uieg_cfg: Optional[Dict[str, Any]] = None,
        on_db_changed: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.cfg = merge_uieg_config(uieg_cfg)
        self.db_path = str(self.cfg.get("database_path") or "")
        self._on_db_changed = on_db_changed

        lay = QVBoxLayout(self)
        title = QLabel("3 UIEG DB Status")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lay.addWidget(title)

        tip = QLabel(
            "Overview of <code>uieg_capture.db</code> plus backup, restore, reindex, "
            "and channel-specific reset (repo vs crawl)."
        )
        tip.setWordWrap(True)
        tip.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(tip)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_database_tab(), "Database")
        lay.addWidget(self.tabs, 1)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(
            "QPushButton { background:#5C6BC0; color:#fff; padding:8px 16px; "
            "border:none; border-radius:4px; font-weight:bold; }"
        )
        self.refresh_btn.clicked.connect(self.refresh)
        refresh_row.addWidget(self.refresh_btn)
        lay.addLayout(refresh_row)

        self.refresh()

    def _text_style(self) -> str:
        return (
            f"QTextEdit {{ background:{self.theme.get('panel_bg', '#2d2d2d')}; "
            f"color:{self.theme.get('fg', '#e0e0e0')}; "
            f"border:1px solid {self.theme.get('border', '#444')}; "
            f"border-radius:4px; padding:8px; }}"
        )

    def _make_run_btn(self, label: str, callback) -> QPushButton:
        btn = QPushButton(label)
        btn.setStyleSheet(
            "QPushButton { background:#1565C0; color:#fff; padding:8px 14px; "
            "border:none; border-radius:4px; font-weight:bold; }"
            "QPushButton:hover { background:#1976D2; }"
        )
        btn.clicked.connect(callback)
        return btn

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        heading = QLabel("UIEG CAPTURE — STATUS")
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        layout.addWidget(heading)
        body = QLabel(
            "Capture counts by channel (repo vs crawl), recent import batches, "
            "source kinds, and repos promoted to Ship's Computer."
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        self.overview_view = QTextEdit()
        self.overview_view.setReadOnly(True)
        self.overview_view.setFont(QFont("Consolas", 10))
        self.overview_view.setStyleSheet(self._text_style())
        layout.addWidget(self.overview_view, 1)
        return tab

    def _build_database_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        heading = QLabel("Database")
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        layout.addWidget(heading)
        intro = QLabel(
            "Backup, restore, reindex (ANALYZE + VACUUM), or reset uieg_capture.db. "
            "Reset creates an automatic backup first and can target repo or crawl channel only."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        actions = [
            (
                "Backup UIEG Database",
                "Copy uieg_capture.db into the backups/ folder with a timestamp.",
                self._op_backup,
            ),
            (
                "Restore UIEG Database",
                "Overwrite the current database from a prior backup (destructive).",
                self._op_restore,
            ),
            (
                "Reindex Database",
                "Run ANALYZE, then VACUUM uieg_capture.db.",
                self._op_reindex,
            ),
            (
                "Reset Database",
                "Automatic backup, then choose: reset Repo / GitHub, "
                "reset Crawl / Website Import, or wipe the entire DB.",
                self._op_reset,
            ),
        ]
        for action_title, action_tip, callback in actions:
            box = QWidget()
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(0, 4, 0, 4)
            box_lay.setSpacing(4)
            sub = QLabel(action_title)
            sf = QFont()
            sf.setBold(True)
            sub.setFont(sf)
            box_lay.addWidget(sub)
            tip_lbl = QLabel(action_tip)
            tip_lbl.setWordWrap(True)
            tip_lbl.setStyleSheet("color: #aaa;")
            box_lay.addWidget(tip_lbl)
            row = QHBoxLayout()
            row.addWidget(self._make_run_btn(f"Run {action_title}", callback))
            row.addStretch()
            box_lay.addLayout(row)
            layout.addWidget(box)
        layout.addStretch()
        return tab

    def refresh(self) -> None:
        text = format_uieg_status_report(self.db_path)
        self.overview_view.setPlainText(text)

    def _notify_changed(self) -> None:
        self.refresh()
        if self._on_db_changed:
            self._on_db_changed()

    def _op_backup(self) -> None:
        try:
            path = backup_db(self.db_path)
            sz = os.path.getsize(path) / (1024 * 1024)
            QMessageBox.information(
                self,
                "Backup",
                f"Backup complete:\n{path}\n{sz:.1f} MB",
            )
        except Exception as e:
            QMessageBox.warning(self, "Backup", str(e))

    def _op_restore(self) -> None:
        backups = list_backups(self.db_path)
        if not backups:
            QMessageBox.information(self, "Restore", "No UIEG backups found.")
            return
        item, ok = QInputDialog.getItem(
            self,
            "Restore UIEG Database",
            "Select backup:",
            backups,
            len(backups) - 1,
            False,
        )
        if not ok:
            return
        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            f"This will OVERWRITE the current database.\nRestore from {item}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            restore_db(self.db_path, item)
            self._notify_changed()
            QMessageBox.information(self, "Restore", f"Restored: {item}")
        except Exception as e:
            QMessageBox.warning(self, "Restore", str(e))

    def _op_reindex(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reindex",
            "Run ANALYZE and VACUUM on uieg_capture.db?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            reindex_db(self.db_path)
            self._notify_changed()
            QMessageBox.information(self, "Reindex", "Reindex complete.")
        except Exception as e:
            QMessageBox.warning(self, "Reindex", str(e))

    def _prompt_reset_mode(self) -> Optional[str]:
        box = QMessageBox(self)
        box.setWindowTitle("Reset UIEG Database")
        box.setText("Choose what to reset:")
        box.setIcon(QMessageBox.Icon.Question)
        repo_btn = box.addButton("Reset Repo / GitHub", QMessageBox.ButtonRole.AcceptRole)
        crawl_btn = box.addButton(
            "Reset Crawl / Website Import", QMessageBox.ButtonRole.AcceptRole
        )
        all_btn = box.addButton("Reset entire database", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == repo_btn:
            return CHANNEL_REPO
        if clicked == crawl_btn:
            return CHANNEL_CRAWL
        if clicked == all_btn:
            return "all"
        return None

    def _op_reset(self) -> None:
        mode = self._prompt_reset_mode()
        if mode is None:
            return

        if mode == CHANNEL_REPO:
            detail = (
                "This will DELETE all repo / GitHub captures and batches from uieg_capture.db.\n"
                "Crawl channel rows are kept.\n\n"
                "An automatic backup is created first.\n\nContinue?"
            )
            tag = "repo"
        elif mode == CHANNEL_CRAWL:
            detail = (
                "This will DELETE all crawl / website import captures and batches.\n"
                "Repo channel rows are kept.\n\n"
                "An automatic backup is created first.\n\nContinue?"
            )
            tag = "crawl"
        else:
            detail = (
                "This will DELETE all captures and batches from uieg_capture.db.\n\n"
                "An automatic backup is created first.\n\nContinue?"
            )
            tag = "all"

        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            detail,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            backup_path = auto_backup_before_reset(self.db_path, tag)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Backup failed",
                f"Could not create automatic backup before reset:\n{e}\n\nReset aborted.",
            )
            return

        try:
            if mode == "all":
                reset_all(self.db_path)
                msg = "Entire UIEG database cleared."
            else:
                caps, batches = reset_channel(self.db_path, mode)
                ch_label = "Repo / GitHub" if mode == CHANNEL_REPO else "Crawl / Website"
                msg = f"Reset {ch_label}: removed {caps} capture(s), {batches} batch(es)."
            if backup_path:
                msg += f"\n\nPre-reset backup:\n{backup_path}"
            self._notify_changed()
            QMessageBox.information(self, "Reset complete", msg)
        except Exception as e:
            QMessageBox.warning(self, "Reset failed", str(e))


def build_uieg_status_panel(
    theme: Dict[str, str],
    *,
    uieg_cfg: Optional[Dict[str, Any]] = None,
    on_db_changed: Optional[Callable[[], None]] = None,
) -> QWidget:
    panel = UiegStatusPanel(theme, uieg_cfg=uieg_cfg, on_db_changed=on_db_changed)
    panel.refresh = panel.refresh  # type: ignore[attr-defined]
    return panel
