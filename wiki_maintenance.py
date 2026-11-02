"""Console maintenance for ship_computer.db: scan roots, settings, profiles.

Extracted from the retired Spock-to-bridge monolith. `WikiMaintenancePanel` is
the tabbed hub Engineering Maintenance shows; the other classes are the dialogs
and tabs it owns.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db_browser import DatabaseManager
from spock_shell.paths import SHIP_COMPUTER_DB

__all__ = [
    "ConsoleProfilesTab",
    "ConsoleSettingsEditor",
    "DeleteScanRootsDialog",
    "HostRecipeTab",
    "ProviderCriteriaTab",
    "ScanRootsDialog",
    "TimingHistoryTab",
    "WikiMaintenancePanel",
]


class ScanRootsDialog(QDialog):
    """Modal dialog to maintain scan_roots (Spock_Console / scan_config.json)."""

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_config.json")
        self.db_path = SHIP_COMPUTER_DB
        self.setWindowTitle("Update Scan Roots")
        self.setMinimumSize(550, 400)
        self.setModal(True)
        self.roots = self._load_roots()
        self.init_ui()

    def _load_roots(self) -> list:
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
            return []

    def _save_roots(self):
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            settings_store.set(self.db_path, "scan.scan_roots", self.roots, by="maintenance")
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

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("SCAN ROOTS — FOLDERS TO INDEX")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Consolas", 10))
        for root in self.roots:
            self.list_widget.addItem(root)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        add_btn = QPushButton("Add Folder...")
        add_btn.setMinimumHeight(30)
        add_btn.clicked.connect(self.add_root)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("Delete Selected")
        del_btn.setMinimumHeight(30)
        del_btn.clicked.connect(self.delete_root)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        save_btn = QPushButton("Save")
        save_btn.setMinimumHeight(30)
        save_btn.setMinimumWidth(80)
        save_btn.clicked.connect(self.save_and_close)
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

    def add_root(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Scan Root Folder")
        if folder:
            folder = folder.replace("/", "\\")
            if folder not in self.roots:
                self.roots.append(folder)
                self.list_widget.addItem(folder)
                self.status_label.setText(f"Added: {folder}")
            else:
                self.status_label.setText("Already in scan roots")

    def delete_root(self):
        row = self.list_widget.currentRow()
        if row < 0:
            self.status_label.setText("Select a root to delete")
            return
        removed = self.list_widget.item(row).text()
        self.list_widget.takeItem(row)
        self.roots = [r for r in self.roots if r != removed]
        self.status_label.setText(f"Removed: {removed}")

    def save_and_close(self):
        self._save_roots()
        QMessageBox.information(
            self, "Saved",
            "Scan roots saved.\n\n"
            "Close and reopen the app for changes to take effect."
        )
        self.accept()


class DeleteScanRootsDialog(QDialog):
    """Modal dialog to purge indexed project roots from ship_computer.db"""

    def __init__(self, theme: dict, db_path: str, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.db_path = db_path
        self.setWindowTitle("Delete Scan Roots")
        self.setMinimumSize(600, 420)
        self.setModal(True)
        self.init_ui()
        self.apply_theme()
        self.refresh_list()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("DELETE SCAN ROOTS — PURGE INDEXED PROJECTS")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        hint = QLabel(
            "Select a project root indexed in ship_computer.db.\n"
            "Deleting removes all documents and related rows for that root."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Consolas", 10))
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumHeight(30)
        refresh_btn.clicked.connect(self.refresh_list)
        btn_row.addWidget(refresh_btn)
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setMinimumHeight(30)
        delete_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(30)
        close_btn.setMinimumWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def apply_theme(self):
        stylesheet = f"""
            QDialog {{
                background-color: {self.theme['bg']};
                color: {self.theme['fg']};
            }}
            QListWidget {{
                background-color: {self.theme['panel_bg']};
                color: {self.theme['fg']};
                border: 1px solid {self.theme['border']};
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
        self.setStyleSheet(stylesheet)

    def _get_roots_with_counts(self) -> list:
        """Return [(root_path, doc_count), ...] from documents.path."""
        if not os.path.exists(self.db_path):
            return []
        conn = sqlite3.connect(self.db_path, timeout=5)
        try:
            rows = conn.execute("""
                SELECT DISTINCT
                    CASE
                        WHEN INSTR(SUBSTR(path, 4), '\\') > 0
                        THEN SUBSTR(path, 1, 3 + INSTR(SUBSTR(path, 4), '\\') - 1)
                        ELSE path
                    END AS root_dir
                FROM documents
                WHERE path IS NOT NULL AND path != ''
                ORDER BY root_dir
            """).fetchall()
            result = []
            for (root,) in rows:
                count = conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE path LIKE ?",
                    (root + "%",),
                ).fetchone()[0]
                result.append((root, count))
            return result
        finally:
            conn.close()

    def _get_project_tables(self, conn, root: str) -> dict:
        counts = {}
        counts["documents"] = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE path LIKE ?", (root + "%",)
        ).fetchone()[0]
        doc_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM documents WHERE path LIKE ?", (root + "%",)
            ).fetchall()
        ]
        if not doc_ids:
            return counts
        id_list = ",".join(str(i) for i in doc_ids)
        for table, sql in [
            ("document_attachments", f"SELECT COUNT(*) FROM document_attachments WHERE doc_id IN ({id_list})"),
            ("document_tags", f"SELECT COUNT(*) FROM document_tags WHERE doc_id IN ({id_list})"),
            ("links", f"SELECT COUNT(*) FROM links WHERE src_doc_id IN ({id_list}) OR dst_doc_id IN ({id_list})"),
            ("captains_log", f"SELECT COUNT(*) FROM captains_log WHERE target_doc_id IN ({id_list})"),
            ("entity_mentions", f"SELECT COUNT(*) FROM entity_mentions WHERE doc_id IN ({id_list})"),
            ("memory_entities", f"SELECT COUNT(*) FROM memory_entities WHERE first_seen_doc_id IN ({id_list}) OR last_updated_doc_id IN ({id_list})"),
        ]:
            try:
                counts[table] = conn.execute(sql).fetchone()[0]
            except Exception:
                counts[table] = 0
        return counts

    def refresh_list(self):
        self.list_widget.clear()
        try:
            roots = self._get_roots_with_counts()
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            return
        if not roots:
            self.status_label.setText("No indexed project roots found")
            return
        for root, count in roots:
            item = QListWidgetItem(f"{root}  ({count} docs)")
            item.setData(Qt.ItemDataRole.UserRole, root)
            self.list_widget.addItem(item)
        self.status_label.setText(f"{len(roots)} project root(s)")

    def delete_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            self.status_label.setText("Select a root to delete")
            return
        root = item.data(Qt.ItemDataRole.UserRole)
        if not root:
            self.status_label.setText("Select a root to delete")
            return

        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            counts = self._get_project_tables(conn, root)
            conn.close()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        lines = [f"Project: {root}", "", "Rows to delete:"]
        total = 0
        for table, count in counts.items():
            if count > 0:
                lines.append(f"  {table}: {count}")
                total += count
        lines.append(f"  TOTAL: {total}")
        lines.append("")
        lines.append("This cannot be undone. Continue?")

        reply = QMessageBox.question(
            self,
            "Confirm Delete Scan Root",
            "\n".join(lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_label.setText("Cancelled")
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status_label.setText(f"Purging {root}...")
        try:
            deleted = self._purge_root(root)
            self.refresh_list()
            self.status_label.setText(f"Deleted {deleted} document(s) under {root}")
            QMessageBox.information(
                self,
                "Deleted",
                f"Purged project root:\n{root}\n\n{deleted} document(s) removed.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            self.status_label.setText(f"Error: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _purge_root(self, root: str) -> int:
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            doc_ids = [
                r[0]
                for r in conn.execute(
                    "SELECT id FROM documents WHERE path LIKE ?", (root + "%",)
                ).fetchall()
            ]
            if not doc_ids:
                return 0
            id_list = ",".join(str(i) for i in doc_ids)
            deletions = [
                f"DELETE FROM entity_mentions WHERE doc_id IN ({id_list})",
                f"DELETE FROM document_tags WHERE doc_id IN ({id_list})",
                f"DELETE FROM document_attachments WHERE doc_id IN ({id_list})",
                f"DELETE FROM links WHERE src_doc_id IN ({id_list}) OR dst_doc_id IN ({id_list})",
                f"DELETE FROM captains_log WHERE target_doc_id IN ({id_list})",
                f"DELETE FROM memory_entities WHERE first_seen_doc_id IN ({id_list}) OR last_updated_doc_id IN ({id_list})",
                f"DELETE FROM documents WHERE id IN ({id_list})",
            ]
            for sql in deletions:
                try:
                    conn.execute(sql)
                    conn.commit()
                except Exception:
                    pass
            try:
                from WarpCore.db import delete_documents_vec

                delete_documents_vec(conn, doc_ids)
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
                conn.commit()
            except Exception:
                pass
            return len(doc_ids)
        finally:
            conn.close()


class ConsoleSettingsEditor(QWidget):
    """Spock_Console settings grid — store-backed editor (read, edit, delete, import, export)."""

    COLUMNS = ("Variable_Name", "Variable_Type", "Value", "Updated", "By")

    def __init__(self, db_path: str, theme: dict, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.theme = theme
        self._rows: list = []
        self._masked = True
        self._filter = ""
        self.init_ui()
        self.refresh()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("search name, type, or value (e.g. 8080, scan., llama)")
        self.filter_edit.textChanged.connect(self._on_filter)
        head.addWidget(self.filter_edit, 1)
        reset_btn = QPushButton("Reset Filter")
        reset_btn.setMinimumHeight(28)
        reset_btn.clicked.connect(self.reset_filter)
        head.addWidget(reset_btn)
        self.reveal_cb = QCheckBox("Reveal secrets")
        self.reveal_cb.toggled.connect(self._on_reveal)
        head.addWidget(self.reveal_cb)
        layout.addLayout(head)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setFont(QFont("Consolas", 9))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        btns = QHBoxLayout()
        btns.addWidget(self._make_btn("Refresh", self.refresh))
        btns.addWidget(self._make_btn("Set Value…", self._on_set_value))
        btns.addWidget(self._make_btn("Clear to Empty", self._on_clear_value))
        btns.addWidget(self._make_btn("Delete Row…", self._on_delete))
        btns.addStretch()
        btns.addWidget(self._make_btn("Import from JSON…", self._on_import_json))
        btns.addWidget(self._make_btn("Export to JSON…", self._on_export_json))
        layout.addLayout(btns)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _make_btn(self, text, callback):
        btn = QPushButton(text)
        btn.setMinimumHeight(28)
        btn.clicked.connect(callback)
        return btn

    def set_filter(self, prefix: str = ""):
        self.filter_edit.setText(prefix)
        self._on_filter()

    def reset_filter(self):
        self.filter_edit.clear()
        self._on_filter()

    def _on_filter(self):
        self._filter = (self.filter_edit.text() or "").strip()
        self._populate()

    def _on_reveal(self):
        self._masked = not self.reveal_cb.isChecked()
        self._populate()

    def refresh(self):
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            root = os.path.dirname(os.path.abspath(__file__))
            report = settings_store.ensure_live_overlays_in_store(self.db_path, root=root)
            self._rows = list(settings_store.get_meta(self.db_path))
            filled = report.get("filled") or []
            msg = f"{len(self._rows)} setting(s)"
            if filled:
                msg += f" — imported {len(filled)} overlay key(s)"
            elif (report.get("scan") or {}).get("imported"):
                msg += " — imported scan.* from JSON"
            self.status_label.setText(msg)
        except Exception as e:
            self._rows = []
            self.status_label.setText(f"Error: {e}")
        self._populate()

    def _display_value(self, name: str, vtype: str, raw: str) -> str:
        if vtype == "secret":
            if self._masked:
                return "••••••••"
            return raw
        try:
            val = json.loads(raw)
            if isinstance(val, (dict, list)):
                return json.dumps(val, ensure_ascii=False)[:200]
        except (TypeError, ValueError):
            pass
        return raw

    def _row_matches_filter(self, name: str, vtype: str, raw: str, updated, by) -> bool:
        needle = (self._filter or "").strip().lower()
        if not needle:
            return True
        haystacks = (
            name or "",
            vtype or "",
            raw or "",
            self._display_value(name, vtype, raw or ""),
            str(updated or ""),
            str(by or ""),
        )
        return any(needle in str(h).lower() for h in haystacks)

    def _populate(self):
        self.table.setRowCount(0)
        filtered = [
            r
            for r in self._rows
            if self._row_matches_filter(r[0], r[1], r[2], r[3], r[4])
        ]
        self.table.setRowCount(len(filtered))
        for i, (name, vtype, raw, updated, by) in enumerate(filtered):
            for col, text in (
                (0, name),
                (1, vtype),
                (2, self._display_value(name, vtype, raw)),
                (3, str(updated or "")),
                (4, str(by or "")),
            ):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, name)
                    item.setData(Qt.ItemDataRole.UserRole + 1, vtype)
                self.table.setItem(i, col, item)
        self.table.resizeColumnsToContents()
        for col in range(len(self.COLUMNS)):
            if self.table.columnWidth(col) > 380:
                self.table.setColumnWidth(col, 380)

    def _selected_row(self) -> tuple:
        row = self.table.currentRow()
        if row < 0:
            return None
        name_item = self.table.item(row, 0)
        if name_item is None:
            return None
        return (
            str(name_item.data(Qt.ItemDataRole.UserRole)),
            str(name_item.data(Qt.ItemDataRole.UserRole + 1)),
        )

    def _on_set_value(self):
        sel = self._selected_row()
        if not sel:
            self.status_label.setText("Select a row first")
            return
        name, vtype = sel
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            current = settings_store.get(self.db_path, name, "")
        except Exception:
            current = ""
        if isinstance(current, (dict, list)):
            current = json.dumps(current, ensure_ascii=False)
        if vtype == "secret":
            text, ok = QInputDialog.getText(
                self, "Set secret", f"{name}\n\nEnter new value (empty clears):",
                QLineEdit.EchoMode.Password,
            )
        else:
            text, ok = QInputDialog.getText(
                self, "Set value", f"{name}\n\nValue:", text=str(current)
            )
        if not ok:
            return
        self._apply_value(name, text.strip())

    def _on_clear_value(self):
        sel = self._selected_row()
        if not sel:
            self.status_label.setText("Select a row first")
            return
        name, vtype = sel
        if vtype == "secret":
            reply = QMessageBox.question(
                self, "Clear secret",
                f"Clear secret '{name}' to empty?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._apply_value(name, "")

    def _apply_value(self, name: str, text: str):
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            settings_store.set(self.db_path, name, text, by="maintenance")
            self.status_label.setText(f"Set {name}")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Settings", f"Set failed:\n{e}")

    def _on_delete(self):
        sel = self._selected_row()
        if not sel:
            self.status_label.setText("Select a row first")
            return
        name, vtype = sel
        label = "secret" if vtype == "secret" else "setting"
        reply = QMessageBox.question(
            self, "Delete row",
            f"Delete {label} '{name}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            settings_store.delete(self.db_path, name)
            self.status_label.setText(f"Deleted {name}")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Settings", f"Delete failed:\n{e}")

    def _on_import_json(self):
        reply = QMessageBox.question(
            self, "Import from JSON",
            "Re-run migration from root config JSONs into Spock_Console?\n"
            "Existing rows are kept; JSON files will be archived to config_archive/.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            report = settings_store.migrate_from_json(
                self.db_path, root=os.path.dirname(self.db_path)
            )
            self.refresh()
            QMessageBox.information(
                self, "Import from JSON",
                f"Imported: {report.get('imported')}\n"
                f"Archived: {len(report.get('archived', []))}\n"
                f"Skipped: {report.get('skipped')}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Import from JSON", str(e))

    def _on_export_json(self):
        out_dir = QFileDialog.getExistingDirectory(
            self, "Export config to folder", os.path.dirname(self.db_path)
        )
        if not out_dir:
            return
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            written = settings_store.export_to_json(self.db_path, out_dir)
            self.status_label.setText("Exported")
            QMessageBox.information(
                self, "Export to JSON",
                "Exported:\n" + "\n".join(f"  {v}" for v in written.values()),
            )
        except Exception as e:
            QMessageBox.critical(self, "Export to JSON", str(e))


class HostRecipeTab(QWidget):
    """Create / Update audited host recipes (Launch GPU policy, -c, -np)."""

    HIST_COLS = ("Ver", "When", "By", "Reason", "Current")

    def __init__(self, db_path: str, theme: dict, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.theme = theme
        self._preview: dict | None = None
        self._history: list = []
        self.init_ui()
        self.refresh()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.drift_lbl = QLabel("")
        self.drift_lbl.setWordWrap(True)
        self.drift_lbl.setStyleSheet("color: #C44A4A; font-weight: bold;")
        self.drift_lbl.setVisible(False)
        layout.addWidget(self.drift_lbl)

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(180)
        self.summary.setFont(QFont("Consolas", 9))
        layout.addWidget(self.summary)

        btns = QHBoxLayout()
        self.create_btn = self._make_btn("Create recipe profile", self._create)
        self.update_btn = self._make_btn("Update recipe profile…", self._update)
        self.preview_btn = self._make_btn("Recompute preview", self._preview_recompute)
        self.refresh_btn = self._make_btn("Refresh", self.refresh)
        btns.addWidget(self.create_btn)
        btns.addWidget(self.update_btn)
        btns.addWidget(self.preview_btn)
        btns.addWidget(self.refresh_btn)
        btns.addStretch()
        layout.addLayout(btns)

        layout.addWidget(QLabel("History (newest first):"))
        self.table = QTableWidget(0, len(self.HIST_COLS))
        self.table.setHorizontalHeaderLabels(list(self.HIST_COLS))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setFont(QFont("Consolas", 9))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_hist_select)
        layout.addWidget(self.table, 1)

        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Consolas", 9))
        self.diff_view.setMaximumHeight(160)
        self.diff_view.setPlaceholderText("Select a history row to view recipe JSON…")
        layout.addWidget(self.diff_view)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _make_btn(self, text, callback):
        btn = QPushButton(text)
        btn.setMinimumHeight(28)
        btn.clicked.connect(callback)
        return btn

    def _format_recipe_block(self, row: dict | None, title: str) -> str:
        if not row:
            return f"{title}\n(none)\n"
        rec = row.get("recipe") or {}
        hw = row.get("hardware") or {}
        notes = rec.get("notes") or []
        note_txt = "\n".join(f"  - {n}" for n in notes) if notes else "  (none)"
        return (
            f"{title}\n"
            f"  version={row.get('version')}  id={row.get('id')}  "
            f"by={row.get('created_by')}  at={row.get('created_at')}\n"
            f"  reason: {row.get('reason') or '(none)'}\n"
            f"  hardware: RAM {hw.get('host_ram_gb')}GB · {hw.get('gpu_summary')}\n"
            f"  policy={rec.get('gpu_policy')}  split={rec.get('split_mode')} "
            f"ts={rec.get('tensor_split') or '-'}\n"
            f"  embed_gpu={rec.get('embed_gpu_index')}  chat_gpu={rec.get('chat_gpu_index')}\n"
            f"  embed_n_ctx={rec.get('embed_n_ctx')}  chat_n_ctx={rec.get('chat_n_ctx')}  "
            f"embed_np={rec.get('embed_np')}  ngl={rec.get('ngl_default')}\n"
            f"  embed_size_class={rec.get('embed_size_class')}\n"
            f"  notes:\n{note_txt}\n"
        )

    def refresh(self):
        from WarpCore import host_recipe as hr

        try:
            current = hr.get_current_recipe(self.db_path)
            self._history = hr.list_recipe_history(self.db_path, limit=100)
            live = hr.probe_hardware()
            drift = hr.hardware_drift(current, live=live) if current else []
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            self.summary.setPlainText(str(e))
            self.table.setRowCount(0)
            self.create_btn.setEnabled(True)
            self.update_btn.setEnabled(False)
            return

        self.create_btn.setEnabled(current is None)
        self.update_btn.setEnabled(current is not None)

        if drift:
            self.drift_lbl.setText(
                "Hardware drift vs current recipe — use Update recipe profile "
                "(does not apply automatically):\n• " + "\n• ".join(drift)
            )
            self.drift_lbl.setVisible(True)
        else:
            self.drift_lbl.clear()
            self.drift_lbl.setVisible(False)

        parts = [self._format_recipe_block(current, "CURRENT RECIPE")]
        if self._preview:
            parts.append(
                self._format_recipe_block(
                    {
                        "version": "(preview)",
                        "id": "-",
                        "created_by": "preview",
                        "created_at": "-",
                        "reason": "(not saved)",
                        "hardware": self._preview.get("_hardware") or {},
                        "recipe": {
                            k: v
                            for k, v in self._preview.items()
                            if k != "_hardware"
                        },
                    },
                    "PREVIEW (not saved)",
                )
            )
        else:
            parts.append(
                "PREVIEW (not saved)\n"
                "Click Recompute preview to see what Create/Update would write.\n"
            )
        self.summary.setPlainText("\n".join(parts))

        self.table.setRowCount(len(self._history))
        for r, row in enumerate(self._history):
            vals = (
                str(row.get("version") or ""),
                str(row.get("created_at") or ""),
                str(row.get("created_by") or ""),
                str(row.get("reason") or ""),
                "yes" if row.get("is_current") else "",
            )
            for c, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, row.get("id"))
                self.table.setItem(r, c, item)
        self.status_label.setText(
            f"{len(self._history)} version(s)"
            + ("; current v" + str(current.get("version")) if current else "; no current")
        )

    def _preview_recompute(self):
        from spock_shell.host_recipe_ui import propose_recipe_with_primary_prompt

        try:
            built = propose_recipe_with_primary_prompt(self)
            if built is None:
                return
            hw, rec = built
            rec = dict(rec)
            rec["_hardware"] = hw
            self._preview = rec
            self.status_label.setText("Preview recomputed (not saved).")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Recipe preview", str(e))

    def _create(self):
        from WarpCore import host_recipe as hr
        from spock_shell.host_recipe_ui import propose_recipe_with_primary_prompt

        if hr.get_current_recipe(self.db_path) is not None:
            QMessageBox.information(
                self,
                "Create recipe",
                "A current recipe already exists. Use Update instead.",
            )
            self.refresh()
            return
        try:
            built = propose_recipe_with_primary_prompt(self)
            if built is None:
                return
            hw, rec = built
            preview = json.dumps(rec, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Create recipe", str(e))
            return
        reply = QMessageBox.question(
            self,
            "Create recipe profile",
            "Create the first host recipe from a live hardware probe?\n\n"
            f"{preview[:1200]}{'…' if len(preview) > 1200 else ''}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            hr.create_recipe(
                self.db_path,
                hardware=hw,
                recipe=rec,
                reason="Initial host recipe",
                created_by="maintenance",
            )
            self._preview = None
            QMessageBox.information(self, "Create recipe", "Host recipe created.")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Create recipe", str(e))

    def _update(self):
        from WarpCore import host_recipe as hr
        from spock_shell.host_recipe_ui import propose_recipe_with_primary_prompt

        if hr.get_current_recipe(self.db_path) is None:
            QMessageBox.information(
                self,
                "Update recipe",
                "No current recipe. Use Create recipe profile first.",
            )
            self.refresh()
            return
        reason, ok = QInputDialog.getText(
            self,
            "Update recipe profile",
            "Reason for this update (required for audit trail):",
        )
        if not ok:
            return
        reason = (reason or "").strip()
        if not reason:
            QMessageBox.warning(
                self, "Update recipe", "A non-empty reason is required."
            )
            return
        try:
            built = propose_recipe_with_primary_prompt(self)
            if built is None:
                return
            hw, rec = built
            hr.update_recipe(
                self.db_path,
                reason=reason,
                hardware=hw,
                recipe=rec,
                created_by="maintenance",
            )
            self._preview = None
            QMessageBox.information(self, "Update recipe", "Host recipe updated.")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Update recipe", str(e))

    def _on_hist_select(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        if not item:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        from WarpCore import host_recipe as hr

        row = hr.get_recipe_by_id(self.db_path, int(rid or 0))
        if not row:
            self.diff_view.setPlainText("(not found)")
            return
        prev = None
        for h in self._history:
            if int(h.get("version") or 0) == int(row.get("version") or 0) - 1:
                prev = h
                break
        text = (
            f"=== v{row.get('version')} recipe ===\n"
            + json.dumps(row.get("recipe") or {}, indent=2)
        )
        if prev:
            text += (
                f"\n\n=== previous v{prev.get('version')} recipe ===\n"
                + json.dumps(prev.get("recipe") or {}, indent=2)
            )
        self.diff_view.setPlainText(text)


class ConsoleProfilesTab(QWidget):
    """Profiles list — delete / refresh against ship_computer.db (spock_profile)."""

    def __init__(self, db_path: str, theme: dict, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.theme = theme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        from spock_shell.profiles import ProfileReviewPanel

        layout.addWidget(ProfileReviewPanel(db_path, self), 1)


class TimingHistoryTab(QWidget):
    """Browse Ask AI / Deep Dive stage timings (ask_timing_history)."""

    COLUMNS = (
        "Time",
        "Category",
        "Question",
        "Response chars",
        "Total ms",
        "Retrieve",
        "Pack",
        "LLM",
        "Docs",
        "Inv",
        "Forced",
        "Budget used",
        "n_ctx",
        "Pack summary",
    )

    def __init__(self, db_path: str, theme: dict, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.theme = theme
        self._rows: list = []
        self.init_ui()
        self.refresh()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        tip = QLabel(
            "Stage timings for Ask AI and Deep Dive (ask_timing_history). "
            "Wiped by content DB reset; Spock_Console settings are kept. "
            "Response length is characters (v1)."
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        head = QHBoxLayout()
        head.addWidget(QLabel("Category:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("All", "")
        self.mode_combo.addItem("Ask AI", "ask")
        self.mode_combo.addItem("Deep Dive", "deep_dive")
        self.mode_combo.currentIndexChanged.connect(self.refresh)
        head.addWidget(self.mode_combo)
        head.addStretch()
        head.addWidget(self._make_btn("Refresh", self.refresh))
        head.addWidget(self._make_btn("Purge older than 30 days…", self._purge_30))
        head.addWidget(self._make_btn("Clear all…", self._clear_all))
        layout.addLayout(head)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setFont(QFont("Consolas", 9))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        layout.addWidget(self.table, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _make_btn(self, text, callback):
        btn = QPushButton(text)
        btn.setMinimumHeight(28)
        btn.clicked.connect(callback)
        return btn

    def refresh(self):
        from WarpCore.ask_timing_store import list_timings, mode_label

        mode = self.mode_combo.currentData()
        try:
            self._rows = list_timings(self.db_path, mode=mode or None, limit=500)
        except Exception as e:
            self._rows = []
            self.status_label.setText(f"Error: {e}")
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            created = row.get("created_at")
            try:
                ts = datetime.fromtimestamp(int(created or 0)).strftime("%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError, OSError):
                ts = str(created or "")
            q = (row.get("question") or "").replace("\n", " ")
            if len(q) > 80:
                q = q[:79] + "…"
            summary = (row.get("pack_summary") or "").replace("\n", " ")
            if len(summary) > 100:
                summary = summary[:99] + "…"
            budget_used = row.get("budget_used")
            pct = row.get("budget_used_pct")
            if budget_used is not None and pct is not None:
                budget_cell = f"{budget_used} ({pct:.0f}%)"
            elif budget_used is not None:
                budget_cell = str(budget_used)
            else:
                budget_cell = ""
            values = (
                ts,
                mode_label(str(row.get("mode") or "")),
                q,
                str(row.get("response_length") if row.get("response_length") is not None else ""),
                str(row.get("total_ms") if row.get("total_ms") is not None else ""),
                str(row.get("retrieve_ms") if row.get("retrieve_ms") is not None else ""),
                str(row.get("pack_ms") if row.get("pack_ms") is not None else ""),
                str(row.get("llm_ms") if row.get("llm_ms") is not None else ""),
                str(row.get("docs_used") if row.get("docs_used") is not None else ""),
                str(row.get("inventory_shown") if row.get("inventory_shown") is not None else ""),
                str(row.get("forced_count") if row.get("forced_count") is not None else ""),
                budget_cell,
                str(row.get("n_ctx") if row.get("n_ctx") is not None else ""),
                summary,
            )
            for c, text in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        self.status_label.setText(f"{len(self._rows)} row(s)")

    def _purge_30(self):
        self._purge(days=30, label="older than 30 days")

    def _clear_all(self):
        self._purge(days=0, label="ALL timing rows")

    def _purge(self, days: int, label: str):
        reply = QMessageBox.question(
            self,
            "Purge timing history",
            f"Delete {label} from ask_timing_history?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from WarpCore.ask_timing_store import purge_older_than_days

            n = purge_older_than_days(days, self.db_path)
            self.status_label.setText(f"Deleted {n} row(s)")
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Purge failed", str(e))


class ProviderCriteriaTab(QWidget):
    """Edit ``llmfit_session_criteria`` provider allow-list (empty = ALL)."""

    def __init__(self, theme: dict | None = None, parent=None):
        super().__init__(parent)
        self.theme = theme or {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        tip = QLabel(
            "Provider allow-list for Bringup Acquire, HF Models, and Launch. "
            "Zero rows = ALL providers. Non-empty list hard-excludes other "
            "publishers (e.g. Google alone drops Qwen / Nvidia / Microsoft)."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.status = QLabel("")
        self.status.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.status)

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        lay.addWidget(self.list, 1)

        add_row = QHBoxLayout()
        self.seed = QComboBox()
        self.seed.setEditable(True)
        try:
            from llmfit_session_criteria import KNOWN_PROVIDER_NAMES

            self.seed.addItems(list(KNOWN_PROVIDER_NAMES))
        except Exception:
            self.seed.addItems(["Google", "Alibaba", "Nvidia", "Microsoft", "Meta"])
        add_row.addWidget(self.seed, 1)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add)
        add_row.addWidget(add_btn)
        lay.addLayout(add_row)

        btns = QHBoxLayout()
        del_btn = QPushButton("Delete selected")
        del_btn.clicked.connect(self._delete)
        clear_btn = QPushButton("Clear filter (ALL)")
        clear_btn.clicked.connect(self._clear)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        for b in (del_btn, clear_btn, save_btn, refresh_btn):
            btns.addWidget(b)
        btns.addStretch()
        lay.addLayout(btns)
        self.refresh()

    def _names_from_list(self) -> list[str]:
        names: list[str] = []
        for i in range(self.list.count()):
            text = (self.list.item(i).text() or "").strip()
            if text and text not in names:
                names.append(text)
        return names

    def _update_status(self) -> None:
        names = self._names_from_list()
        if not names:
            self.status.setText("Filtering: ALL (no providers)")
        else:
            self.status.setText("Filtering: " + ", ".join(names))

    def refresh(self) -> None:
        try:
            from llmfit_session_criteria import load_criteria, provider_allowlist

            load_criteria(refresh=True)
            names = provider_allowlist()
        except Exception as e:
            self.status.setText(f"Load failed: {e}")
            return
        self.list.clear()
        for name in names:
            self.list.addItem(name)
        self._update_status()

    def _add(self) -> None:
        name = (self.seed.currentText() or "").strip()
        if not name:
            return
        existing = {self.list.item(i).text().lower() for i in range(self.list.count())}
        if name.lower() in existing:
            return
        self.list.addItem(name)
        self._update_status()

    def _delete(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._update_status()

    def _clear(self) -> None:
        self.list.clear()
        self._update_status()

    def _save(self) -> None:
        try:
            from llmfit_session_criteria import set_providers

            set_providers(self._names_from_list())
            self.refresh()
            QMessageBox.information(
                self,
                "Providers saved",
                f"Provider filter is now: {self.status.text().replace('Filtering: ', '')}",
            )
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))


class WikiMaintenancePanel(QWidget):
    """Ship computer maintenance — combined action tabs + Settings + Config Profiles."""

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.db_path = SHIP_COMPUTER_DB
        self.stats_display = None  # Overview lives on Ship Computer DB Health
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        self.tabs = QTabWidget()

        # Scan Roots + List Roots + Delete Roots
        self.tabs.addTab(
            self._build_multi_action_tab(
                "Scan Roots",
                "Manage which folders Wiki Agent indexes, list configured scan roots "
                "(with document counts), or delete indexed roots.",
                [
                    (
                        "Update Scan Roots",
                        "Add or remove folders that Wiki Agent / ingest should scan.",
                        self.op_update_scan_roots,
                    ),
                    (
                        "List Project Roots",
                        "Show distinct project root folders already indexed in ship_computer.db.",
                        self.op_list_roots,
                    ),
                    (
                        "Delete Scan Roots",
                        "Remove selected scan roots and optionally purge related documents.",
                        self.op_delete_scan_roots,
                    ),
                ],
            ),
            "Scan Roots",
        )

        # Backup / Restore / Reindex / Purge / Reset (Reset auto-backs up first)
        self.tabs.addTab(
            self._build_multi_action_tab(
                "Database",
                "Backup, restore, reindex, purge missing files, clear embeddings for "
                "re-embed, or reset ship_computer.db. "
                "Reset offers (a) corpus/logs only — keep settings+profiles, or "
                "(b) recreate ALL tables. Always creates an automatic backup first.",
                [
                    (
                        "Backup Database",
                        "Copy ship_computer.db into the backups/ folder with a timestamp.",
                        self.op_backup,
                    ),
                    (
                        "Restore Database",
                        "Overwrite the current database from a prior backup (destructive).",
                        self.op_restore,
                    ),
                    (
                        "Reindex Database",
                        "Rebuild FTS5, run ANALYZE, then VACUUM ship_computer.db.",
                        self.op_reindex,
                    ),
                    (
                        "Purge Missing",
                        "Remove documents whose files no longer exist under scan roots.",
                        self.op_purge_missing_content,
                    ),
                    (
                        "Clear Embeddings (re-embed)",
                        "Null document vectors and clear kb_embedding_corpus only — "
                        "keeps documents, settings, and profiles. Then launch the new "
                        "GGUF on :8080 and run Wiki Scan.",
                        self.op_clear_embeddings,
                    ),
                    (
                        "Reset Database",
                        "Automatic backup, then choose: (a) wipe corpus/logs only "
                        "(keep settings + profiles), or (b) recreate ALL tables from schema.",
                        self.op_reset_db,
                    ),
                ],
            ),
            "Database",
        )

        # Codebase knowledge (awesome-copilot acquire-codebase-knowledge)
        self.tabs.addTab(
            self._build_multi_action_tab(
                "Codebase Knowledge",
                "Run a deterministic codebase scan and write seven docs under "
                "docs/codebase/ (STACK, STRUCTURE, ARCHITECTURE, CONVENTIONS, "
                "INTEGRATIONS, TESTING, CONCERNS). Queues Wiki Agent onboarding "
                "so the docs can be embedded for Ask AI / Deep Dive.",
                [
                    (
                        "Acquire Codebase Knowledge",
                        "Pick a project root, optional focus area, write docs/codebase "
                        "markdown, and queue ingest.",
                        self.op_acquire_codebase_knowledge,
                    ),
                ],
            ),
            "Codebase Knowledge",
        )

        # Scan Settings + Settings
        settings_wrap = QWidget()
        settings_lay = QVBoxLayout(settings_wrap)
        settings_lay.setContentsMargins(8, 8, 8, 8)
        settings_lay.setSpacing(8)
        tip = QLabel(
            "Spock Console settings live in ship_computer.db. Refresh / Import overlays "
            "pulls leftover scan_config.json, wiki_agent_session.json, .env secrets "
            "(HF_TOKEN, API keys), and first_models_last.json paths when keys are empty. "
            "spock_ready_last.json is status-only and is not imported."
        )
        tip.setWordWrap(True)
        settings_lay.addWidget(tip)
        shortcut_defs = (
            ("Scan Settings", "scan."),
            ("Embedding Profile", "app.embedding_profile"),
            ("MCP", "app.mcp"),
            ("RAG API", "app.rag_api"),
            ("Search Keys", "app.search"),
            ("UIEG", "app.uieg"),
            ("Ctx - Context", "app.ctx"),
            ("HF Token", "hf."),
            ("Llama", "app.llama"),
            ("OpenAI Compat", "app.openai_compat"),
            ("Secrets", "api_key"),
        )
        for row_defs in (shortcut_defs[:6], shortcut_defs[6:]):
            row = QHBoxLayout()
            for label, prefix in row_defs:
                btn = self._make_btn(
                    label,
                    lambda _=False, p=prefix, n=label: self._jump_settings_filter(p, n),
                    kind="run",
                )
                row.addWidget(btn)
            row.addStretch()
            settings_lay.addLayout(row)
        import_row = QHBoxLayout()
        import_row.addWidget(
            self._make_btn(
                "Import .env / JSON overlays",
                self.op_import_overlays,
                kind="run",
            )
        )
        import_row.addStretch()
        settings_lay.addLayout(import_row)
        self.settings_editor = ConsoleSettingsEditor(self.db_path, theme=self.theme)
        settings_lay.addWidget(self.settings_editor, 1)
        self.tabs.addTab(settings_wrap, "Settings")

        # Provider allow-list (Acquire / HF Models / Launch)
        self.provider_tab = ProviderCriteriaTab(theme=self.theme)
        self.tabs.addTab(self.provider_tab, "Provider")

        # Ask AI / Deep Dive timing history
        self.timing_tab = TimingHistoryTab(self.db_path, theme=self.theme)
        self.tabs.addTab(self.timing_tab, "Timing")

        # Host recipe (Launch defaults; audited Create/Update)
        recipe_wrap = QWidget()
        recipe_lay = QVBoxLayout(recipe_wrap)
        recipe_lay.setContentsMargins(8, 8, 8, 8)
        recipe_lay.setSpacing(8)
        recipe_tip = QLabel(
            "Host recipe profiles encode machine capability for Launch defaults "
            "(GPU policy, tensor-split, -c, embed -np). Separate from session "
            "Spock Config Profiles. Create once; Update only with an explicit reason "
            "(audit trail). Hardware drift is shown but never auto-applies."
        )
        recipe_tip.setWordWrap(True)
        recipe_lay.addWidget(recipe_tip)
        self.recipe_tab = HostRecipeTab(self.db_path, theme=self.theme)
        recipe_lay.addWidget(self.recipe_tab, 1)
        self.tabs.addTab(recipe_wrap, "Recipe")

        # Spock Config Profiles (Embedding Health lives on Ship Computer DB Health)
        profiles_wrap = QWidget()
        profiles_lay = QVBoxLayout(profiles_wrap)
        profiles_lay.setContentsMargins(8, 8, 8, 8)
        profiles_lay.setSpacing(8)
        profiles_tip = QLabel(
            "Manage saved Spock configuration profiles in ship_computer.db "
            "(spock_profile). Use Load Selected Profile to restore settings and "
            "start only the services that profile needs (no duplicate PIDs). "
            "Embedding Health is under 2 Ship Computer DB Health → spock_health."
        )
        profiles_tip.setWordWrap(True)
        profiles_lay.addWidget(profiles_tip)
        self.profiles_tab = ConsoleProfilesTab(self.db_path, theme=self.theme)
        profiles_lay.addWidget(self.profiles_tab, 1)
        self.tabs.addTab(profiles_wrap, "Spock Config Profiles")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.tabs)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        name = self.tabs.tabText(index)
        if name == "Timing" and hasattr(self, "timing_tab"):
            self.timing_tab.refresh()
        elif name == "Recipe" and hasattr(self, "recipe_tab"):
            self.recipe_tab.refresh()
        elif name == "Provider" and hasattr(self, "provider_tab"):
            self.provider_tab.refresh()

    def _build_multi_action_tab(
        self, title: str, intro: str, actions: list
    ) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        heading = QLabel(title)
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        layout.addWidget(heading)
        body = QLabel(intro)
        body.setWordWrap(True)
        layout.addWidget(body)
        for action_title, tip, callback in actions:
            box = QWidget()
            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(0, 4, 0, 4)
            box_lay.setSpacing(4)
            sub = QLabel(action_title)
            sf = QFont()
            sf.setBold(True)
            sub.setFont(sf)
            box_lay.addWidget(sub)
            tip_lbl = QLabel(tip)
            tip_lbl.setWordWrap(True)
            tip_lbl.setStyleSheet("color: #aaa;")
            box_lay.addWidget(tip_lbl)
            row = QHBoxLayout()
            row.addWidget(self._make_btn(f"Run {action_title}", callback, kind="run"))
            row.addStretch()
            box_lay.addLayout(row)
            layout.addWidget(box)
        layout.addStretch()
        return tab

    def _build_overview_tab(self) -> QWidget:
        """Shared overview builder (used by Ship Computer DB Health)."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title = QLabel("SHIP COMPUTER — DATABASE OVERVIEW")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        tip = QLabel(
            "Document / queue / captains_log counts for ship_computer.db. "
            "Refresh after Wiki Scan or maintenance actions."
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.stats_display = QTextEdit()
        self.stats_display.setReadOnly(True)
        self.stats_display.setFont(QFont("Consolas", 10))
        layout.addWidget(self.stats_display, 1)

        row = QHBoxLayout()
        row.addWidget(self._make_btn("Refresh Stats", self.refresh_stats, kind="accent"))
        row.addStretch()
        layout.addLayout(row)
        return tab

    def _build_action_tab(self, title: str, tip: str, callback) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        heading = QLabel(title)
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        layout.addWidget(heading)
        body = QLabel(tip)
        body.setWordWrap(True)
        layout.addWidget(body)
        row = QHBoxLayout()
        row.addWidget(
            self._make_btn(f"Run {title}", callback, kind="run")
        )
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        return tab

    def _make_btn(self, text, callback, *, kind: str = "accent"):
        """Compact action button (content-sized, not full-width)."""
        btn = QPushButton(text)
        btn.setMinimumHeight(32)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setProperty("maint_kind", "run" if kind == "run" else "accent")
        btn.clicked.connect(callback)
        return btn

    def open_settings_tab(self, prefix: str = ""):
        if (prefix or "").startswith("app.ctx"):
            try:
                from WarpCore.settings_store import ensure_ctx_defaults_in_store

                ensure_ctx_defaults_in_store(self.db_path)
                self.settings_editor.refresh()
            except Exception:
                pass
        # Settings editor is nested inside the combined Settings tab
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Settings":
                self.tabs.setCurrentIndex(i)
                break
        self.settings_editor.set_filter(prefix)

    def apply_theme(self):
        accent = self.theme.get("accent", "#5C6BC0")
        accent_hover = self.theme.get("accent_hover", "#3F51B5")
        fg = self.theme.get("fg", "#FFFFFF")
        bg = self.theme.get("bg", "#1e1e1e")
        panel = self.theme.get("panel_bg", "#2d2d2d")
        border = self.theme.get("border", "#444444")
        stylesheet = f"""
            QWidget {{
                background-color: {bg};
                color: {fg};
            }}
            QTextEdit {{
                background-color: {panel};
                color: {fg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
            QPushButton {{
                background-color: {accent};
                color: {fg};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {accent_hover};
            }}
            QPushButton[maint_kind="run"] {{
                background-color: #6D9E5A;
                color: #FFFFFF;
            }}
            QPushButton[maint_kind="run"]:hover {{
                background-color: #5A8A4A;
            }}
            QLabel {{
                color: {fg};
            }}
            QTabWidget::pane {{
                border: 1px solid {border};
                top: -1px;
            }}
            QTabBar::tab {{
                background: {panel};
                color: {fg};
                border: 1px solid {border};
                padding: 8px 12px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: #5C6BC0;
                color: #FFFFFF;
                font-weight: bold;
                border-color: #5C6BC0;
            }}
            QTabBar::tab:hover:!selected {{
                background: {accent_hover};
                color: #FFFFFF;
            }}
        """
        self.setStyleSheet(stylesheet)

    def _db_info(self) -> dict:
        if not os.path.exists(self.db_path):
            return {"exists": False}
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            emb = conn.execute("SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL").fetchone()[0]
            logs = conn.execute("SELECT COUNT(*) FROM captains_log").fetchone()[0]
            queue = conn.execute("SELECT COUNT(*) FROM agent_queue").fetchone()[0]
            quar = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
            conn.close()
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            return {"exists": True, "docs": docs, "emb": emb, "logs": logs,
                    "queue": queue, "quar": quar, "size_mb": size_mb}
        except Exception as e:
            return {"exists": True, "error": str(e)}

    def refresh_stats(self):
        if self.stats_display is None:
            return
        info = self._db_info()
        if not info.get("exists"):
            self.stats_display.setPlainText(f"Database not found:\n{self.db_path}")
            return
        if "error" in info:
            self.stats_display.setPlainText(f"Error reading database:\n{info['error']}")
            return
        stats = (
            f"  Database: {os.path.basename(self.db_path)}\n"
            f"  Size:     {info['size_mb']:.1f} MB\n"
            f"  Documents:       {info['docs']:>6d}  ({info['emb']} with embeddings)\n"
            f"  Captains log:    {info['logs']:>6d}\n"
            f"  Agent queue:     {info['queue']:>6d}\n"
            f"  Quarantine:      {info['quar']:>6d}"
        )
        self.stats_display.setPlainText(stats)
        self.status_label.setText("Stats refreshed")

    def op_purge_missing_content(self):
        """Quick-scan scan roots; purge documents whose files no longer exist."""
        from db_maintenance import load_scan_roots, purge_missing_content

        roots = load_scan_roots()
        if not roots:
            QMessageBox.warning(
                self,
                "Purge DB Missing Content",
                "No scan roots found in scan_config.json.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Purge DB Missing Content",
            "Quick-scan scan roots and remove documents whose files "
            "no longer exist on disk?\n\n"
            "Roots:\n  - "
            + "\n  - ".join(roots)
            + "\n\nRelated rows (tags, links, attachments, log targets) "
            "are removed with each document.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_label.setText("Purge cancelled")
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status_label.setText("Scanning for missing files…")
        QApplication.processEvents()
        try:
            result = purge_missing_content(self.db_path, roots=roots)
        except Exception as e:
            QMessageBox.critical(self, "Purge DB Missing Content", str(e))
            self.status_label.setText(f"Purge failed: {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        if result.get("error"):
            QMessageBox.warning(self, "Purge DB Missing Content", result["error"])
            self.status_label.setText(result["error"])
            self.refresh_stats()
            return

        purged = int(result.get("purged") or 0)
        missing = int(result.get("missing") or 0)
        checked = int(result.get("checked") or 0)
        sample = result.get("paths") or []
        msg_lines = [
            f"Checked {checked} document path(s) under {len(roots)} scan root(s).",
            f"Missing on disk: {missing}",
            f"Purged from ship_computer.db: {purged}",
        ]
        if sample:
            msg_lines.append("")
            msg_lines.append("Examples:")
            for p in sample[:12]:
                msg_lines.append(f"  • {p}")
            if missing > 12:
                msg_lines.append(f"  …and {missing - 12} more")
        QMessageBox.information(self, "Purge DB Missing Content", "\n".join(msg_lines))
        self.status_label.setText(
            f"Purged {purged} missing document(s) (checked {checked})"
        )
        self.refresh_stats()

    def op_update_scan_roots(self):
        dialog = ScanRootsDialog(self.theme, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.status_label.setText("Scan roots updated")

    def op_status(self):
        info = self._db_info()
        if "error" in info:
            QMessageBox.warning(self, "Error", info["error"])
            return
        tables = ["documents", "document_attachments", "tags", "document_tags",
                  "links", "captains_log", "quarantine", "agent_queue",
                  "ask_timing_history", "memory_entities", "entity_mentions", "config"]
        lines = [f"  Database: {os.path.basename(self.db_path)}",
                 f"  Size:     {info['size_mb']:.1f} MB", "",
                 f"  {'Table':<25s} {'Rows':>8s}",
                 f"  {'─'*25} {'─'*8}"]
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            for t in tables:
                try:
                    n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                    lines.append(f"  {t:<25s} {n:>8d}")
                except Exception:
                    lines.append(f"  {t:<25s} (missing)")
            conn.close()
        except Exception as e:
            lines.append(f"  Error: {e}")
        QMessageBox.information(self, "Database Status", "\n".join(lines))

    def op_list_roots(self):
        try:
            from db_maintenance import format_configured_scan_roots

            text = format_configured_scan_roots(self.db_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        QMessageBox.information(self, "Scan Roots", text)

    def op_acquire_codebase_knowledge(self):
        """Scan a project root and write docs/codebase/*.md for Ask AI ingest."""
        from spock_shell.paths import ROOT as SPOCK_ROOT

        default = str(SPOCK_ROOT) if SPOCK_ROOT else ""
        root = QFileDialog.getExistingDirectory(
            self,
            "Select project root to map / document",
            default,
        )
        if not root:
            self.status_label.setText("Acquire Codebase Knowledge cancelled")
            return
        focus, ok = QInputDialog.getText(
            self,
            "Focus area (optional)",
            "Optional focus (e.g. architecture only, testing and concerns).\n"
            "Leave blank to cover all seven docs:",
        )
        if not ok:
            self.status_label.setText("Acquire Codebase Knowledge cancelled")
            return
        focus = (focus or "").strip()
        ingest = (
            QMessageBox.question(
                self,
                "Queue Wiki ingest?",
                "Write docs under docs/codebase/ and queue Wiki Agent "
                "onboarding so they can be embedded for Ask AI?\n\n"
                "(If Wiki Scan is not running, start it after this so the "
                "queue is processed.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        )
        from spock_shell.busy_ui import clear_override_cursors
        from PyQt6.QtWidgets import QApplication

        clear_override_cursors()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status_label.setText("Acquire Codebase Knowledge — scanning…")
        QApplication.processEvents()
        try:
            from wiki_agent import Skills

            result = Skills.acquire_codebase_knowledge(
                {
                    "root_path": root,
                    "focus": focus,
                    "output_rel": "docs/codebase",
                    "ingest": ingest,
                }
            )
        except Exception as e:
            clear_override_cursors()
            QMessageBox.warning(self, "Acquire Codebase Knowledge", str(e))
            self.status_label.setText("Acquire Codebase Knowledge failed")
            return
        finally:
            clear_override_cursors()

        ok_flag = bool(getattr(result, "ok", False))
        evidence = str(getattr(result, "evidence", "") or "")
        lines = list(getattr(result, "log_lines", None) or [])
        written = [ln[6:] for ln in lines if str(ln).startswith("wrote:")]
        body = evidence or ("OK" if ok_flag else "Failed")
        if written:
            body += "\n\nFiles:\n" + "\n".join(f"  • {p}" for p in written)
        if ok_flag:
            QMessageBox.information(self, "Acquire Codebase Knowledge", body)
            self.status_label.setText(
                f"Acquire Codebase Knowledge — {len(written)} doc(s) written"
            )
        else:
            QMessageBox.warning(self, "Acquire Codebase Knowledge", body)
            self.status_label.setText("Acquire Codebase Knowledge failed")

    def op_reindex(self):
        reply = QMessageBox.question(
            self, "Reindex", "Rebuild FTS5 index, run ANALYZE and VACUUM?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
            conn.commit()
            conn.execute("ANALYZE")
            conn.commit()
            conn.close()
            # VACUUM in-process (avoid python -c with Windows paths like D:\Spock…).
            vac = sqlite3.connect(self.db_path, timeout=30)
            try:
                vac.execute("VACUUM")
            finally:
                vac.close()
            self.refresh_stats()
            QMessageBox.information(self, "Done", "Reindex complete.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def op_backup(self):
        backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"ship_computer_{ts}.db")
        try:
            src = sqlite3.connect(self.db_path, timeout=5)
            dst = sqlite3.connect(backup_path)
            src.backup(dst)
            dst.close()
            src.close()
            sz = os.path.getsize(backup_path) / (1024 * 1024)
            QMessageBox.information(self, "Backup", f"Backup complete:\n{backup_path}\n{sz:.1f} MB")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def op_restore(self):
        backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
        if not os.path.isdir(backup_dir):
            QMessageBox.information(self, "Restore", "No backups directory found.")
            return
        backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("ship_computer_") and f.endswith(".db")])
        if not backups:
            QMessageBox.information(self, "Restore", "No backups found.")
            return
        item, ok = QInputDialog.getItem(
            self, "Restore", "Select backup:", backups, len(backups) - 1, False
        )
        if not ok:
            return
        reply = QMessageBox.question(
            self, "Confirm", f"This will OVERWRITE the current database.\nRestore from {item}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import shutil
            for suffix in ["", "-wal", "-shm"]:
                f = self.db_path + suffix if suffix else self.db_path
                if os.path.exists(f):
                    os.remove(f)
            shutil.copy2(os.path.join(backup_dir, item), self.db_path)
            self.refresh_stats()
            QMessageBox.information(self, "Done", f"Restored: {item}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def op_test_embeddings(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_embeddings.py")
        if not os.path.exists(script):
            QMessageBox.warning(self, "Error", f"Not found: {script}")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status_label.setText("Running test embeddings...")
        try:
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=300,
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            output = result.stdout + "\n" + result.stderr
            self._show_output_dialog("Embedding Health", output.strip())
            self.status_label.setText("Embedding Health complete")
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, "Timeout", "test_embeddings.py timed out after 300s")
            self.status_label.setText("Embedding Health timed out")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            self.status_label.setText(f"Error: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _show_output_dialog(self, title: str, text: str):
        """Show a scrollable output viewer with Select All / Copy."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(750, 500)
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(10, 10, 10, 10)
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setFont(QFont("Consolas", 10))
        viewer.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        viewer.setPlainText(text)
        layout.addWidget(viewer)
        btn_row = QHBoxLayout()
        select_btn = QPushButton("Select All")
        select_btn.setMinimumWidth(90)
        select_btn.clicked.connect(viewer.selectAll)
        btn_row.addWidget(select_btn)
        copy_btn = QPushButton("Copy")
        copy_btn.setMinimumWidth(70)
        copy_btn.setToolTip("Copy all text to the clipboard")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(viewer.toPlainText())
        )
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(70)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec()

    def op_edit_config(self):
        # Console Maintenance — Settings tab filtered to scan.* (store-backed editor)
        self._jump_settings_filter("scan.", "Scan Settings")

    def _jump_settings_filter(self, prefix: str, label: str = "") -> None:
        self.open_settings_tab(prefix)
        self.status_label.setText(f"Filter: {label or prefix}")

    def op_import_overlays(self) -> None:
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            root = os.path.dirname(os.path.abspath(__file__))
            report = settings_store.ensure_live_overlays_in_store(self.db_path, root=root)
            self.settings_editor.refresh()
            filled = report.get("filled") or []
            scan = report.get("scan") or {}
            lines = [
                f"Filled / created: {len(filled)}",
                *([f"  • {k}" for k in filled[:20]] or ["  (none — already in DB)"]),
                f"Scan import: {scan}",
                f"wiki_agent.session imported: {report.get('wiki_session')}",
                f"hf.token row ensured: {report.get('hf_token_row')}",
                f"Skipped status JSON: {', '.join(report.get('skipped_status_json') or [])}",
            ]
            QMessageBox.information(self, "Import overlays", "\n".join(lines))
            self.status_label.setText("Overlay import finished")
        except Exception as e:
            QMessageBox.warning(self, "Import overlays", str(e))

    def op_delete_scan_roots(self):
        dialog = DeleteScanRootsDialog(self.theme, self.db_path, parent=self)
        dialog.exec()
        self.refresh_stats()
        self.status_label.setText("Delete scan roots closed")

    def op_clear_embeddings(self):
        """Null document vectors + clear kb_embedding_corpus (keep documents)."""
        reply = QMessageBox.question(
            self,
            "Clear Embeddings (re-embed)",
            "Clear all document embeddings and kb_embedding_corpus?\n\n"
            "This keeps documents, settings, and profiles.\n"
            "It does NOT wipe captains_log / queue (unlike Reset content).\n\n"
            "Afterward: launch the new embedding GGUF on :8080, then Run Wiki Scan.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_label.setText("Clear embeddings cancelled")
            return

        from spock_shell.busy_ui import busy_scope, clear_override_cursors

        try:
            from spock_rag_adapter.reembed import clear_embeddings, format_clear_result

            with busy_scope(self, "Clearing embeddings…"):
                result = clear_embeddings(self.db_path)
            clear_override_cursors()
            text = format_clear_result(result)
            self._show_output_dialog("Clear Embeddings (re-embed)", text)
            self.status_label.setText(
                f"Cleared embeddings "
                f"({result.get('embeddings_before')} → {result.get('embeddings_after')})"
            )
            self.refresh_stats()
        except Exception as e:
            clear_override_cursors()
            QMessageBox.warning(self, "Clear Embeddings", str(e))
            self.status_label.setText(f"Error: {e}")

    def op_reset_db(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reset.py")
        if not os.path.exists(script):
            QMessageBox.warning(self, "Error", f"Not found: {script}")
            return

        mode = self._prompt_reset_mode()
        if mode is None:
            return

        if mode == "content":
            detail = (
                "CONTENT reset will:\n"
                "• Delete documents, embeddings, FTS, captains_log, agent_queue,\n"
                "  quarantine, ask_timing_history, tags, links, memory entities,\n"
                "  kb_embedding_corpus, and spock_host_recipe\n"
                "• Drop/rebuild indexes and FTS, then VACUUM\n"
                "• Drop the sqlite-vec vector index (rebuilt on next embedding pass)\n"
                "• KEEP Spock_Console settings and spock_profile rows\n"
                "• After reset: re-probe hardware and recreate the host recipe\n"
                "  (multi-GPU hosts are asked which card is primary for AI)\n\n"
                "An automatic backup is created first.\n\nContinue?"
            )
        else:
            detail = (
                "FULL reset will:\n"
                "• DELETE and recreate ship_computer.db from ship_computer_schema.sql\n"
                "• Wipe settings (Spock_Console) and profiles as well\n"
                "• Clear captains_log.md / index.md\n\n"
                "An automatic backup is created first.\n\nContinue?"
            )
        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            detail,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Automatic backup before destructive reset
        try:
            backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(
                backup_dir, f"ship_computer_pre_reset_{mode}_{ts}.db"
            )
            if os.path.isfile(self.db_path):
                src = sqlite3.connect(self.db_path, timeout=5)
                dst = sqlite3.connect(backup_path)
                src.backup(dst)
                dst.close()
                src.close()
                self.status_label.setText(f"Pre-reset backup: {backup_path}")
        except Exception as e:
            QMessageBox.warning(
                self,
                "Backup failed",
                f"Could not create automatic backup before reset:\n{e}\n\nReset aborted.",
            )
            return

        # Close the app's DB connection so reset can rename/lock the file
        import gc

        main = self.window()
        if hasattr(main, "db_manager") and main.db_manager:
            main.db_manager.close()
            main.db_manager = None
        gc.collect()

        self.status_label.setText(f"Running reset.py --mode {mode}...")
        try:
            result = subprocess.run(
                [sys.executable, script, "--mode", mode],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            self._show_output_dialog(f"Reset Database ({mode})", output.strip())

            if hasattr(main, "db_manager") and main.db_manager is None:
                try:
                    main.db_manager = DatabaseManager(SHIP_COMPUTER_DB)
                except Exception:
                    pass

            if mode == "full":
                # Schema recreate omits Spock_Console — re-seed overlays if JSON/.env exist
                try:
                    import _warpcore_path

                    _warpcore_path.ensure()
                    from WarpCore import settings_store

                    root = os.path.dirname(os.path.abspath(__file__))
                    settings_store.ensure_live_overlays_in_store(self.db_path, root=root)
                    if hasattr(self, "settings_editor"):
                        self.settings_editor.refresh()
                except Exception:
                    pass

            if mode in ("content", "full") and result.returncode == 0:
                self._rebuild_host_recipe_after_reset()

            self.refresh_stats()
            self.status_label.setText(f"Reset complete ({mode})")
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, "Timeout", "reset.py timed out after 180s")
            self.status_label.setText("Reset timed out")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            self.status_label.setText(f"Error: {e}")

    def _rebuild_host_recipe_after_reset(self) -> None:
        """Re-probe hardware and create a fresh host recipe (asks primary AI GPU)."""
        try:
            from PyQt6.QtWidgets import QApplication

            from spock_shell.host_recipe_ui import create_or_confirm_host_recipe

            # Let the reset output dialog fully close before stacking modals.
            QApplication.processEvents()
            row = create_or_confirm_host_recipe(
                self,
                self.db_path,
                reason="Rebuilt after database reset",
                created_by="maintenance",
                confirm_title="Create host recipe",
                confirm_body=(
                    "Database reset cleared host recipes. Create Launch defaults "
                    "from a live hardware probe?\n"
                    "Multi-GPU hosts are asked which card is primary for AI first."
                ),
            )
            if row is None:
                QMessageBox.information(
                    self,
                    "Host recipe",
                    "Host recipe not created.\n"
                    "Create it later under the Recipe tab (or on next Bringup launch).\n"
                    "Multi-GPU hosts must pick a primary AI GPU.",
                )
                return
            rec = row.get("recipe") or {}
            self.status_label.setText(
                f"Host recipe created (AI GPU {rec.get('embed_gpu_index')})"
            )
            if hasattr(self, "recipe_tab") and self.recipe_tab is not None:
                try:
                    self.recipe_tab.refresh()
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.warning(
                self,
                "Host recipe",
                f"Could not rebuild host recipe after reset:\n{e}\n\n"
                "Create it later under the Recipe tab.",
            )

    def _prompt_reset_mode(self) -> str | None:
        """Return 'content', 'full', or None if cancelled."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Reset ship_computer.db")
        dlg.setMinimumWidth(560)

        theme = getattr(self, "theme", {}) or {}
        bg = theme.get("bg", "#1e1e2e")
        fg = theme.get("fg", "#e8e8e8")
        border = theme.get("border", "#666666")
        accent = theme.get("accent", "#5C6BC0")
        accent_hover = theme.get("accent_hover", "#7986CB")
        dlg.setStyleSheet(
            f"""
            QDialog {{
                background-color: {bg};
                color: {fg};
            }}
            QLabel {{
                color: {fg};
            }}
            QRadioButton {{
                color: {fg};
                spacing: 10px;
                padding: 6px 0 2px 0;
            }}
            QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {border};
                border-radius: 10px;
                background-color: {bg};
            }}
            QRadioButton::indicator:hover {{
                border-color: {accent_hover};
            }}
            QRadioButton::indicator:checked {{
                border: 2px solid {accent};
                background-color: {accent};
            }}
            QPushButton {{
                background-color: {accent};
                color: #FFFFFF;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 72px;
            }}
            QPushButton:hover {{
                background-color: {accent_hover};
            }}
            """
        )

        lay = QVBoxLayout(dlg)
        lay.setSpacing(6)
        intro = QLabel("Choose how far the reset should go:")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        content = QRadioButton("a) Corpus / logs only — keep settings & profiles")
        content.setChecked(True)
        content_hint = QLabel(
            "Clears documents, embeddings/FTS, captains_log, agent_queue, "
            "quarantine, and related tables; VACUUM + rebuild indexes."
        )
        content_hint.setWordWrap(True)
        content_hint.setStyleSheet("color: #aaaaaa; padding-left: 28px;")

        full = QRadioButton("b) ALL tables — recreate from ship_computer_schema.sql")
        full_hint = QLabel(
            "Wipes Spock_Console settings and spock_profile rows too."
        )
        full_hint.setWordWrap(True)
        full_hint.setStyleSheet("color: #aaaaaa; padding-left: 28px;")

        group = QButtonGroup(dlg)
        group.addButton(content)
        group.addButton(full)

        lay.addWidget(content)
        lay.addWidget(content_hint)
        lay.addSpacing(10)
        lay.addWidget(full)
        lay.addWidget(full_hint)
        lay.addSpacing(8)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return "content" if content.isChecked() else "full"


