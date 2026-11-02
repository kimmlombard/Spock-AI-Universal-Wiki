"""Hardware scan panel (Spock-Scanner tabs)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from model_selector_core import format_hardware_report
from spock_scanner_core import ABOUT_TEXT, load_model_guide

from .state import ModelSelectorState
from .widgets import _action_btn, _panel_stylesheet
from .workers import HardwareScanWorker, LlamaConfigWorker


class HardwareScanPanel(QWidget):
    """Spock-Scanner assessment UI in the middle pane.

    Tabs: Ship status, Upgrade advice, Model guide, GPU details,
    llamaccp config, About. Live Monitor lives in Status window.
    Launch is left-nav only.
    """

    scan_complete = pyqtSignal(dict)

    def __init__(self, theme: dict, state: ModelSelectorState, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.state = state
        self._worker: Optional[HardwareScanWorker] = None
        self._cfg_worker: Optional[LlamaConfigWorker] = None
        self._build()
        self.apply_theme()
        self._restore_from_state()

    def _console(self) -> QTextEdit:
        t = QTextEdit()
        t.setReadOnly(True)
        t.setFont(QFont("Consolas", 10))
        return t

    def _build(self):
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.scan_btn = _action_btn("SCAN HARDWARE", "#5C6BC0", "#FFFFFF")
        self.scan_btn.clicked.connect(self._start_scan)
        row.addWidget(self.scan_btn)
        row.addStretch()
        self.status_lbl = QLabel(self.state.status_message)
        row.addWidget(self.status_lbl)
        layout.addLayout(row)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.ship_text = self._console()
        self.tabs.addTab(self.ship_text, "Ship status")

        self.upgrade_text = self._console()
        self.tabs.addTab(self.upgrade_text, "Upgrade advice")

        self.guide_text = self._console()
        self.guide_text.setPlainText(load_model_guide())
        self.tabs.addTab(self.guide_text, "Model guide")

        self.gpu_text = self._console()
        self.tabs.addTab(self.gpu_text, "GPU details")

        cfg_page = QWidget()
        cfg_layout = QVBoxLayout(cfg_page)
        cfg_btn_row = QHBoxLayout()
        self.cfg_btn = _action_btn("Generate Config", "#5C6BC0", "#FFFFFF")
        self.cfg_btn.clicked.connect(self._generate_llamaccp_config)
        cfg_btn_row.addWidget(self.cfg_btn)
        cfg_btn_row.addStretch()
        cfg_note = QLabel(
            "Explains chat vs embeddings vs RAG :8090 · Live Monitor is in Status"
        )
        cfg_note.setStyleSheet("color: #aaa;")
        cfg_btn_row.addWidget(cfg_note)
        cfg_layout.addLayout(cfg_btn_row)
        self.cfg_text = self._console()
        cfg_layout.addWidget(self.cfg_text)
        self.tabs.addTab(cfg_page, "llamaccp config")

        self.about_text = self._console()
        self.about_text.setPlainText(ABOUT_TEXT)
        self.tabs.addTab(self.about_text, "About")

    def _restore_from_state(self):
        if self.state.hardware_probed_at:
            self.status_lbl.setText(
                f"STATUS: SCAN COMPLETE (probed {self.state.hardware_probed_at})"
            )
        elif self.state.hardware_probe_error:
            self.status_lbl.setText(
                f"STATUS: SCAN FAILED - {self.state.hardware_probe_error}"
            )
        if self.state.ship_status_report:
            self.ship_text.setPlainText(self.state.ship_status_report)
        elif self.state.hardware_report:
            self.ship_text.setPlainText(self.state.hardware_report)
        if self.state.upgrade_report:
            self.upgrade_text.setPlainText(self.state.upgrade_report)
        if self.state.gpu_details_report:
            self.gpu_text.setPlainText(self.state.gpu_details_report)
        if self.state.llamaccp_config_report:
            self.cfg_text.setPlainText(self.state.llamaccp_config_report)

    def _start_scan(self):
        # A scan is 3 nvidia-smi spawns + an NVML pass; never run two at once.
        if self._worker is not None and self._worker.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.status_lbl.setText("STATUS: SCANNING...")
        self.state.status_message = "STATUS: SCANNING..."
        self.ship_text.setPlainText("Scanning hardware...")
        self._worker = HardwareScanWorker(self)
        self._worker.finished_ok.connect(self._on_scan_ok)
        self._worker.failed.connect(self._on_scan_fail)
        self._worker.start()

    def _on_scan_ok(self, result: dict):
        specs = result.get("specs", {})
        self.state.hardware_specs = specs
        self.state.hardware_report = format_hardware_report(specs) if specs else ""
        self.state.gpu_list = specs.get("all_gpus", [])
        self.state.ship_status_report = result.get("ship_status_report", "")
        self.state.upgrade_report = result.get("upgrade_report", "")
        self.state.gpu_details_report = result.get("gpu_details_report", "")
        self.state.status_message = "STATUS: SCAN COMPLETE"
        self.state.hardware_probed_at = datetime.now().strftime("%H:%M:%S")
        self.state.hardware_probe_error = ""

        self.ship_text.setPlainText(self.state.ship_status_report)
        self.upgrade_text.setPlainText(self.state.upgrade_report)
        self.gpu_text.setPlainText(self.state.gpu_details_report)
        self.status_lbl.setText(
            f"STATUS: SCAN COMPLETE (probed {self.state.hardware_probed_at})"
        )
        self.scan_btn.setEnabled(True)
        self.tabs.setCurrentIndex(0)
        self.scan_complete.emit(specs)

    def _on_scan_fail(self, err: str):
        self.status_lbl.setText(f"STATUS: SCAN FAILED - {err}")
        self.state.status_message = f"STATUS: SCAN FAILED - {err}"
        self.state.hardware_probe_error = err
        self.ship_text.setPlainText(f"ERROR: {err}")
        self.scan_btn.setEnabled(True)

    def _generate_llamaccp_config(self):
        self.cfg_btn.setEnabled(False)
        self.cfg_text.setPlainText("Generating llama.cpp config...")
        self._cfg_worker = LlamaConfigWorker(self)
        self._cfg_worker.finished_ok.connect(self._on_cfg_ok)
        self._cfg_worker.failed.connect(self._on_cfg_fail)
        self._cfg_worker.start()

    def _on_cfg_ok(self, text: str):
        self.state.llamaccp_config_report = text
        self.cfg_text.setPlainText(text)
        self.cfg_btn.setEnabled(True)

    def _on_cfg_fail(self, err: str):
        self.cfg_text.setPlainText(f"ERROR: {err}")
        self.cfg_btn.setEnabled(True)

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))
        border = self.theme["border"]
        bg = self.theme["bg"]
        panel = self.theme["panel_bg"]
        fg = self.theme["fg"]
        accent = self.theme["accent"]
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: 1px solid {border};
                background: {bg};
            }}
            QTabBar::tab {{
                background: {panel};
                color: {fg};
                padding: 8px 14px;
                margin-right: 2px;
                border: 1px solid {border};
            }}
            QTabBar::tab:selected {{
                background: {accent};
                font-weight: bold;
            }}
            QGroupBox {{
                color: {fg};
                border: 1px solid {border};
                margin-top: 8px;
                padding-top: 8px;
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
            """
        )


# ── Models ──────────────────────────────────────────────────────────────
