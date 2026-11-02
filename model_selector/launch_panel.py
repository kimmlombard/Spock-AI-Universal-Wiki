"""Local GGUF Launch panel."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from WarpCore.service_endpoints import DEFAULT_CTX
from llama_server_manager import LlamaServerManager
from model_selector_core import (
    format_hardware_report,
    get_llamaccp_dir,
    get_model_directory_options,
    gpu_combo_labels,
    is_embedding_gguf_path,
    embedding_profile_identity,
    merge_embedding_profile,
    scan_gguf_models_from_directory,
)
from spock_scanner_core import recommend_n_ctx

from .state import ModelSelectorState
from .widgets import _SortableTableItem, _action_btn, _panel_stylesheet
from .workers import HardwareScanWorker


class LaunchPanel(QWidget):
    request_model_info = pyqtSignal()
    llama_gui_launched = pyqtSignal(str)
    embedding_model_launched = pyqtSignal(str, str)

    def __init__(
        self,
        theme: dict,
        state: ModelSelectorState,
        server_manager: LlamaServerManager,
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.state = state
        self.manager = server_manager
        self._local_models: List[Dict[str, Any]] = []
        self._model_dirs: List[tuple] = []
        self._embedding_profile = merge_embedding_profile()
        self._hw_worker: Optional[HardwareScanWorker] = None
        self._pending_launch: Optional[Dict[str, Any]] = None
        self._closing = False
        self._kind_filter = "all"  # all | embedding | chat
        self._host_recipe: Optional[Dict[str, Any]] = None
        self._build()
        self.apply_theme()
        self._connect_manager()
        self._populate_gpus()
        self._populate_model_dirs()
        self._load_host_recipe_defaults()
        self._update_buttons()

    def _build(self):
        layout = QVBoxLayout(self)

        # Header: Model Selection + llamaccp path + Model Directory
        header = QVBoxLayout()
        title = QLabel("Model Selection")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #FF9800;")
        header.addWidget(title)
        self.llama_path_lbl = QLabel(f"llamaccp: {get_llamaccp_dir()}")
        self.llama_path_lbl.setStyleSheet("color: #aaa;")
        header.addWidget(self.llama_path_lbl)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Model Directory:"))
        self.dir_combo = QComboBox()
        self.dir_combo.setMinimumWidth(420)
        self.dir_combo.currentIndexChanged.connect(self._on_dir_changed)
        dir_row.addWidget(self.dir_combo, stretch=1)
        header.addLayout(dir_row)
        layout.addLayout(header)

        row = QHBoxLayout()
        self.scan_btn = _action_btn("SCAN MODELS", "#5C6BC0", "#FFFFFF")
        self.scan_btn.clicked.connect(self._scan_models)
        self.launch_btn = _action_btn("LAUNCH", "#6D9E5A", "#FFFFFF")
        self.launch_btn.clicked.connect(self._launch)
        self.launch_btn.setEnabled(False)
        self.delete_btn = _action_btn("DELETE", "#C44A4A", "#FFFFFF")
        self.delete_btn.clicked.connect(self._delete_model)
        self.delete_btn.setEnabled(False)
        self.delete_btn.setToolTip("Permanently delete the selected GGUF file from disk")
        self.stop_btn = _action_btn("STOP", "#C44A4A", "#FFFFFF")
        self.stop_btn.clicked.connect(self.manager.stop)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("Stop the latest Launch-owned instance (Status has per-instance Stop/Restart)")
        self.kill_btn = _action_btn("KILL ALL", "#8B0000", "#FFFFFF")
        self.kill_btn.clicked.connect(self._kill_all)
        self.browser_btn = _action_btn("Model Details", "#FF9800")
        self.browser_btn.setToolTip("Open Model Info panel for the selected / current model")
        self.browser_btn.clicked.connect(self._open_model_details)

        row.addWidget(self.scan_btn)
        row.addWidget(self.launch_btn)
        row.addWidget(self.delete_btn)
        row.addWidget(self.stop_btn)
        row.addWidget(self.kill_btn)
        row.addWidget(self.browser_btn)

        row.addWidget(QLabel("Port:"))
        try:
            from WarpCore.service_endpoints import DEFAULT_EMBED_PORT

            _default_port = str(DEFAULT_EMBED_PORT)
        except ImportError:
            _default_port = "8080"
        self.port_edit = QLineEdit(_default_port)
        self.port_edit.setMaximumWidth(60)
        row.addWidget(self.port_edit)

        row.addWidget(QLabel("GPU:"))
        self.gpu_combo = QComboBox()
        self.gpu_combo.setMinimumWidth(220)
        row.addWidget(self.gpu_combo)

        row.addWidget(QLabel("GPU Layers:"))
        self.ngl_edit = QLineEdit("-1")
        self.ngl_edit.setMaximumWidth(50)
        row.addWidget(self.ngl_edit)

        row.addWidget(QLabel("Context (-c):"))
        self.n_ctx_spin = QSpinBox()
        self.n_ctx_spin.setRange(512, 262144)
        self.n_ctx_spin.setSingleStep(1024)
        self.n_ctx_spin.setValue(int(DEFAULT_CTX["chat_n_ctx"]))
        self.n_ctx_spin.setMinimumWidth(100)
        self.n_ctx_spin.setMaximumWidth(120)
        self.n_ctx_spin.setToolTip(
            "llama-server -c / n_ctx. Host recipe + Suggest Context set a VRAM-safe value. "
            "GGUF train-ctx defaults (e.g. 256K) can exhaust VRAM — set this explicitly."
        )
        row.addWidget(self.n_ctx_spin)
        self.n_ctx_rec_btn = _action_btn("Suggest Context", "#5C6BC0", "#FFFFFF")
        self.n_ctx_rec_btn.setToolTip(
            "Fill Context (-c) from GPU VRAM heuristic for the selected GGUF "
            "(embedding vs chat). Also runs automatically when you select a row."
        )
        self.n_ctx_rec_btn.clicked.connect(self._apply_recommended_n_ctx)
        row.addWidget(self.n_ctx_rec_btn)
        row.addStretch()
        layout.addLayout(row)

        recipe_row = QHBoxLayout()
        recipe_row.addWidget(QLabel("GPU policy:"))
        self.gpu_policy_combo = QComboBox()
        self.gpu_policy_combo.addItem("Single GPU", "single_gpu")
        self.gpu_policy_combo.addItem("Pin per role", "pin_per_role")
        self.gpu_policy_combo.addItem("Tensor-split chat", "tensor_split_chat")
        self.gpu_policy_combo.setMinimumWidth(160)
        self.gpu_policy_combo.currentIndexChanged.connect(self._on_gpu_policy_changed)
        recipe_row.addWidget(self.gpu_policy_combo)
        recipe_row.addWidget(QLabel("tensor-split:"))
        self.tensor_split_edit = QLineEdit("0.5,0.5")
        self.tensor_split_edit.setMaximumWidth(100)
        self.tensor_split_edit.setToolTip(
            "llama-server --tensor-split (chat only). Leave blank to pin one GPU."
        )
        recipe_row.addWidget(self.tensor_split_edit)
        recipe_row.addWidget(QLabel("split-mode:"))
        self.split_mode_combo = QComboBox()
        self.split_mode_combo.addItems(["layer", "row", "tensor"])
        recipe_row.addWidget(self.split_mode_combo)
        recipe_row.addWidget(QLabel("MoE on CPU:"))
        self.n_cpu_moe_spin = QSpinBox()
        self.n_cpu_moe_spin.setRange(0, 999)
        self.n_cpu_moe_spin.setValue(0)
        self.n_cpu_moe_spin.setMaximumWidth(60)
        self.n_cpu_moe_spin.setToolTip(
            "llama-server -ncmoe for chat. MoE expert weights of the first N "
            "layers stay in CPU RAM so the rest fits in VRAM. 0 omits the flag. "
            "Embedding launches ignore this. Save to Recipe to keep it for this machine."
        )
        recipe_row.addWidget(self.n_cpu_moe_spin)
        recipe_row.addWidget(QLabel("Reasoning:"))
        self.reasoning_combo = QComboBox()
        self.reasoning_combo.addItem("off", "off")
        self.reasoning_combo.addItem("auto", "auto")
        self.reasoning_combo.addItem("on", "on")
        self.reasoning_combo.setToolTip(
            "llama-server --reasoning for chat. off disables thinking. "
            "auto lets the model template decide. Embedding launches omit this flag. "
            "Save Defaults to keep it on every machine."
        )
        recipe_row.addWidget(self.reasoning_combo)
        recipe_row.addWidget(QLabel("embed -np:"))
        self.embed_np_spin = QSpinBox()
        self.embed_np_spin.setRange(1, 16)
        self.embed_np_spin.setValue(1)
        self.embed_np_spin.setMaximumWidth(60)
        self.embed_np_spin.setToolTip("llama-server -np for embedding (slots). Spock default 1.")
        recipe_row.addWidget(self.embed_np_spin)
        self.save_pins_btn = _action_btn("SAVE DEFAULTS", "#5C6BC0", "#FFFFFF")
        self.save_pins_btn.setToolTip(
            "Remember GPU Layers, embed -np, and --reasoning for every launch "
            "on any machine (app.launch.* in Spock_Console)."
        )
        self.save_pins_btn.clicked.connect(self._save_launch_pins)
        recipe_row.addWidget(self.save_pins_btn)
        self.save_recipe_btn = _action_btn("SAVE TO RECIPE", "#6D9E5A", "#FFFFFF")
        self.save_recipe_btn.setToolTip(
            "Save GPU policy, tensor-split, split-mode, MoE-on-CPU (-ncmoe) and "
            "Context (-c) as a new host recipe version for this machine."
        )
        self.save_recipe_btn.clicked.connect(self._save_to_recipe)
        recipe_row.addWidget(self.save_recipe_btn)
        self.recipe_lbl = QLabel("")
        self.recipe_lbl.setStyleSheet("color: #aaa;")
        recipe_row.addWidget(self.recipe_lbl)
        recipe_row.addStretch()
        layout.addLayout(recipe_row)

        embed_row = QHBoxLayout()
        self.embed_server_cb = QCheckBox("Use as embedding server (profile -b/-ub + EMBEDDINGS_URL)")
        self.embed_server_cb.setToolTip(
            "When checked (or auto-detected from GGUF name), Launch applies Embedding Profile "
            "batch sizes and updates embeddings URL. Chat can stay on LM Studio."
        )
        embed_row.addWidget(self.embed_server_cb)
        embed_row.addStretch()
        layout.addLayout(embed_row)

        filt = QHBoxLayout()
        filt.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setMaximumWidth(220)
        self.filter_edit.textChanged.connect(self._apply_filter)
        filt.addWidget(self.filter_edit)
        self.filter_embed_btn = _action_btn("Filter Embeddings", "#5C6BC0", "#FFFFFF")
        self.filter_embed_btn.setCheckable(True)
        self.filter_embed_btn.setToolTip("Show only embedding GGUFs (name signals)")
        self.filter_embed_btn.clicked.connect(self._on_filter_embed_clicked)
        filt.addWidget(self.filter_embed_btn)
        self.filter_chat_btn = _action_btn("Filter Chat", "#FF9800")
        self.filter_chat_btn.setCheckable(True)
        self.filter_chat_btn.setToolTip("Show only chat / instruct GGUFs")
        self.filter_chat_btn.clicked.connect(self._on_filter_chat_clicked)
        filt.addWidget(self.filter_chat_btn)
        self.clear_filter_btn = _action_btn("CLEAR FILTER", "#C44A4A", "#FFFFFF")
        self.clear_filter_btn.setToolTip(
            "Clear text/kind filters and the Provider allow-list (ALL providers)."
        )
        self.clear_filter_btn.clicked.connect(self._clear_filters)
        filt.addWidget(self.clear_filter_btn)
        self.provider_filter_lbl = QLabel("")
        self.provider_filter_lbl.setStyleSheet("color: #FF9800; font-weight: bold;")
        filt.addWidget(self.provider_filter_lbl)
        self.llama_gui_embed_btn = _action_btn("Launch LLama GUI Embed", "#6D9E5A", "#FFFFFF")
        self.llama_gui_embed_btn.setToolTip(
            "Stop llama-server on port 8080, then start the command saved on "
            "Configure Spock AI tab 8."
        )
        self.llama_gui_embed_btn.clicked.connect(
            lambda: self._launch_llama_gui("embedding", 8080)
        )
        filt.addWidget(self.llama_gui_embed_btn)
        self.llama_gui_chat_btn = _action_btn("Launch LLama GUI Chat", "#5C6BC0", "#FFFFFF")
        self.llama_gui_chat_btn.setToolTip(
            "Stop llama-server on port 8081, then start the command saved on "
            "Configure Spock AI tab 9."
        )
        self.llama_gui_chat_btn.clicked.connect(
            lambda: self._launch_llama_gui("chat", 8081)
        )
        filt.addWidget(self.llama_gui_chat_btn)
        self.filter_count = QLabel("")
        filt.addWidget(self.filter_count)
        filt.addStretch()
        layout.addLayout(filt)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Model File", "Size (GB)", "Full Path"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(self._on_select)
        splitter.addWidget(self.table)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        splitter.addWidget(self.log)
        splitter.setSizes([280, 220])
        layout.addWidget(splitter)

        self.launch_status = QLabel(
            "Select All sources (or a specific folder), then SCAN MODELS."
        )
        self.launch_status.setStyleSheet("color: #FF9800; font-weight: bold;")
        layout.addWidget(self.launch_status)

    def _populate_model_dirs(self):
        self._model_dirs = get_model_directory_options()
        self.dir_combo.blockSignals(True)
        self.dir_combo.clear()
        for label, _path in self._model_dirs:
            self.dir_combo.addItem(label)
        self.dir_combo.blockSignals(False)
        # Default: All sources (first option)
        if self._model_dirs:
            self.dir_combo.setCurrentIndex(0)
        self._scan_models()

    def _selected_model_dir(self) -> Optional[str]:
        idx = self.dir_combo.currentIndex()
        if idx < 0 or idx >= len(self._model_dirs):
            return None
        return self._model_dirs[idx][1]

    def _on_dir_changed(self, _index: int = 0):
        self._scan_models()

    def _connect_manager(self):
        self.manager.log_line.connect(self._append_log)
        self.manager.status_message.connect(self._set_status)
        self.manager.started.connect(self._on_started)
        self.manager.stopped.connect(self._on_stopped)
        self.manager.failed.connect(self._on_failed)
        self.manager.instances_changed.connect(self._update_buttons)

    def _populate_gpus(self):
        labels, default_idx = gpu_combo_labels(self.state.gpu_list)
        if not self.state.gpu_list:
            labels = ["(scan hardware first)"]
            default_idx = None
        self.gpu_combo.clear()
        self.gpu_combo.addItems(labels)
        if default_idx is not None:
            self.gpu_combo.setCurrentIndex(default_idx)

    def _scan_models(self):
        selected = self._selected_model_dir()
        label = self.dir_combo.currentText()
        self._local_models = scan_gguf_models_from_directory(selected)
        if not self._local_models:
            self.launch_status.setText(f"0 GGUF model(s) found in: {label}")
            self.launch_status.setStyleSheet("color: #FF9800; font-weight: bold;")
            self._apply_filter()
            return
        self.launch_status.setText(
            f"{len(self._local_models)} GGUF model(s) found in: {label}"
        )
        self.launch_status.setStyleSheet("color: #6D9E5A; font-weight: bold;")
        self._apply_filter()

    def _clear_filters(self):
        self.filter_edit.blockSignals(True)
        self.filter_edit.clear()
        self.filter_edit.blockSignals(False)
        self._kind_filter = "all"
        self.filter_embed_btn.setChecked(False)
        self.filter_chat_btn.setChecked(False)
        try:
            from llmfit_session_criteria import clear_provider_filter

            clear_provider_filter()
        except Exception:
            pass
        self._apply_filter()

    def _launch_llama_gui(self, role: str, port: int) -> None:
        """Stop a llama-server on this port, then start the saved View Command."""
        from spock_shell.llama_gui_command import assess_port

        assessment = assess_port(port)
        action = assessment.get("action")
        if action == "refuse":
            self._report_llama_gui(str(assessment.get("message") or "Port is busy."))
            return
        if action == "kill":
            pid = assessment.get("pid")
            if pid:
                tracked = self.manager._instances.get(int(pid)) if hasattr(self.manager, "_instances") else None
                if tracked is not None:
                    self.manager.stop_pid(int(pid))
                else:
                    self.manager._terminate_pid_tree(int(pid))
        ok = bool(self.manager.launch_saved_llama_gui(role))
        which = "Embed" if role == "embedding" else "Chat"
        if ok:
            message = f"Launch LLama GUI {which} started on port {port}."
        else:
            message = f"Launch LLama GUI {which} did not start."
        self._report_llama_gui(message)

    def _report_llama_gui(self, message: str) -> None:
        self.launch_status.setText(message)
        self.launch_status.setStyleSheet("color: #FF9800; font-weight: bold;")
        self.llama_gui_launched.emit(message)

    def _on_filter_embed_clicked(self, checked: bool):
        if checked:
            self._kind_filter = "embedding"
            self.filter_chat_btn.setChecked(False)
        else:
            self._kind_filter = "all"
        self._apply_filter()

    def _on_filter_chat_clicked(self, checked: bool):
        if checked:
            self._kind_filter = "chat"
            self.filter_embed_btn.setChecked(False)
        else:
            self._kind_filter = "all"
        self._apply_filter()

    def _apply_filter(self):
        query = self.filter_edit.text().strip().lower()
        try:
            from llmfit_session_criteria import model_id_allowed, provider_filter_label

            allow = model_id_allowed
            prov_lbl = provider_filter_label()
        except Exception:
            allow = lambda _mid: True  # noqa: E731
            prov_lbl = "ALL"
        if hasattr(self, "provider_filter_lbl"):
            self.provider_filter_lbl.setText(f"Providers: {prov_lbl}")
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        shown = 0
        for orig_i, m in enumerate(self._local_models, start=1):
            path = m["path"]
            is_embed = is_embedding_gguf_path(path)
            if self._kind_filter == "embedding" and not is_embed:
                continue
            if self._kind_filter == "chat" and is_embed:
                continue
            # Match allow-list against file name + full path (local GGUFs lack org/).
            hay = f"{m.get('file', '')} {path}"
            if not allow(hay):
                continue
            if query and query not in m["file"].lower() and query not in path.lower():
                continue
            shown += 1
            r = self.table.rowCount()
            self.table.insertRow(r)
            # Keep original scan index in "#" so sort-by-# is stable across filters.
            idx_item = _SortableTableItem(str(orig_i))
            idx_item.setData(Qt.ItemDataRole.UserRole, int(orig_i))
            self.table.setItem(r, 0, idx_item)
            self.table.setItem(r, 1, _SortableTableItem(m["file"]))
            size_item = _SortableTableItem(f"{m['size_gb']:.2f}")
            size_item.setData(Qt.ItemDataRole.UserRole, float(m["size_gb"]))
            self.table.setItem(r, 2, size_item)
            self.table.setItem(r, 3, _SortableTableItem(path))
        total = len(self._local_models)
        parts = []
        if prov_lbl and prov_lbl != "ALL":
            parts.append(f"providers={prov_lbl}")
        if self._kind_filter != "all":
            parts.append(self._kind_filter)
        if query:
            parts.append(f'"{query}"')
        suffix = f" ({', '.join(parts)})" if parts else ""
        self.filter_count.setText(f"{shown}/{total} shown{suffix}" if parts else "")
        self.table.setSortingEnabled(True)
        # Embeddings / Chat filters: "#" (column 1) descending.
        if self._kind_filter in ("embedding", "chat"):
            self.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        else:
            self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    def _selected_model_path(self) -> Optional[str]:
        rows = self.table.selectionModel().selectedRows()
        row = rows[0].row() if rows else self.table.currentRow()
        if row < 0:
            return None
        path_item = self.table.item(row, 3)
        return path_item.text() if path_item else None

    def _delete_model(self):
        path = self._selected_model_path()
        if not path:
            QMessageBox.warning(self, "No Selection", "Select a GGUF model file first.")
            return
        norm = os.path.normcase(os.path.abspath(path))
        in_use = []
        for inst in self.manager.list_instances(refresh_discovered=True):
            if not inst.model_path:
                continue
            if os.path.normcase(os.path.abspath(inst.model_path)) == norm and inst.is_alive:
                in_use.append(f"PID {inst.pid} on :{inst.port}")
        if in_use:
            QMessageBox.warning(
                self,
                "Model In Use",
                "Cannot delete — model is loaded by a running llama-server:\n\n"
                + "\n".join(in_use)
                + "\n\nStop it on Status first.",
            )
            return
        name = os.path.basename(path)
        try:
            size_gb = os.path.getsize(path) / (1024**3)
            size_txt = f"{size_gb:.2f} GB"
        except OSError:
            size_txt = "unknown size"
        reply = QMessageBox.question(
            self,
            "Delete Model",
            f"Permanently delete this GGUF from disk?\n\n"
            f"{name}\n{path}\n({size_txt})\n\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(path)
        except OSError as e:
            QMessageBox.critical(self, "Delete Failed", f"Could not delete:\n{path}\n\n{e}")
            return
        if getattr(self.state, "selected_gguf_path", None):
            sel = os.path.normcase(os.path.abspath(self.state.selected_gguf_path))
            if sel == norm:
                self.state.selected_gguf_path = ""
        self._append_log(f"Deleted model: {path}")
        self.launch_status.setText(f"Deleted: {name}")
        self.launch_status.setStyleSheet("color: #C44A4A; font-weight: bold;")
        self._scan_models()

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            path_item = self.table.item(rows[0].row(), 3)
            if path_item:
                path = path_item.text()
                self.state.selected_gguf_path = path
                # Toggle embedding-server flag from GGUF name signals
                is_embed = is_embedding_gguf_path(path)
                self.embed_server_cb.setChecked(is_embed)
                # Same as Suggest Context: fill Context (-c) for this GGUF / GPU.
                self._apply_recommended_n_ctx()
        else:
            # No selection — leave checkbox as-is
            pass
        self._update_buttons()

    def use_as_embedding_server(self) -> bool:
        return self.embed_server_cb.isChecked()

    def clear_embedding_server_flag(self):
        """Uncheck after Launch has applied Embedding Profile once."""
        self.embed_server_cb.setChecked(False)

    def set_embedding_profile(self, profile: Dict[str, Any]):
        self._embedding_profile = merge_embedding_profile(profile)

    def _load_host_recipe_defaults(self) -> None:
        """Apply current host recipe to Launch controls (no silent Create).

        When the stored recipe describes another machine — ship_computer.db
        copied to a different box — its policy and ``-c`` values would not fit,
        so the defaults come from a live proposal and the label says so. The
        stored recipe itself is only replaced from Maintenance → Recipe.
        """
        drift: list = []
        try:
            from spock_shell.paths import SHIP_COMPUTER_DB
            from WarpCore.host_recipe import effective_recipe, get_current_recipe

            row = get_current_recipe(SHIP_COMPUTER_DB)
            if row is not None:
                plan = effective_recipe(SHIP_COMPUTER_DB)
                drift = list(plan.get("drift") or [])
                if drift:
                    row = {**row, "recipe": plan["recipe"]}
        except Exception:
            row = None
        self._host_recipe = (row or {}).get("recipe") if row else None
        rec = self._host_recipe if isinstance(self._host_recipe, dict) else {}
        if not rec:
            self.n_cpu_moe_spin.setValue(0)
            self.recipe_lbl.setText("(no host recipe — Maintenance → Recipe)")
            self._apply_launch_pins()
            self._on_gpu_policy_changed()
            return
        policy = str(rec.get("gpu_policy") or "single_gpu")
        idx = self.gpu_policy_combo.findData(policy)
        if idx < 0:
            idx = 0
        self.gpu_policy_combo.blockSignals(True)
        self.gpu_policy_combo.setCurrentIndex(idx)
        self.gpu_policy_combo.blockSignals(False)
        ts = str(rec.get("tensor_split") or "").strip()
        if ts:
            self.tensor_split_edit.setText(ts)
        sm = str(rec.get("split_mode") or "layer")
        sm_i = self.split_mode_combo.findText(sm)
        if sm_i >= 0:
            self.split_mode_combo.setCurrentIndex(sm_i)
        try:
            self.embed_np_spin.setValue(int(rec.get("embed_np") or 1))
        except (TypeError, ValueError):
            self.embed_np_spin.setValue(1)
        try:
            self.n_cpu_moe_spin.setValue(
                max(0, min(999, int(rec.get("n_cpu_moe") or 0)))
            )
        except (TypeError, ValueError):
            self.n_cpu_moe_spin.setValue(0)
        ngl = str(rec.get("ngl_default") or "-1")
        if ngl:
            self.ngl_edit.setText(ngl)
        # Default spin to chat n_ctx; selection/Suggest still role-aware.
        try:
            self.n_ctx_spin.setValue(int(rec.get("chat_n_ctx") or DEFAULT_CTX["chat_n_ctx"]))
        except (TypeError, ValueError):
            self.n_ctx_spin.setValue(int(DEFAULT_CTX["chat_n_ctx"]))
        # Pinned flags win over the recipe: they are what the user typed, and
        # they mean the same thing on whatever machine this database lands on.
        self._apply_launch_pins()
        if drift:
            self.recipe_lbl.setText(
                f"{policy} from live probe · saved recipe "
                f"v{(row or {}).get('version')} is for other hardware "
                "(Maintenance → Recipe to save this host)"
            )
        else:
            self.recipe_lbl.setText(f"recipe v{(row or {}).get('version')} · {policy}")
        self._on_gpu_policy_changed()

    def reload_host_recipe(self) -> None:
        """Re-read the host recipe into the Launch controls (e.g. after Acquire)."""
        self._load_host_recipe_defaults()

    def _apply_launch_pins(self) -> None:
        """Show the flags pinned in ``app.launch.*`` over the recipe's defaults."""
        try:
            from spock_shell.paths import SHIP_COMPUTER_DB
            from WarpCore.host_recipe import pinned_launch_settings

            pinned = pinned_launch_settings(SHIP_COMPUTER_DB)
        except Exception:
            return
        ngl = str(pinned.get("ngl") or "-1")
        if ngl != "-1":
            self.ngl_edit.setText(ngl)
        try:
            self.embed_np_spin.setValue(int(pinned.get("embed_np") or 1))
        except (TypeError, ValueError):
            pass
        reasoning = str(pinned.get("reasoning") or "off")
        ri = self.reasoning_combo.findData(reasoning)
        if ri >= 0:
            self.reasoning_combo.setCurrentIndex(ri)

    def _save_launch_pins(self) -> None:
        """Persist GPU Layers + embed -np as app.launch.* (exported to app_config.json)."""
        ngl = self.ngl_edit.text().strip() or "-1"
        if ngl.lower() == "auto":
            ngl = "-1"
        if not ngl.lstrip("-").isdigit() or not -1 <= int(ngl) <= 999:
            QMessageBox.warning(
                self,
                "GPU Layers",
                "Enter -1 (ask llmfit at launch) or 0-999 for GPU layers.",
            )
            return
        try:
            from spock_shell.paths import SHIP_COMPUTER_DB
            from WarpCore import settings_store

            settings_store.set_many(
                SHIP_COMPUTER_DB,
                {
                    "app.launch.ngl": str(int(ngl)),
                    "app.launch.embed_np": int(self.embed_np_spin.value()),
                    "app.launch.reasoning": str(
                        self.reasoning_combo.currentData() or "off"
                    ),
                },
                by="launch-panel",
            )
        except Exception as e:
            QMessageBox.warning(self, "Save Defaults", f"Could not save: {e}")
            return
        how = (
            "llmfit picks the layer count at launch"
            if ngl == "-1"
            else f"-ngl {int(ngl)} on every launch"
        )
        reasoning = str(self.reasoning_combo.currentData() or "off")
        self.log.append(
            f"Saved launch defaults: {how}, embed -np {self.embed_np_spin.value()}, "
            f"--reasoning {reasoning}"
        )

    def _save_to_recipe(self) -> None:
        """Save GPU shape + -c as a new host recipe version for this machine."""
        try:
            from spock_shell.paths import SHIP_COMPUTER_DB
            from WarpCore import host_recipe as hr
        except Exception as e:
            QMessageBox.warning(self, "Save To Recipe", f"Recipe unavailable: {e}")
            return
        try:
            plan = hr.effective_recipe(SHIP_COMPUTER_DB, created_by="launch-panel")
        except Exception as e:
            QMessageBox.warning(self, "Save To Recipe", f"Recipe unavailable: {e}")
            return

        policy = str(self.gpu_policy_combo.currentData() or "single_gpu")
        role = "embed" if self.embed_server_cb.isChecked() else "chat"
        # Drift means the saved recipe belongs to another machine. Build on the
        # live proposal so we never carry that machine's GPU indexes forward.
        base = dict(plan["recipe"])
        drift = list(plan.get("drift") or [])
        if drift:
            reply = QMessageBox.question(
                self,
                "Save To Recipe",
                "The saved recipe was made on different hardware:\n\n"
                + "\n".join(f"  • {d}" for d in drift)
                + "\n\nSave a new version for this machine using these settings?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        base["gpu_policy"] = policy
        if policy == "tensor_split_chat":
            base["tensor_split"] = self.tensor_split_edit.text().strip() or "0.5,0.5"
            base["split_mode"] = self.split_mode_combo.currentText() or "layer"
        else:
            base["tensor_split"] = ""
            base["split_mode"] = "layer"
        # One -c box, two roles: write the slot the current selection launches into.
        base["embed_n_ctx" if role == "embed" else "chat_n_ctx"] = int(
            self.n_ctx_spin.value()
        )
        base["n_cpu_moe"] = int(self.n_cpu_moe_spin.value())
        reason = (
            f"Launch panel: {policy}, {role} -c {self.n_ctx_spin.value()}, "
            f"-ncmoe {int(self.n_cpu_moe_spin.value())}"
        )
        if drift:
            reason += " (saved for this host after drift: " + "; ".join(drift) + ")"
        try:
            row = hr.update_recipe(
                SHIP_COMPUTER_DB,
                reason=reason,
                hardware=plan["hardware"],
                recipe=base,
                created_by="launch-panel",
            )
        except Exception as e:
            QMessageBox.warning(self, "Save To Recipe", f"Could not save: {e}")
            return
        self.log.append(
            f"Saved host recipe v{row.get('version')}: {policy}, "
            f"{role} -c {self.n_ctx_spin.value()}, "
            f"-ncmoe {int(self.n_cpu_moe_spin.value())}"
        )
        self._load_host_recipe_defaults()

    def _on_gpu_policy_changed(self) -> None:
        policy = self.gpu_policy_combo.currentData()
        split = policy == "tensor_split_chat"
        self.tensor_split_edit.setEnabled(split)
        self.split_mode_combo.setEnabled(split)

    def _launch_recipe_overrides(self, role: str) -> Dict[str, Any]:
        """Merge UI policy + host recipe + pinned flags into manager.launch kwargs."""
        try:
            from spock_shell.paths import SHIP_COMPUTER_DB
            from WarpCore.host_recipe import launch_plan_for_role

            base = launch_plan_for_role(SHIP_COMPUTER_DB, self._host_recipe, role)
        except Exception:
            from WarpCore.host_recipe import launch_overrides_for_role

            base = launch_overrides_for_role(self._host_recipe, role)
        policy = self.gpu_policy_combo.currentData() or base.get("gpu_policy")
        out = dict(base)
        out["gpu_policy"] = policy
        if role in ("embedding", "embed"):
            out["n_parallel"] = int(self.embed_np_spin.value())
            out["split_mode"] = ""
            out["tensor_split"] = ""
            out["pin_cuda"] = True
            if out.get("cuda_device") in (None, ""):
                out["cuda_device"] = "0"
        elif policy == "tensor_split_chat":
            out["split_mode"] = self.split_mode_combo.currentText() or "layer"
            out["tensor_split"] = self.tensor_split_edit.text().strip() or "0.5,0.5"
            out["pin_cuda"] = False
            out["cuda_device"] = ""
            out["n_parallel"] = None
        else:
            out["split_mode"] = ""
            out["tensor_split"] = ""
            out["pin_cuda"] = True
            if policy == "pin_per_role" and self._host_recipe:
                out["cuda_device"] = str(
                    self._host_recipe.get("chat_gpu_index")
                    if role == "chat"
                    else self._host_recipe.get("embed_gpu_index") or "0"
                )
        if role in ("embedding", "embed"):
            out["n_cpu_moe"] = 0
            out.pop("reasoning", None)
        else:
            out["n_cpu_moe"] = int(self.n_cpu_moe_spin.value())
            out["reasoning"] = str(self.reasoning_combo.currentData() or "off")
        return out

    def _launch(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "No Selection", "Select a GGUF model file first.")
            return
        model_path = self.table.item(rows[0].row(), 3).text()
        port_text = self.port_edit.text().strip()
        if not port_text.isdigit():
            QMessageBox.warning(self, "Invalid Port", "Enter a valid port number (1-65535).")
            return
        if is_embedding_gguf_path(model_path):
            self.embed_server_cb.setChecked(True)
        profile = getattr(self, "_embedding_profile", None) or merge_embedding_profile()
        launch_args = {
            "model_path": model_path,
            "port": int(port_text),
            "ngl": self.ngl_edit.text().strip(),
            "n_ctx": int(self.n_ctx_spin.value()),
            "gpu_name": self.gpu_combo.currentText(),
            "llama_batch": int(profile.get("llama_batch", 512)),
            "llama_ubatch": int(profile.get("llama_ubatch", 512)),
        }
        if not self.state.hardware_specs or not self.state.gpu_list:
            self.launch_status.setText("STATUS: Hardware scan required — scanning...")
            self.launch_status.setStyleSheet("color: #FF9800; font-weight: bold;")
            self.launch_btn.setEnabled(False)
            self._pending_launch = launch_args
            self._hw_worker = HardwareScanWorker(self)
            self._hw_worker.finished_ok.connect(self._on_hw_scan_before_launch)
            self._hw_worker.failed.connect(self._on_hw_scan_before_launch_fail)
            self._hw_worker.start()
            return
        self._do_launch(launch_args)

    def _on_hw_scan_before_launch(self, result: dict):
        specs = result.get("specs", {})
        self.state.hardware_specs = specs
        self.state.hardware_report = format_hardware_report(specs) if specs else ""
        self.state.gpu_list = specs.get("all_gpus", [])
        self.state.ship_status_report = result.get("ship_status_report", "")
        self.state.upgrade_report = result.get("upgrade_report", "")
        self.state.gpu_details_report = result.get("gpu_details_report", "")
        self.state.status_message = "STATUS: SCAN COMPLETE"
        self._populate_gpus()
        args = self._pending_launch
        self._pending_launch = None
        self.launch_btn.setEnabled(True)
        if args:
            # Prefer newly populated GPU combo selection if prior was placeholder
            args = dict(args)
            args["gpu_name"] = self.gpu_combo.currentText()
            self._do_launch(args)

    def _on_hw_scan_before_launch_fail(self, err: str):
        self._pending_launch = None
        self.launch_btn.setEnabled(True)
        self.launch_status.setText(f"STATUS: HARDWARE SCAN FAILED - {err}")
        QMessageBox.critical(
            self,
            "Hardware Scan Failed",
            f"Could not scan hardware before Launch:\n{err}",
        )

    def _do_launch(self, args: Dict[str, Any]):
        self.log.clear()
        role = "embedding" if self.embed_server_cb.isChecked() else "chat"
        if is_embedding_gguf_path(args["model_path"]):
            role = "embedding"
            self.embed_server_cb.setChecked(True)
        overrides = self._launch_recipe_overrides(role)
        ngl = str(args.get("ngl", overrides.get("ngl", "-1")) or "-1")
        # Only credit the pin when the box still holds the pinned number.
        ngl_source = (
            str(overrides.get("ngl_source") or "")
            if ngl == str(overrides.get("ngl") or "")
            else ""
        )
        n_ctx = int(args.get("n_ctx", self.n_ctx_spin.value()))
        if role == "chat":
            try:
                from spock_shell.good_results_coach import tip_launch_fit

                fit = tip_launch_fit(
                    model_path=str(args.get("model_path") or ""),
                    n_ctx=n_ctx,
                    vram_gb=float(self._selected_gpu_vram_gb() or 0.0),
                    role="chat",
                )
            except Exception:
                fit = None
            if fit:
                reply = QMessageBox.warning(
                    self,
                    "Fit warning — Launch anyway?",
                    fit
                    + "\n\nLaunch may be slow or time out on Deep Dive. "
                    "Prefer Suggest Context or a smaller quant.\n\nLaunch anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.launch_status.setText("STATUS: Launch cancelled (fit warning)")
                    self.launch_status.setStyleSheet("color: #FF9800; font-weight: bold;")
                    return
                self.launch_status.setText("STATUS: " + fit[:120])
                self.launch_status.setStyleSheet("color: #FF9800; font-weight: bold;")
        self.manager.launch(
            model_path=args["model_path"],
            port=int(args["port"]),
            ngl=ngl,
            gpu_list=self.state.gpu_list,
            gpu_name=args.get("gpu_name", ""),
            llama_batch=int(args.get("llama_batch", 512)),
            llama_ubatch=int(args.get("llama_ubatch", 512)),
            role=role,
            n_ctx=n_ctx,
            split_mode=str(overrides.get("split_mode") or ""),
            tensor_split=str(overrides.get("tensor_split") or ""),
            n_parallel=overrides.get("n_parallel"),
            pin_cuda=overrides.get("pin_cuda"),
            cuda_device=str(overrides.get("cuda_device") or ""),
            ngl_source=ngl_source,
            flash_attn=overrides.get("flash_attn"),
            cache_type_k=overrides.get("cache_type_k"),
            cache_type_v=overrides.get("cache_type_v"),
            n_cpu_moe=int(overrides.get("n_cpu_moe") or 0),
            reasoning=str(overrides.get("reasoning") or ""),
        )

    def _selected_gpu_vram_gb(self) -> float:
        """Best-effort VRAM for the GPU combo selection (or max GPU / specs)."""
        import re

        gpus = self.state.gpu_list or []
        label = (self.gpu_combo.currentText() or "").strip()
        label_l = label.lower()

        # 1) Match combo selection to a scanned GPU
        for g in gpus:
            name = str(g.get("name") or "").lower()
            if name and name in label_l:
                if g.get("vram_gb") not in (None, ""):
                    return float(g["vram_gb"])
                if g.get("vram_mb") not in (None, ""):
                    return float(g["vram_mb"]) / 1024.0

        # 2) Parse "(22.5 GB)" from the combo label itself
        m = re.search(r"\(([\d.]+)\s*GB\)", label, flags=re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

        # 3) Largest GPU in the list
        if gpus:
            best = max(
                gpus,
                key=lambda x: float(
                    x.get("vram_gb")
                    or (float(x.get("vram_mb") or 0) / 1024.0)
                    or 0
                ),
            )
            if best.get("vram_gb") not in (None, ""):
                return float(best["vram_gb"])
            if best.get("vram_mb") not in (None, ""):
                return float(best["vram_mb"]) / 1024.0

        # 4) Top-level hardware_specs.vram_gb (do NOT invent 8GB)
        specs = self.state.hardware_specs or {}
        try:
            top = float(specs.get("vram_gb") or 0)
            if top > 0:
                return top
        except (TypeError, ValueError):
            pass
        return 0.0

    def _selected_model_size_gb(self, path: str = "") -> Optional[float]:
        if path and os.path.isfile(path):
            try:
                return os.path.getsize(path) / (1024**3)
            except OSError:
                pass
        rows = self.table.selectionModel().selectedRows()
        row = rows[0].row() if rows else self.table.currentRow()
        if row < 0:
            return None
        size_item = self.table.item(row, 2)
        if not size_item:
            return None
        raw = size_item.data(Qt.ItemDataRole.UserRole)
        try:
            if raw is not None:
                return float(raw)
            return float(size_item.text())
        except (TypeError, ValueError):
            return None

    def _apply_recommended_n_ctx(self):
        role = "embedding" if self.embed_server_cb.isChecked() else "chat"
        path = self._selected_model_path() or (self.state.selected_gguf_path or "")
        if path and is_embedding_gguf_path(path):
            role = "embedding"
            self.embed_server_cb.setChecked(True)
        elif path:
            # Chat filter / chat GGUF: never keep a stale embedding flag
            role = "chat"
            self.embed_server_cb.setChecked(False)

        vram = self._selected_gpu_vram_gb()
        model_gb = self._selected_model_size_gb(path)
        sibling_gb = None
        other = "embedding" if role == "chat" else "chat"
        # Only subtract sibling when recipe says both roles share one physical GPU.
        share_gpu = True
        try:
            from WarpCore.host_recipe import roles_share_physical_gpu

            share_gpu = roles_share_physical_gpu(self._host_recipe)
            policy = self.gpu_policy_combo.currentData()
            if policy == "tensor_split_chat":
                share_gpu = False
            elif policy == "pin_per_role" and self._host_recipe:
                share_gpu = roles_share_physical_gpu(self._host_recipe)
        except Exception:
            share_gpu = True
        if share_gpu:
            try:
                for inst in self.manager.alive_for_role(other):
                    p = getattr(inst, "model_path", "") or ""
                    if p and os.path.isfile(p):
                        sibling_gb = os.path.getsize(p) / (1024**3)
                        break
            except Exception:
                sibling_gb = None
        if vram <= 0:
            self.log.append(
                "Suggest Context: no GPU VRAM yet — run 1 Hardware scan first "
                "(refusing to invent 8GB / 8192).\n"
            )
            QMessageBox.information(
                self,
                "Suggest Context",
                "No GPU VRAM detected yet.\n\n"
                "Open 1 Hardware and let the scan finish, then return here "
                "and click Suggest Context again.",
            )
            return

        info = recommend_n_ctx(
            vram, role=role, model_size_gb=model_gb, sibling_size_gb=sibling_gb
        )
        self.n_ctx_spin.setValue(int(info["n_ctx"]))
        self.log.append(
            f"Recommended -c {info['n_ctx']} for {role} "
            f"(VRAM~{info['vram_gb']:.1f}GB"
            + (f", model~{model_gb:.1f}GB" if model_gb else "")
            + f"): {info['reason']}\n"
        )

    def _open_model_details(self):
        """Open Model Info panel (same destination as Models → Model Info)."""
        path = self._selected_model_path() or (self.state.selected_gguf_path or "")
        if not path:
            QMessageBox.warning(
                self,
                "No Selection",
                "Select a GGUF model in the grid first, then click Model Details.",
            )
            return
        # Prefer matching HF id from prior Models query; else use folder name
        folder = os.path.basename(os.path.dirname(path))
        file_stem = os.path.splitext(os.path.basename(path))[0]
        candidates = []
        for m in list(self.state.model_data) + list(self.state.close_data):
            mid = str(m.get("id") or "")
            if mid and (
                mid.endswith("/" + folder)
                or mid.endswith("/" + file_stem)
                or folder in mid
                or file_stem in mid
            ):
                candidates.append(mid)
        if candidates:
            self.state.selected_hf_model_id = candidates[0]
        elif folder:
            # Best-effort: downloads land in models/<short_name>/
            self.state.selected_hf_model_id = folder
        self.state.selected_gguf_path = path
        self.request_model_info.emit()

    def _kill_all(self):
        self.manager.kill_all()
        self._update_buttons()

    def _append_log(self, text: str):
        if self._closing:
            return
        try:
            self.log.moveCursor(self.log.textCursor().MoveOperation.End)
            self.log.insertPlainText(text)
            self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        except RuntimeError:
            pass

    def prepare_shutdown(self):
        """Disconnect from manager signals so late log lines don't hit deleted widgets."""
        self._closing = True
        try:
            self.manager.log_line.disconnect(self._append_log)
        except (TypeError, RuntimeError):
            pass
        try:
            self.manager.status_message.disconnect(self._set_status)
        except (TypeError, RuntimeError):
            pass
        try:
            self.manager.started.disconnect(self._on_started)
        except (TypeError, RuntimeError):
            pass
        try:
            self.manager.stopped.disconnect(self._on_stopped)
        except (TypeError, RuntimeError):
            pass
        try:
            self.manager.failed.disconnect(self._on_failed)
        except (TypeError, RuntimeError):
            pass
        try:
            self.manager.instances_changed.disconnect(self._update_buttons)
        except (TypeError, RuntimeError):
            pass

    def _set_status(self, text: str):
        self.launch_status.setText(text)
        color = "#6D9E5A" if "RUNNING" in text else "#FF9800"
        if "FAILED" in text or "STOPPED" in text:
            color = "#FF9800"
        self.launch_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _on_started(self, model_path: str, port: int, pid: int, gpu: str):
        self.state.selected_gguf_path = model_path
        self._bump_port_after_launch(port)
        self._update_buttons()
        try:
            launched_port = int(port)
        except (TypeError, ValueError):
            launched_port = 0
        if launched_port == 8080 or is_embedding_gguf_path(model_path):
            known = [
                str(m.get("id") or "")
                for m in list(self.state.model_data) + list(self.state.close_data)
            ]
            ident = embedding_profile_identity(model_path, known_ids=known)
            self.embedding_model_launched.emit(ident["model_path"], ident["model_id"])

    def _bump_port_after_launch(self, launched_port: int):
        """After a successful launch, advance Port +1 for the next instance."""
        try:
            used = int(launched_port)
        except (TypeError, ValueError):
            text = self.port_edit.text().strip()
            used = int(text) if text.isdigit() else 8080
        next_port = used + 1
        if next_port > 65535:
            next_port = 65535
        self.port_edit.setText(str(next_port))
        self._set_status(
            f"RUNNING on :{used} — next Launch port set to {next_port}"
        )

    def _on_stopped(self, _code: int):
        self._update_buttons()

    def _on_failed(self, msg: str):
        QMessageBox.critical(self, "Launch Failed", msg)
        self._update_buttons()

    def _update_buttons(self):
        # One embedding + one chat max (manager stops prior same-role on Launch)
        pending = self._pending_launch is not None
        has_sel = bool(self.table.selectionModel().selectedRows())
        self.stop_btn.setEnabled(self.manager.is_running)
        self.scan_btn.setEnabled(not pending)
        self.dir_combo.setEnabled(not pending)
        self.launch_btn.setEnabled(not pending and has_sel)
        self.delete_btn.setEnabled(not pending and has_sel)

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))


# ── Embedding Profile (Config) ───────────────────────────────────────────
