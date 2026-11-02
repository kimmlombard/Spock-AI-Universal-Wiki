"""LLM / Ship Status window (suite Tools → Ship Status)."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from llama_server_manager import LlamaServerManager
from lm_studio_api import (
    find_catalog_key_for_path,
    list_models as lm_list_models,
    load_model as lm_load_model,
    loaded_instance_context_length as lm_loaded_context_length,
    loaded_models as lm_loaded_models,
    models_match as lm_models_match,
    snapshot as lm_snapshot,
    unload_model as lm_unload_model,
)
from model_selector_core import SCRIPT_DIR, get_llamaccp_dir, is_embedding_gguf_path
from spock_scanner_core import get_live_monitor_snapshot

from .widgets import _action_btn, _panel_stylesheet


class LlmStatusWindow(QWidget):
    """Non-modal Status: Live Monitor / LM Studio tabs + llama-server instances."""

    def __init__(
        self,
        theme: dict,
        server_manager: LlamaServerManager,
        parent=None,
        get_lm_config=None,
        get_spock_health_context=None,
        *,
        window_title: str = "Status",
        show_lm_studio_tab: bool = True,
    ):
        super().__init__(parent)
        self.theme = theme
        self.manager = server_manager
        self.get_lm_config = get_lm_config or (lambda: {})
        self.get_spock_health_context = get_spock_health_context or (lambda: {})
        self._show_lm_studio_tab = bool(show_lm_studio_tab)
        self._monitor_labels: Dict[str, Dict[str, QLabel]] = {}
        self._monitor_grid: Optional[QGridLayout] = None
        self._closing = False
        self.setWindowTitle(window_title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        # Tall enough for ~6 service rows + LM catalog without squeezing the grid.
        self.resize(860, 1100)
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._update_monitor)
        self._build()
        self.apply_theme()
        self._connect()
        self.set_standby()
        # Auto-start live monitor
        self._monitor_timer.start(1000)
        self.monitor_btn.setText("Stop Monitor")
        self._update_monitor()
        if self._show_lm_studio_tab:
            QTimer.singleShot(200, self._lm_check_status)

    def _lm_cfg(self) -> Dict[str, Any]:
        cfg = self.get_lm_config() or {}
        try:
            ctx = int(cfg.get("context_length") or 32768)
        except (TypeError, ValueError):
            ctx = 32768
        return {
            "host": str(cfg.get("host") or "localhost"),
            "port": int(cfg.get("port") or 1234),
            "key": str(cfg.get("key") or ""),
            "context_length": max(512, min(ctx, 262144)),
        }

    def _build(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        # ── Tab 1: Live Monitor ──
        mon_page = QWidget()
        mon_layout = QVBoxLayout(mon_page)
        mon_title = QLabel("Live Monitor")
        mon_font = QFont()
        mon_font.setPointSize(13)
        mon_font.setBold(True)
        mon_title.setFont(mon_font)
        mon_title.setStyleSheet("color: #FF9800;")
        mon_layout.addWidget(mon_title)

        ctrl = QHBoxLayout()
        self.monitor_btn = _action_btn("Stop Monitor", "#6D9E5A", "#FFFFFF")
        self.monitor_btn.clicked.connect(self._toggle_monitor)
        ctrl.addWidget(self.monitor_btn)
        self.status_py_btn = _action_btn("Embedding Status", "#5C6BC0", "#FFFFFF")
        self.status_py_btn.setToolTip(
            "Run wiki_agent_status.py (ingest queue / embed progress for Embedding Profile)"
        )
        self.status_py_btn.clicked.connect(self._run_status_py)
        ctrl.addWidget(self.status_py_btn)
        self.spock_status_btn = _action_btn("Run Spock Status", "#00897B", "#FFFFFF")
        self.spock_status_btn.setToolTip(
            "Same report as MCP → Run spock-status "
            "(RAG API, llama :8080/:8081, MCP adapter, --ui-mcp-proxy)"
        )
        self.spock_status_btn.clicked.connect(self._run_spock_status)
        ctrl.addWidget(self.spock_status_btn)
        ctrl.addWidget(QLabel("Interval:"))
        self.monitor_interval = QSpinBox()
        self.monitor_interval.setRange(500, 5000)
        self.monitor_interval.setSingleStep(500)
        self.monitor_interval.setValue(1000)
        self.monitor_interval.setSuffix(" ms")
        ctrl.addWidget(self.monitor_interval)
        ctrl.addStretch()
        mon_layout.addLayout(ctrl)

        self._monitor_host = QWidget()
        self._monitor_grid = QGridLayout(self._monitor_host)
        mon_layout.addWidget(self._monitor_host, stretch=1)
        self._rebuild_monitor_boxes(
            {
                "CPU": {
                    "Usage": "--",
                    "Threads": "--",
                    "Cores": "--",
                    "Frequency": "--",
                },
                "Memory": {
                    "Total": "--",
                    "Used": "--",
                    "Available": "--",
                    "Percent": "--",
                },
                "GPU 0": {
                    "Name": "--",
                    "Utilization": "--",
                    "Temperature": "--",
                    "VRAM Used": "--",
                    "VRAM Free": "--",
                    "Power": "--",
                },
            }
        )
        self.tabs.addTab(mon_page, "Live Monitor")

        # ── Tab 2: LM Studio ──
        lm_page = QWidget()
        lm_layout = QVBoxLayout(lm_page)
        lm_title = QLabel("LM Studio")
        lm_title.setFont(mon_font)
        lm_title.setStyleSheet("color: #FF9800;")
        lm_layout.addWidget(lm_title)

        self.lm_status_lbl = QLabel("LM Studio: not checked")
        self.lm_status_lbl.setWordWrap(True)
        lm_layout.addWidget(self.lm_status_lbl)

        lm_btns = QHBoxLayout()
        self.lm_check_btn = _action_btn("Check LM Studio status", "#5C6BC0", "#FFFFFF")
        self.lm_check_btn.clicked.connect(self._lm_check_status)
        self.lm_list_btn = _action_btn("List LM Studio Models", "#5C6BC0", "#FFFFFF")
        self.lm_list_btn.clicked.connect(self._lm_list_models)
        self.lm_load_btn = _action_btn("Load Selected Model", "#6D9E5A", "#FFFFFF")
        self.lm_load_btn.setToolTip(
            "Load the selected row from the LM Studio catalog list above.\n"
            "If nothing is selected there, falls back to mapping a selected "
            "llama-server instance (below) into LM Studio."
        )
        self.lm_load_btn.clicked.connect(self._lm_load_selected_model)
        for b in (self.lm_check_btn, self.lm_list_btn, self.lm_load_btn):
            lm_btns.addWidget(b)
        lm_btns.addStretch()
        lm_layout.addLayout(lm_btns)

        ctx_row = QHBoxLayout()
        ctx_row.addWidget(QLabel("Load context (-c):"))
        self.lm_ctx_spin = QSpinBox()
        self.lm_ctx_spin.setRange(512, 262144)
        self.lm_ctx_spin.setSingleStep(1024)
        self.lm_ctx_spin.setValue(int(self._lm_cfg().get("context_length") or 32768))
        self.lm_ctx_spin.setToolTip(
            "Passed as context_length to LM Studio /api/v1/models/load.\n"
            "Overrides LM Studio’s single-GPU VRAM estimate that often clamps to 8192 "
            "when another GPU (e.g. RTX 3060 embeddings) is also in use.\n"
            "Reload the model after changing this. 262144 is rarely practical — "
            "32768–65536 is typical for a 24GB chat GPU."
        )
        self.lm_ctx_spin.valueChanged.connect(self._lm_ctx_changed)
        ctx_row.addWidget(self.lm_ctx_spin)
        ctx_row.addStretch()
        lm_layout.addLayout(ctx_row)

        lm_layout.addWidget(QLabel("LM Studio catalog / loaded models:"))
        self.lm_model_list = QListWidget()
        self.lm_model_list.setMinimumHeight(320)
        lm_layout.addWidget(self.lm_model_list, stretch=1)
        tip_lm = QLabel(
            "1) List LM Studio Models → select a catalog row → Load Selected Model.\n"
            "Or select a llama-server instance below to map that GGUF into LM Studio.\n"
            "Set Load context above so Ask AI / Deep Dive are not stuck at 8192 tokens."
        )
        tip_lm.setWordWrap(True)
        tip_lm.setStyleSheet("color: #aaa;")
        lm_layout.addWidget(tip_lm)
        if self._show_lm_studio_tab:
            self.tabs.addTab(lm_page, "LM Studio")
        else:
            # Keep widgets constructed for signal wiring, but hide the tab in wizards.
            lm_page.setVisible(False)
            self._lm_page_hidden = lm_page
            self.tabs.tabBar().setVisible(False)

        layout.addWidget(self.tabs, stretch=2)

        # ── Below tabs: suite listeners (embed/chat + WebUI/RAG/MCP) ──
        llm_title = QLabel("Running services")
        llm_title.setFont(mon_font)
        llm_title.setStyleSheet("color: #FF9800;")
        layout.addWidget(llm_title)

        self.state_lbl = QLabel("STANDBY")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.state_lbl.setFont(font)
        self.state_lbl.setStyleSheet("color: #FFC107;")
        layout.addWidget(self.state_lbl)

        tip = QLabel(
            "Embedding :8080 / chat :8081 (GPU on PID). Also lists WebUI :8082, "
            "RAG :8090, MCP :8765 when launched. Embedding ports are for "
            "/embeddings only — use Ask AI / LM Studio for instruct chat."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #aaa;")
        layout.addWidget(tip)

        btns = QHBoxLayout()
        self.refresh_inst_btn = _action_btn("Refresh", "#5C6BC0", "#FFFFFF")
        self.refresh_inst_btn.clicked.connect(self._refresh_instances)
        self.stop_inst_btn = _action_btn("Stop", "#C44A4A", "#FFFFFF")
        self.stop_inst_btn.clicked.connect(self._stop_selected)
        self.restart_inst_btn = _action_btn("Restart", "#FF9800")
        self.restart_inst_btn.clicked.connect(self._restart_selected)
        self.model_info_inst_btn = _action_btn("Model Info", "#5C6BC0", "#FFFFFF")
        self.model_info_inst_btn.setToolTip(
            "Show model details for the selected running instance"
        )
        self.model_info_inst_btn.clicked.connect(self._model_info_selected)
        self.model_info_inst_btn.setEnabled(False)
        self.kill_all_btn = _action_btn("Kill All", "#8B0000", "#FFFFFF")
        self.kill_all_btn.clicked.connect(self._kill_all_instances)
        self.open_inst_btn = _action_btn("Open Browser Chat", "#6D9E5A", "#FFFFFF")
        self.open_inst_btn.setToolTip("Open llama-server web chat UI for the selected instance")
        self.open_inst_btn.clicked.connect(self._open_selected)
        self.open_inst_btn.setEnabled(False)
        for b in (
            self.refresh_inst_btn,
            self.stop_inst_btn,
            self.restart_inst_btn,
            self.model_info_inst_btn,
            self.kill_all_btn,
        ):
            btns.addWidget(b)
        btns.addSpacing(24)
        btns.addWidget(self.open_inst_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self.inst_table = QTableWidget(0, 6)
        self.inst_table.setHorizontalHeaderLabels(
            ["Role", "Model", "Port", "GPU", "PID", "Log"]
        )
        self.inst_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.inst_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.inst_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # ~6 rows visible (was ~3); keep growing with the window.
        self.inst_table.setMinimumHeight(280)
        self.inst_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.inst_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.Stretch
        )
        self.inst_table.itemSelectionChanged.connect(self._on_inst_select)
        self.inst_table.cellDoubleClicked.connect(self._open_selected_log)
        layout.addWidget(self.inst_table, stretch=2)

        self.log_path_lbl = QLabel("Server log: —")
        self.log_path_lbl.setWordWrap(True)
        self.log_path_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.log_path_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_path_lbl.mousePressEvent = self._open_log_path  # type: ignore
        layout.addWidget(self.log_path_lbl)

        layout.addWidget(QLabel("Live output (latest Launch):"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setMinimumHeight(120)
        self.log.setMaximumHeight(220)
        layout.addWidget(self.log, stretch=1)

        # Compat aliases used by older helpers
        self.model_lbl = QLabel("")
        self.port_lbl = QLabel("")
        self.gpu_lbl = QLabel("")
        self.pid_lbl = QLabel("")
        self.model_lbl.hide()
        self.port_lbl.hide()
        self.gpu_lbl.hide()
        self.pid_lbl.hide()

    def _lm_check_status(self):
        cfg = self._lm_cfg()
        snap = lm_snapshot(cfg["host"], cfg["port"], cfg["key"])
        if snap.get("reachable"):
            loaded = snap.get("loaded") or []
            if loaded:
                names = ", ".join(
                    f"{x.get('key')} [{x.get('type')}]" for x in loaded[:6]
                )
                more = "" if len(loaded) <= 6 else f" (+{len(loaded) - 6} more)"
                self.lm_status_lbl.setText(
                    f"LM Studio: online @ {cfg['host']}:{cfg['port']} — "
                    f"loaded: {names}{more} ({snap.get('detail')})"
                )
                self.lm_status_lbl.setStyleSheet("color: #6D9E5A;")
            else:
                self.lm_status_lbl.setText(
                    f"LM Studio: online @ {cfg['host']}:{cfg['port']} — "
                    f"no model loaded ({snap.get('detail')})"
                )
                self.lm_status_lbl.setStyleSheet("color: #FFC107;")
        else:
            self.lm_status_lbl.setText(
                f"LM Studio: offline @ {cfg['host']}:{cfg['port']} — {snap.get('detail')}"
            )
            self.lm_status_lbl.setStyleSheet("color: #C44A4A;")
        return snap

    def _lm_list_models(self):
        cfg = self._lm_cfg()
        info = lm_list_models(cfg["host"], cfg["port"], cfg["key"])
        self.lm_model_list.clear()
        if not info.get("ok"):
            self.lm_status_lbl.setText(f"LM Studio list failed: {info.get('detail')}")
            self.lm_status_lbl.setStyleSheet("color: #C44A4A;")
            QMessageBox.warning(
                self, "LM Studio", f"Could not list models:\n{info.get('detail')}"
            )
            return
        for m in info.get("models") or []:
            loaded = m.get("loaded_instance_ids") or []
            flag = " [LOADED]" if loaded else ""
            text = f"{m.get('type', 'llm')}: {m.get('display_name') or m.get('key')}{flag}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, m.get("key") or "")
            item.setData(Qt.ItemDataRole.UserRole + 1, m.get("type") or "llm")
            self.lm_model_list.addItem(item)
        self.lm_status_lbl.setText(
            f"LM Studio: listed {self.lm_model_list.count()} model(s) "
            f"({info.get('detail')})"
        )
        self.lm_status_lbl.setStyleSheet("color: #6D9E5A;")

    def _lm_load_selected_model(self):
        """Load from LM Studio catalog selection, else map a llama-server instance."""
        item = self.lm_model_list.currentItem()
        if item is not None:
            key = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            mtype = str(item.data(Qt.ItemDataRole.UserRole + 1) or "llm").strip()
            if key:
                if mtype == "embedding" or is_embedding_gguf_path(key):
                    reply = QMessageBox.warning(
                        self,
                        "Embedding model",
                        "That catalog entry looks like an embedding model.\n\n"
                        "Ask AI expects an instruct/chat model.\n\n"
                        "Load it into LM Studio anyway?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return
                self._lm_load_catalog_key(key)
                return

        meta = self._selected_inst_meta()
        if meta:
            self._lm_load_selected_instance()
            return

        QMessageBox.information(
            self,
            "Load Selected Model",
            "Select a model in the LM Studio catalog list above "
            "(use List LM Studio Models first),\n"
            "or select a llama-server instance in the table below "
            "to map its GGUF into LM Studio.",
        )

    def _lm_ctx_changed(self, value: int):
        """Persist context spin into app config via MainWindow when possible."""
        try:
            mw = self.parent()
            while mw is not None and not hasattr(mw, "config"):
                mw = mw.parent()
            if mw is None or not hasattr(mw, "config"):
                return
            mw.config["lm_studio_context_length"] = int(value)  # type: ignore[attr-defined]
            if hasattr(mw, "save_config"):
                mw.save_config()  # type: ignore[attr-defined]
        except Exception:
            pass

    def _lm_desired_context(self) -> int:
        if hasattr(self, "lm_ctx_spin") and self.lm_ctx_spin is not None:
            return int(self.lm_ctx_spin.value())
        return int(self._lm_cfg().get("context_length") or 32768)

    def _lm_persist_model_key(self, key: str):
        """Save catalog key into app config + live Ask AI client."""
        try:
            mw = self.parent()
            while mw is not None and not hasattr(mw, "config"):
                mw = mw.parent()
            if mw is None or not hasattr(mw, "config"):
                return
            mw.config["lm_studio_model"] = key  # type: ignore[attr-defined]
            mw.config["ask_ai_provider"] = "LM Studio"  # type: ignore[attr-defined]
            mw.config["lm_studio_context_length"] = self._lm_desired_context()  # type: ignore[attr-defined]
            if hasattr(mw, "save_config"):
                mw.save_config()  # type: ignore[attr-defined]
            if hasattr(mw, "_refresh_ask_ai_chat_client"):
                mw._refresh_ask_ai_chat_client()  # type: ignore[attr-defined]
            elif hasattr(mw, "_apply_ask_ai_provider_config"):
                mw._apply_ask_ai_provider_config()  # type: ignore[attr-defined]
        except Exception:
            pass

    def _lm_model_already_loaded(self, key: str, loaded: list) -> bool:
        for entry in loaded:
            if str(entry.get("type") or "llm") == "embedding":
                continue
            ek = str(entry.get("key") or "")
            iid = str(entry.get("instance_id") or "")
            if (
                lm_models_match(key, ek)
                or lm_models_match(key, iid)
                or key == ek
                or key == iid
                or (key and iid.startswith(key + ":"))
            ):
                return True
        return False

    def _lm_load_catalog_key(self, key: str):
        cfg = self._lm_cfg()
        desired_ctx = self._lm_desired_context()
        snap = lm_snapshot(cfg["host"], cfg["port"], cfg["key"])
        if not snap.get("reachable"):
            QMessageBox.critical(
                self,
                "LM Studio",
                f"LM Studio is not reachable at {cfg['host']}:{cfg['port']}.\n"
                f"{snap.get('detail')}",
            )
            return

        loaded = lm_loaded_models(cfg["host"], cfg["port"], cfg["key"])
        if self._lm_model_already_loaded(key, loaded):
            live_ctx = lm_loaded_context_length(
                cfg["host"], cfg["port"], cfg["key"], model_key=key
            )
            # LM Studio often clamps to 8192 under multi-GPU "single GPU" estimates —
            # reload when the live context is below what Ask AI / Deep Dive need.
            if live_ctx is not None and live_ctx >= desired_ctx:
                self._lm_persist_model_key(key)
                self.lm_status_lbl.setText(
                    f"LM Studio: ready — {key} (context={live_ctx})"
                )
                self.lm_status_lbl.setStyleSheet("color: #6D9E5A;")
                self._lm_list_models()
                QMessageBox.information(
                    self,
                    "LM Studio",
                    f"Already loaded and ready for Ask AI:\n{key}\n"
                    f"context_length={live_ctx}",
                )
                return
            # Too small (or unknown) — eject and reload with explicit context_length
            for entry in loaded:
                if str(entry.get("type") or "llm") == "embedding":
                    continue
                iid = entry.get("instance_id") or ""
                if not iid:
                    continue
                lm_unload_model(iid, cfg["host"], cfg["port"], cfg["key"])
            self.lm_status_lbl.setText(
                f"LM Studio: reloading {key} with context_length={desired_ctx} "
                f"(was {live_ctx})…"
            )
        else:
            # Eject other chat instances only (keep embeddings if any)
            for entry in loaded:
                if str(entry.get("type") or "llm") == "embedding":
                    continue
                iid = entry.get("instance_id") or ""
                if not iid:
                    continue
                ok_u, detail_u = lm_unload_model(
                    iid, cfg["host"], cfg["port"], cfg["key"]
                )
                if not ok_u:
                    QMessageBox.warning(
                        self,
                        "LM Studio",
                        f"Could not eject {iid}:\n{detail_u}\n\nTrying load anyway…",
                    )
            self.lm_status_lbl.setText(
                f"LM Studio: loading {key} (context_length={desired_ctx})…"
            )

        QApplication.processEvents()
        ok, detail = lm_load_model(
            key,
            cfg["host"],
            cfg["port"],
            cfg["key"],
            context_length=desired_ctx,
            flash_attention=True,
            offload_kv_cache_to_gpu=True,
            echo_load_config=True,
        )

        # Trust live state: load API may error even when the model is up.
        loaded_after = lm_loaded_models(cfg["host"], cfg["port"], cfg["key"])
        if self._lm_model_already_loaded(key, loaded_after):
            live_ctx = lm_loaded_context_length(
                cfg["host"], cfg["port"], cfg["key"], model_key=key
            )
            self._lm_persist_model_key(key)
            ctx_note = f"context_length={live_ctx}" if live_ctx else detail
            self.lm_status_lbl.setText(f"LM Studio: ready — {key} ({ctx_note})")
            self.lm_status_lbl.setStyleSheet("color: #6D9E5A;")
            self._lm_list_models()
            QMessageBox.information(
                self,
                "LM Studio",
                f"Ready for Ask AI:\n{key}\n\n{detail if ok else ctx_note}",
            )
            return

        self.lm_status_lbl.setText(f"LM Studio load failed: {detail}")
        self.lm_status_lbl.setStyleSheet("color: #C44A4A;")
        QMessageBox.critical(
            self,
            "LM Studio",
            f"Load failed:\n{detail}\n\n"
            "Confirm the model appears under Developer → Local Server in LM Studio.\n"
            "If VRAM is tight on the RTX 6000, lower Load context (e.g. 16384).",
        )

    def _lm_load_selected_instance(self):
        meta = self._selected_inst_meta()
        if not meta:
            QMessageBox.information(
                self,
                "Load Selected Model",
                "Select a llama-server instance in the table below first.",
            )
            return
        model_path = str(meta.get("model_path") or "")
        role = str(meta.get("role") or "")
        if role == "embedding" or is_embedding_gguf_path(model_path):
            reply = QMessageBox.warning(
                self,
                "Embedding model",
                "The selected instance looks like an embedding model.\n\n"
                "Loading it into LM Studio as a chat model is usually wrong "
                "(Ask AI expects an instruct/chat model).\n\n"
                "Load it into LM Studio anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        cfg = self._lm_cfg()
        info = lm_list_models(cfg["host"], cfg["port"], cfg["key"])
        if not info.get("ok"):
            QMessageBox.critical(
                self, "LM Studio", f"Cannot reach LM Studio:\n{info.get('detail')}"
            )
            return
        catalog = info.get("models") or []
        key = find_catalog_key_for_path(model_path, catalog)
        if not key:
            QMessageBox.warning(
                self,
                "LM Studio",
                "Could not map this llama-server GGUF to an LM Studio catalog entry.\n\n"
                f"Path:\n{model_path}\n\n"
                "Import/download the model in LM Studio first, then List Models.",
            )
            return
        self._lm_load_catalog_key(key)

    def _rebuild_monitor_boxes(self, snap: Dict[str, Dict[str, str]]):
        assert self._monitor_grid is not None
        while self._monitor_grid.count():
            item = self._monitor_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._monitor_labels = {}
        # Prefer stable order: CPU, Memory, GPU*
        keys = []
        for k in ("CPU", "Memory"):
            if k in snap:
                keys.append(k)
        keys.extend(sorted(k for k in snap if k.startswith("GPU")))
        for extra in snap:
            if extra not in keys:
                keys.append(extra)
        for i, section in enumerate(keys):
            items = snap[section]
            box = QGroupBox(section)
            box_layout = QVBoxLayout(box)
            self._monitor_labels[section] = {}
            for item, value in items.items():
                lbl = QLabel(f"{item}: {value}")
                lbl.setFont(QFont("Consolas", 10))
                box_layout.addWidget(lbl)
                self._monitor_labels[section][item] = lbl
            self._monitor_grid.addWidget(box, i // 2, i % 2)

    def _connect(self):
        self.manager.started.connect(self._on_started)
        self.manager.log_line.connect(self._append_log)
        self.manager.stopped.connect(self._on_stopped)
        self.manager.failed.connect(self._on_failed)
        self.manager.status_message.connect(self._on_status_msg)
        self.manager.instances_changed.connect(self._refresh_instances)

    def set_standby(self):
        self.state_lbl.setText("STANDBY")
        self.state_lbl.setStyleSheet("color: #FFC107;")
        self.log_path_lbl.setText("Server log: —")
        self._current_log_path = ""
        self.inst_table.setRowCount(0)

    @staticmethod
    def _short_model_name(model_path: str) -> str:
        return os.path.basename(model_path) if model_path else "—"

    @staticmethod
    def _short_gpu_name(gpu: str) -> str:
        """Strip combo prefixes like '[1] Quadro RTX 6000 (24 GB)' → 'Quadro RTX 6000'."""
        if not gpu or gpu.startswith("("):
            return "—"
        text = gpu.strip()
        if "]" in text:
            text = text.split("]", 1)[1].strip()
        if "(" in text:
            text = text.split("(", 1)[0].strip()
        return text or "—"

    def refresh_from_manager(self):
        """Populate instance table from manager + discovered processes."""
        self._refresh_instances()

    def _refresh_instances(self):
        if self._closing:
            return
        from spock_health_report import discover_suite_service_rows
        from spock_onboarding.llama_process import format_pid_gpu, gpu_label_for_pid

        instances = self.manager.list_instances(refresh_discovered=True)
        self.inst_table.setRowCount(0)
        for inst in instances:
            r = self.inst_table.rowCount()
            self.inst_table.insertRow(r)
            role = inst.role or "unknown"
            gpu = (inst.gpu_label or "").strip()
            if not gpu:
                gpu = gpu_label_for_pid(int(inst.pid or 0))
                if gpu:
                    inst.gpu_label = gpu
            cells = [
                role,
                self._short_model_name(inst.model_path),
                str(inst.port or "—"),
                self._short_gpu_name(gpu),
                format_pid_gpu(inst.pid, gpu),
                inst.log_path or "—",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, inst.pid)
                    item.setData(Qt.ItemDataRole.UserRole + 1, role)
                    item.setData(Qt.ItemDataRole.UserRole + 2, inst.port)
                    item.setData(Qt.ItemDataRole.UserRole + 3, bool(inst.owned))
                    item.setData(Qt.ItemDataRole.UserRole + 4, inst.log_path or "")
                    item.setData(Qt.ItemDataRole.UserRole + 5, inst.model_path or "")
                    item.setData(Qt.ItemDataRole.UserRole + 6, gpu or "")
                    item.setData(Qt.ItemDataRole.UserRole + 7, False)  # suite service
                self.inst_table.setItem(r, c, item)

        for svc in discover_suite_service_rows():
            r = self.inst_table.rowCount()
            self.inst_table.insertRow(r)
            role = str(svc.get("role") or "service")
            pid = int(svc.get("pid") or 0)
            port = int(svc.get("port") or 0)
            cells = [
                role,
                str(svc.get("model") or "—"),
                str(port or "—"),
                "—",
                format_pid_gpu(pid, ""),
                "—",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, pid)
                    item.setData(Qt.ItemDataRole.UserRole + 1, role)
                    item.setData(Qt.ItemDataRole.UserRole + 2, port)
                    item.setData(Qt.ItemDataRole.UserRole + 3, False)
                    item.setData(Qt.ItemDataRole.UserRole + 4, "")
                    item.setData(Qt.ItemDataRole.UserRole + 5, "")
                    item.setData(Qt.ItemDataRole.UserRole + 6, "")
                    item.setData(Qt.ItemDataRole.UserRole + 7, True)
                self.inst_table.setItem(r, c, item)

        n = self.inst_table.rowCount()
        if n == 0:
            self.state_lbl.setText("STANDBY")
            self.state_lbl.setStyleSheet("color: #FFC107;")
            self.log_path_lbl.setText("Server log: —")
            self._current_log_path = ""
        else:
            roles = []
            for r in range(n):
                it = self.inst_table.item(r, 0)
                if it:
                    roles.append(it.text())
            self.state_lbl.setText(f"RUNNING — {n} service(s) ({', '.join(roles)})")
            self.state_lbl.setStyleSheet("color: #6D9E5A;")
        self._on_inst_select()

    def _selected_inst_meta(self) -> Optional[Dict[str, Any]]:
        rows = self.inst_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.inst_table.item(rows[0].row(), 0)
        if not item:
            return None
        return {
            "pid": int(item.data(Qt.ItemDataRole.UserRole) or 0),
            "role": str(item.data(Qt.ItemDataRole.UserRole + 1) or "unknown"),
            "port": int(item.data(Qt.ItemDataRole.UserRole + 2) or 0),
            "owned": bool(item.data(Qt.ItemDataRole.UserRole + 3)),
            "log_path": str(item.data(Qt.ItemDataRole.UserRole + 4) or ""),
            "model_path": str(item.data(Qt.ItemDataRole.UserRole + 5) or ""),
            "gpu_label": str(item.data(Qt.ItemDataRole.UserRole + 6) or ""),
            "service": bool(item.data(Qt.ItemDataRole.UserRole + 7)),
        }

    def _on_inst_select(self):
        meta = self._selected_inst_meta()
        has = meta is not None and meta["pid"] > 0
        is_svc = bool(meta and meta.get("service"))
        role = str(meta.get("role") or "") if meta else ""
        self.stop_inst_btn.setEnabled(has and not is_svc)
        self.restart_inst_btn.setEnabled(
            has and bool(meta and meta["owned"]) and not is_svc
        )
        openable = role in ("chat", "webui", "rag", "mcp", "embedding")
        self.open_inst_btn.setEnabled(has and bool(meta and meta["port"]) and openable)
        self.model_info_inst_btn.setEnabled(has and not is_svc)
        if meta and meta.get("log_path"):
            self._current_log_path = meta["log_path"]
            self.log_path_lbl.setText(f"Server log: {meta['log_path']}")
            self.log_path_lbl.setToolTip("Click to open log file")
        elif not has:
            pass
        else:
            self._current_log_path = ""
            self.log_path_lbl.setText("Server log: —")

    def _model_info_selected(self):
        meta = self._selected_inst_meta()
        if not meta or not meta.get("pid"):
            QMessageBox.warning(
                self,
                "No Selection",
                "Select a running instance row in the grid first.",
            )
            return
        path = meta.get("model_path") or ""
        name = self._short_model_name(path) if path else "—"
        size_txt = "—"
        exists = False
        if path and os.path.isfile(path):
            exists = True
            try:
                size_txt = f"{os.path.getsize(path) / (1024 ** 3):.2f} GB"
            except OSError:
                size_txt = "unreadable"
        lines = [
            f"Model:     {name}",
            f"Path:      {path or '—'}",
            f"On disk:   {'yes' if exists else 'no / unknown'}",
            f"Size:      {size_txt}",
            f"Role:      {meta.get('role') or '—'}",
            f"Port:      {meta.get('port') or '—'}",
            f"PID:       {meta.get('pid') or '—'}",
            f"GPU:       {self._short_gpu_name(meta.get('gpu_label') or '')}",
            f"Owned:     {'yes' if meta.get('owned') else 'discovered'}",
            f"Log:       {meta.get('log_path') or '—'}",
        ]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Model Info — {name}")
        dlg.setMinimumSize(640, 720)
        dlg.resize(720, 720)
        dlg.setModal(True)
        v = QVBoxLayout(dlg)
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setFont(QFont("Consolas", 10))
        viewer.setPlainText("\n".join(lines))
        v.addWidget(viewer)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close_btn)
        v.addLayout(row)
        dlg.exec()

    def _stop_selected(self):
        meta = self._selected_inst_meta()
        if not meta:
            return
        self.manager.stop_pid(meta["pid"])
        self._refresh_instances()

    def _restart_selected(self):
        meta = self._selected_inst_meta()
        if not meta:
            return
        if not meta["owned"]:
            QMessageBox.information(
                self,
                "Restart",
                "Only instances launched from Spock-to-bridge can be restarted.\n"
                "Stop the external process, then Launch again.",
            )
            return
        self.manager.restart_pid(meta["pid"])
        self._refresh_instances()

    def _open_selected(self):
        meta = self._selected_inst_meta()
        if not meta or not meta["port"]:
            return
        port = meta["port"]
        role = str(meta.get("role") or "")
        from spock_shell.open_url import open_url

        if role == "embedding":
            QMessageBox.warning(
                self,
                "Embedding server — not for chat",
                "This instance is an embedding model.\n\n"
                "Opening the web chat UI produces garbage text and runaway token "
                "counts. Use Ask AI / LM Studio for chat.\n\n"
                f"Opening health check: http://127.0.0.1:{port}/health",
            )
            open_url(f"http://127.0.0.1:{port}/health")
            return
        if role == "rag":
            open_url(f"http://127.0.0.1:{port}/health")
            return
        if role == "mcp":
            open_url(f"http://127.0.0.1:{port}/mcp")
            return
        open_url(f"http://127.0.0.1:{port}/")

    def _kill_all_instances(self):
        reply = QMessageBox.question(
            self,
            "Kill All",
            "Stop every llama-server process (owned and discovered)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.manager.kill_all()
        self._refresh_instances()

    def _open_selected_log(self, row: int, _col: int):
        item = self.inst_table.item(row, 0)
        if not item:
            return
        path = str(item.data(Qt.ItemDataRole.UserRole + 4) or "")
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _apply_running_fields(
        self,
        model_path: str,
        port: int,
        pid: int,
        gpu: str,
        log_path: str = "",
    ):
        path = log_path or getattr(self.manager, "log_path", "") or ""
        self._current_log_path = path
        if path:
            self.log_path_lbl.setText(f"Server log: {path}")
        self._refresh_instances()

    def _open_log_path(self, _event):
        path = getattr(self, "_current_log_path", "") or ""
        if not path or not os.path.exists(path):
            folder = os.path.dirname(path) if path else ""
            if folder and os.path.isdir(folder):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _toggle_monitor(self):
        if self._monitor_timer.isActive():
            self._monitor_timer.stop()
            self.monitor_btn.setText("Start Monitor")
        else:
            self._monitor_timer.start(self.monitor_interval.value())
            self.monitor_btn.setText("Stop Monitor")
            self._update_monitor()

    def _run_status_py(self):
        script = os.path.join(SCRIPT_DIR, "wiki_agent_status.py")
        if not os.path.isfile(script):
            QMessageBox.warning(self, "Error", f"Not found: {script}")
            return
        from spock_shell.busy_ui import clear_override_cursors

        clear_override_cursors()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                cwd=SCRIPT_DIR,
            )
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            clear_override_cursors()
            self._show_output_dialog(
                "Embedding Status (wiki_agent_status.py)", output.strip() or "(no output)"
            )
        except subprocess.TimeoutExpired:
            clear_override_cursors()
            QMessageBox.warning(self, "Timeout", "wiki_agent_status.py timed out after 120s")
        except Exception as e:
            clear_override_cursors()
            QMessageBox.warning(self, "Error", str(e))
        finally:
            clear_override_cursors()

    def _run_spock_status(self):
        """Same report as MCP panel → Run spock-status."""
        from spock_health_report import format_spock_health_report, probe_spock_health
        from spock_shell.busy_ui import clear_override_cursors

        clear_override_cursors()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            try:
                ctx = self.get_spock_health_context() or {}
            except Exception as e:
                clear_override_cursors()
                self._show_output_dialog(
                    "Spock Status", f"Could not read health context: {e}"
                )
                return
            try:
                chat_port = int(ctx.get("chat_port") or 8081)
            except (TypeError, ValueError):
                chat_port = 8081
            try:
                mcp_port = int(ctx.get("mcp_port") or 8765)
            except (TypeError, ValueError):
                mcp_port = 8765
            try:
                webui_port = int(ctx.get("webui_port") or 8082)
            except (TypeError, ValueError):
                webui_port = 8082
            data = probe_spock_health(
                api_base=str(ctx.get("api_base") or "http://127.0.0.1:8090"),
                db_path=str(ctx.get("db_path") or ""),
                embeddings_url=str(ctx.get("embeddings_url") or ""),
                api_key=str(ctx.get("api_key") or ""),
                chat_host=str(ctx.get("chat_host") or "localhost"),
                chat_port=chat_port,
                mcp_host=str(ctx.get("mcp_host") or "127.0.0.1"),
                mcp_port=mcp_port,
                mcp_transport=str(ctx.get("mcp_transport") or "streamable-http"),
                webui_host=str(ctx.get("webui_host") or "127.0.0.1"),
                webui_port=webui_port,
            )
            report = format_spock_health_report(data)
            clear_override_cursors()
            self._show_output_dialog("Spock Status (spock-status)", report)
        except Exception as e:
            clear_override_cursors()
            QMessageBox.warning(self, "Spock Status", str(e))
        finally:
            clear_override_cursors()

    def _show_output_dialog(self, title: str, text: str):
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
        btn_row.addStretch()
        copy_btn = QPushButton("Copy")
        copy_btn.setMinimumWidth(70)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(text))
        btn_row.addWidget(copy_btn)
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(70)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec()

    def _update_monitor(self):
        if self._closing:
            return
        snap = get_live_monitor_snapshot()
        # Rebuild if sections or per-section metric keys changed
        need_rebuild = set(snap.keys()) != set(self._monitor_labels.keys())
        if not need_rebuild:
            for section, items in snap.items():
                if set(items.keys()) != set(self._monitor_labels.get(section, {})):
                    need_rebuild = True
                    break
        if need_rebuild:
            self._rebuild_monitor_boxes(snap)
        for section, items in snap.items():
            labels = self._monitor_labels.get(section, {})
            for key, value in items.items():
                if key in labels:
                    labels[key].setText(f"{key}: {value}")
        if self._monitor_timer.isActive():
            wanted = self.monitor_interval.value()
            if self._monitor_timer.interval() != wanted:
                self._monitor_timer.setInterval(wanted)

    def _on_started(self, model_path: str, port: int, pid: int, gpu: str):
        self.log.clear()
        self._apply_running_fields(
            model_path,
            port,
            pid,
            gpu,
            getattr(self.manager, "log_path", "") or "",
        )

    def _on_stopped(self, code: int):
        self._append_log(f"\n[stopped exit {code}]\n")
        self._refresh_instances()

    def _on_failed(self, msg: str):
        self.state_lbl.setText("FAILED")
        self.state_lbl.setStyleSheet("color: #C44A4A;")
        self._append_log(msg + "\n")
        self._refresh_instances()

    def _on_status_msg(self, text: str):
        # Instance list refreshes via instances_changed; keep label hints light
        if "FAILED" in text.upper():
            self.state_lbl.setText("FAILED")
            self.state_lbl.setStyleSheet("color: #C44A4A;")

    def _append_log(self, text: str):
        if self._closing:
            return
        try:
            self.log.moveCursor(self.log.textCursor().MoveOperation.End)
            self.log.insertPlainText(text)
            self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        except RuntimeError:
            pass

    def stop_monitor(self):
        self._closing = True
        if self._monitor_timer.isActive():
            self._monitor_timer.stop()
        try:
            self.manager.instances_changed.disconnect(self._refresh_instances)
        except (TypeError, RuntimeError):
            pass
        try:
            self.manager.log_line.disconnect(self._append_log)
        except (TypeError, RuntimeError):
            pass

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))

    def closeEvent(self, event):
        # Normal X: hide so MainWindow can re-raise the same window.
        # App exit sets _force_close so we actually destroy and let Qt quit.
        # Under WSLg, ignore()+hide() leaves the window stuck — accept then hide.
        if getattr(self, "_force_close", False):
            self.stop_monitor()
            event.accept()
            return
        event.accept()
        self.hide()
