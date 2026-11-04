"""HF Hub models panel (query / filter / download / Gemini)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gemini_openai_models import list_models_for_ui, probe_model_chat
from model_selector_core import (
    PDF_AVAILABLE,
    _estimate_gguf_size_gb,
    export_report_pdf,
)

from .state import ModelSelectorState
from .widgets import _SortableTableItem, _action_btn, _panel_stylesheet
from .workers import DownloadWorker, HfQueryWorker, ModelCardWorker


class ModelsPanel(QWidget):
    request_show_info = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    gemini_use_for_ask_ai = pyqtSignal(str)  # model id e.g. google/gemini-2.5-flash

    def __init__(
        self,
        theme: dict,
        state: ModelSelectorState,
        parent=None,
        openai_compat: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.state = state
        self.openai_compat = dict(openai_compat or {})
        self._query_worker: Optional[HfQueryWorker] = None
        self._dl_worker: Optional[DownloadWorker] = None
        self._card_worker: Optional[ModelCardWorker] = None
        self._gemini_rows: List[Dict[str, Any]] = []
        self._hf_rows: List[Dict[str, Any]] = []
        self._kind_filter = "all"  # all | embedding | chat
        self._build()
        self.apply_theme()
        self._restore()

    def _build(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ── HuggingFace (local GGUF discovery) ──
        hf_page = QWidget()
        hf_layout = QVBoxLayout(hf_page)

        row = QHBoxLayout()
        # Embedding first (Launch :8080), then chat (:8081) — matches Launch order.
        self.query_embed_btn = _action_btn(
            "Query HF Hub - Embedding Models", "#5C6BC0", "#FFFFFF"
        )
        self.query_embed_btn.clicked.connect(lambda: self._start_query(embedding=True))
        self.query_btn = _action_btn("Query HF Hub - Chat Models", "#FF9800")
        self.query_btn.clicked.connect(lambda: self._start_query(embedding=False))
        self.download_btn = _action_btn("DOWNLOAD", "#FFC107")
        self.download_btn.clicked.connect(self._start_download)
        self.clear_btn = _action_btn("CLEAR", "#C44A4A", "#FFFFFF")
        self.clear_btn.clicked.connect(self._clear_all)
        self.export_btn = _action_btn("EXPORT PDF", "#6D9E5A", "#FFFFFF")
        self.export_btn.clicked.connect(self._export_pdf)
        self.view_info_btn = _action_btn("Model Info", "#5C6BC0", "#FFFFFF")
        self.view_info_btn.clicked.connect(self._view_info)
        self.open_browser_btn = _action_btn("Open in Browser", "#FF9800")
        self.open_browser_btn.setToolTip("Open the selected model page on huggingface.co")
        self.open_browser_btn.clicked.connect(self._open_in_browser)
        self.open_browser_btn.setEnabled(False)

        for b in (
            self.query_embed_btn,
            self.query_btn,
            self.download_btn,
            self.clear_btn,
            self.export_btn,
            self.view_info_btn,
            self.open_browser_btn,
        ):
            row.addWidget(b)
        row.addStretch()
        hf_layout.addLayout(row)

        # Same filter bar as Launch (text + embeddings / chat / clear).
        filt = QHBoxLayout()
        filt.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setMaximumWidth(220)
        self.filter_edit.textChanged.connect(self._apply_filter)
        filt.addWidget(self.filter_edit)
        self.filter_embed_btn = _action_btn("Filter Embeddings", "#5C6BC0", "#FFFFFF")
        self.filter_embed_btn.setCheckable(True)
        self.filter_embed_btn.setToolTip("Show only embedding models (kind column)")
        self.filter_embed_btn.clicked.connect(self._on_filter_embed_clicked)
        filt.addWidget(self.filter_embed_btn)
        self.filter_chat_btn = _action_btn("Filter Chat", "#FF9800")
        self.filter_chat_btn.setCheckable(True)
        self.filter_chat_btn.setToolTip("Show only chat / instruct models")
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
        self.filter_count = QLabel("")
        filt.addWidget(self.filter_count)
        filt.addStretch()
        hf_layout.addLayout(filt)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [
                "#",
                "Model ID",
                "Kind",
                "Params",
                "Size (GB)",
                "Score",
                "Ctx",
                "tok/s",
                "Fit",
                "Downloads",
                "Likes",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(6, 80)
        self.table.setColumnWidth(7, 100)
        self.table.setColumnWidth(8, 70)
        self.table.itemSelectionChanged.connect(self._on_select)
        hf_layout.addWidget(self.table)

        bottom = QHBoxLayout()
        self.download_status = QLabel("")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setValue(0)
        bottom.addWidget(self.download_status, stretch=1)
        bottom.addWidget(self.progress)
        hf_layout.addLayout(bottom)

        has_hw = bool(self.state.hardware_specs)
        self.query_btn.setEnabled(has_hw)
        self.query_embed_btn.setEnabled(has_hw)
        self.download_btn.setEnabled(False)
        self.export_btn.setEnabled(bool(self.state.model_data or self.state.close_data))
        self.view_info_btn.setEnabled(False)
        self.open_browser_btn.setEnabled(False)

        self.tabs.addTab(hf_page, "HuggingFace")

        # ── Gemini / Vertex OpenAI-compatible ──
        gem_page = QWidget()
        gem_layout = QVBoxLayout(gem_page)
        hint = QLabel(
            "Vertex OpenAI-compatible chat models (Ask AI). "
            "GET /models often 404s on Vertex — Spock shows Google’s documented "
            "google/gemini-* catalog and can Probe access with ADC.\n"
            "CLI tip: with a Gemini API key, "
            "curl https://generativelanguage.googleapis.com/v1beta/openai/models "
            "-H \"Authorization: Bearer $KEY\""
        )
        hint.setWordWrap(True)
        gem_layout.addWidget(hint)

        gem_btns = QHBoxLayout()
        self.gemini_refresh_btn = _action_btn("Refresh list", "#5C6BC0", "#FFFFFF")
        self.gemini_refresh_btn.clicked.connect(self._gemini_refresh)
        self.gemini_probe_btn = _action_btn("Probe selected", "#FF9800")
        self.gemini_probe_btn.clicked.connect(self._gemini_probe_selected)
        self.gemini_use_btn = _action_btn("Use for Ask AI", "#2A9D8F", "#FFFFFF")
        self.gemini_use_btn.clicked.connect(self._gemini_use_selected)
        self.gemini_docs_btn = _action_btn("Open docs", "#6D9E5A", "#FFFFFF")
        self.gemini_docs_btn.clicked.connect(self._gemini_open_docs)
        for b in (
            self.gemini_refresh_btn,
            self.gemini_probe_btn,
            self.gemini_use_btn,
            self.gemini_docs_btn,
        ):
            gem_btns.addWidget(b)
        gem_btns.addStretch()
        gem_layout.addLayout(gem_btns)

        self.gemini_base_lbl = QLabel("")
        self.gemini_base_lbl.setWordWrap(True)
        self.gemini_base_lbl.setStyleSheet("color: #8aa0ad;")
        gem_layout.addWidget(self.gemini_base_lbl)

        self.gemini_table = QTableWidget(0, 5)
        self.gemini_table.setHorizontalHeaderLabels(
            ["#", "Model ID", "Family", "Tier", "Notes / Probe"]
        )
        self.gemini_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.gemini_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.gemini_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.gemini_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.gemini_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self.gemini_table.setColumnWidth(0, 40)
        self.gemini_table.setColumnWidth(2, 100)
        self.gemini_table.setColumnWidth(3, 90)
        gem_layout.addWidget(self.gemini_table)

        self.gemini_status = QLabel("")
        self.gemini_status.setWordWrap(True)
        gem_layout.addWidget(self.gemini_status)

        self.tabs.addTab(gem_page, "Gemini (Vertex)")
        self._gemini_refresh()

    def _restore(self):
        rows: List[Dict[str, Any]] = []
        for m in self.state.model_data:
            kind = m.get("kind", "chat")
            params_b = m.get("size_b")
            size_gb = m.get("size_gb")
            if size_gb is None and params_b is not None:
                size_gb = _estimate_gguf_size_gb(float(params_b), str(m.get("id") or ""))
            rows.append(
                {
                    "id": str(m["id"]),
                    "kind": str(kind),
                    "params_txt": f"{params_b}B",
                    "size_gb": float(size_gb or 0),
                    "score": int(m.get("score") or 0),
                    "native_ctx": int(m.get("native_ctx") or 0),
                    "estimated_tps": m.get("estimated_tps"),
                    "fit_level": m.get("fit_level"),
                    "llmfit_run_mode": m.get("llmfit_run_mode"),
                    "downloads": int(m.get("downloads") or 0),
                    "likes": int(m.get("likes") or 0),
                    "params_b": params_b,
                }
            )
        for m in self.state.close_data:
            kind = m.get("kind", "chat")
            params_b = m.get("size_b")
            size_gb = m.get("size_gb")
            if size_gb is None and params_b is not None:
                size_gb = _estimate_gguf_size_gb(float(params_b), str(m.get("id") or ""))
            rows.append(
                {
                    "id": f"{m['id']}  (close)",
                    "kind": str(kind),
                    "params_txt": f"{params_b}B",
                    "size_gb": float(size_gb or 0),
                    "score": int(m.get("score") or 0),
                    "native_ctx": int(m.get("native_ctx") or 0),
                    "estimated_tps": m.get("estimated_tps"),
                    "fit_level": m.get("fit_level"),
                    "llmfit_run_mode": m.get("llmfit_run_mode"),
                    "downloads": int(m.get("downloads") or 0),
                    "likes": int(m.get("likes") or 0),
                    "params_b": params_b,
                }
            )
        self._hf_rows = rows
        self._apply_filter()
        if rows:
            self.download_status.setText(
                f"{len(rows)} models listed. Ctrl+click to multi-select, then DOWNLOAD."
            )
            self.view_info_btn.setEnabled(True)
            self.open_browser_btn.setEnabled(True)
            self.export_btn.setEnabled(True)

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
        for orig_i, m in enumerate(self._hf_rows, start=1):
            kind = str(m.get("kind") or "chat").lower()
            is_embed = kind == "embedding" or "embed" in kind
            if self._kind_filter == "embedding" and not is_embed:
                continue
            if self._kind_filter == "chat" and is_embed:
                continue
            mid = str(m.get("id") or "")
            if not allow(mid):
                continue
            if query and query not in mid.lower() and query not in kind:
                continue
            shown += 1
            r = self.table.rowCount()
            self.table.insertRow(r)
            idx_item = _SortableTableItem(str(orig_i))
            idx_item.setData(Qt.ItemDataRole.UserRole, int(orig_i))
            self.table.setItem(r, 0, idx_item)
            self.table.setItem(r, 1, _SortableTableItem(mid))
            self.table.setItem(r, 2, _SortableTableItem(str(m.get("kind") or "")))
            params_item = _SortableTableItem(str(m.get("params_txt") or ""))
            try:
                params_item.setData(Qt.ItemDataRole.UserRole, float(m.get("params_b") or 0))
            except (TypeError, ValueError):
                params_item.setData(Qt.ItemDataRole.UserRole, 0.0)
            self.table.setItem(r, 3, params_item)
            size_gb = float(m.get("size_gb") or 0)
            gb_item = _SortableTableItem(f"{size_gb:.2f}")
            gb_item.setData(Qt.ItemDataRole.UserRole, size_gb)
            self.table.setItem(r, 4, gb_item)
            score = int(m.get("score") or 0)
            score_item = _SortableTableItem(str(score))
            score_item.setData(Qt.ItemDataRole.UserRole, score)
            self.table.setItem(r, 5, score_item)
            ctx = int(m.get("native_ctx") or 0)
            ctx_item = _SortableTableItem(f"{ctx:,}" if ctx else "")
            ctx_item.setData(Qt.ItemDataRole.UserRole, ctx)
            self.table.setItem(r, 6, ctx_item)
            tps = m.get("estimated_tps")
            try:
                tps_f = float(tps) if tps is not None else 0.0
            except (TypeError, ValueError):
                tps_f = 0.0
            tps_txt = f"{tps_f:.1f}" if tps_f > 0 else ""
            tps_item = _SortableTableItem(tps_txt)
            tps_item.setData(Qt.ItemDataRole.UserRole, tps_f)
            if tps_txt:
                fit_lbl = str(m.get("fit_level") or "")
                mode = str(m.get("llmfit_run_mode") or "")
                tip = f"llmfit estimate ~{tps_f:.1f} tok/s"
                if fit_lbl:
                    tip += f" ({fit_lbl})"
                if mode:
                    tip += f" · {mode}"
                tps_item.setToolTip(tip)
            self.table.setItem(r, 7, tps_item)
            fit_txt = str(m.get("fit_level") or "")
            fit_item = _SortableTableItem(fit_txt)
            fit_item.setData(Qt.ItemDataRole.UserRole, fit_txt)
            self.table.setItem(r, 8, fit_item)
            downloads = int(m.get("downloads") or 0)
            dl_item = _SortableTableItem(f"{downloads:,}")
            dl_item.setData(Qt.ItemDataRole.UserRole, downloads)
            self.table.setItem(r, 9, dl_item)
            likes = int(m.get("likes") or 0)
            likes_item = _SortableTableItem(str(likes))
            likes_item.setData(Qt.ItemDataRole.UserRole, likes)
            self.table.setItem(r, 10, likes_item)
        total = len(self._hf_rows)
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
        self.table.sortByColumn(5, Qt.SortOrder.DescendingOrder)

    def _start_query(self, embedding: bool = False):
        if not self.state.hardware_specs:
            QMessageBox.warning(
                self, "No Hardware Data", "Scan hardware first from Hardware Scan."
            )
            return
        self.query_btn.setEnabled(False)
        self.query_embed_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        msg = (
            "STATUS: QUERYING HF HUB — EMBEDDING MODELS..."
            if embedding
            else "STATUS: QUERYING HF HUB — CHAT MODELS..."
        )
        self.state.status_message = msg
        self.status_changed.emit(msg)
        self._query_worker = HfQueryWorker(
            self.state.hardware_specs, embedding=embedding, parent=self
        )
        self._query_worker.finished_ok.connect(
            lambda models, close, emb=embedding: self._on_query_ok(models, close, emb)
        )
        self._query_worker.failed.connect(self._on_query_fail)
        self._query_worker.start()

    def _on_query_ok(self, models: list, close: list, embedding: bool = False):
        self.query_btn.setEnabled(True)
        self.query_embed_btn.setEnabled(True)
        if models and "error" in models[0]:
            self.download_status.setText(f"ERROR: {models[0]['error']}")
            self.state.status_message = "STATUS: QUERY FAILED"
            self.status_changed.emit(self.state.status_message)
            return

        self.state.model_data = [m for m in models[:15] if "error" not in m]
        self.state.close_data = close[:10]
        # Align kind filter with the query just run (embed-first workflow).
        if embedding:
            self._kind_filter = "embedding"
            self.filter_embed_btn.setChecked(True)
            self.filter_chat_btn.setChecked(False)
        else:
            self._kind_filter = "chat"
            self.filter_chat_btn.setChecked(True)
            self.filter_embed_btn.setChecked(False)
        self._restore()
        self.export_btn.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.state.status_message = (
            "STATUS: EMBEDDING QUERY COMPLETE"
            if embedding
            else "STATUS: QUERY COMPLETE"
        )
        self.status_changed.emit(self.state.status_message)

    def _on_query_fail(self, err: str):
        self.query_btn.setEnabled(True)
        self.query_embed_btn.setEnabled(True)
        self.state.status_message = f"STATUS: QUERY FAILED - {err}"
        self.status_changed.emit(self.state.status_message)
        self.download_status.setText(f"ERROR: {err}")

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.download_status.setText(
                f"{len(rows)} model(s) selected. Click DOWNLOAD."
            )
            self.download_btn.setEnabled(True)
            self.view_info_btn.setEnabled(True)
            self.open_browser_btn.setEnabled(True)
            item = self.table.item(rows[0].row(), 1)
            if item:
                model_id = item.text().replace("  (close)", "").strip()
                self.state.selected_hf_model_id = model_id
                self._prefetch_card(model_id)
        else:
            self.view_info_btn.setEnabled(False)
            self.open_browser_btn.setEnabled(False)

    def _prefetch_card(self, model_id: str):
        self.state.info_card_text = f"Loading model card for {model_id}..."
        self._card_worker = ModelCardWorker(model_id, self)
        self._card_worker.finished_ok.connect(self._on_card)
        self._card_worker.start()

    def _on_card(self, text: str):
        self.state.info_card_text = text

    def _view_info(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "No Selection", "Select a model from the list first.")
            return
        item = self.table.item(rows[0].row(), 1)
        model_id = item.text().replace("  (close)", "").strip()
        self.state.selected_hf_model_id = model_id
        self.request_show_info.emit(model_id)

    def _open_in_browser(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "No Selection", "Select a model from the list first.")
            return
        item = self.table.item(rows[0].row(), 1)
        if not item:
            QMessageBox.warning(self, "No Selection", "Select a model from the list first.")
            return
        model_id = item.text().replace("  (close)", "").strip()
        if not model_id:
            QMessageBox.warning(self, "No Selection", "Select a model from the list first.")
            return
        QDesktopServices.openUrl(QUrl(f"https://huggingface.co/{model_id}"))

    def _selected_model_ids(self) -> List[str]:
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            item = self.table.item(idx.row(), 1)
            if item:
                ids.append(item.text().replace("  (close)", "").strip())
        return ids

    def _start_download(self):
        model_ids = self._selected_model_ids()
        if not model_ids:
            QMessageBox.warning(
                self,
                "No Selection",
                "Select one or more models from the list first.\n\n"
                "Click a row to select. Hold Ctrl or Shift for multi-select.",
            )
            return
        preview = "\n".join(model_ids[:5]) + ("\n..." if len(model_ids) > 5 else "")
        reply = QMessageBox.question(
            self,
            "Confirm Download",
            f"Download {len(model_ids)} model(s) to .\\models ?\n\n{preview}\n\n"
            "Saves a preferred Q4/Q5 GGUF (not every quant in the Hub repo) "
            "for Spock Launch / llama-server.\n"
            "LM Studio is not required.\n\n"
            "This may take a while for large files. Status updates appear under the table.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.download_btn.setEnabled(False)
        self.progress.setMaximum(max(1, len(model_ids)))
        self.progress.setValue(0)
        self.download_status.setText("Starting Hugging Face download…")
        self.state.status_message = "STATUS: DOWNLOADING..."
        self.status_changed.emit(self.state.status_message)
        self._dl_worker = DownloadWorker(model_ids, self)
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.finished_ok.connect(self._on_dl_done)
        self._dl_worker.failed.connect(self._on_dl_fail)
        self._dl_worker.start()

    def _on_dl_progress(self, text: str, value: float):
        self.download_status.setText(text)
        self.progress.setValue(int(value))

    def _on_dl_done(self, text: str):
        self.download_status.setText(text)
        self.progress.setValue(self.progress.maximum())
        self.download_btn.setEnabled(True)
        self.state.status_message = "STATUS: DOWNLOAD COMPLETE"
        self.status_changed.emit(self.state.status_message)
        QMessageBox.information(self, "Download complete", text)

    def _on_dl_fail(self, err: str):
        self.download_status.setText(f"ERROR: {err}")
        self.download_btn.setEnabled(True)
        self.state.status_message = "STATUS: DOWNLOAD FAILED"
        self.status_changed.emit(self.state.status_message)
        QMessageBox.critical(
            self,
            "Download failed",
            f"{err}\n\n"
            "Tips for a new Windows install:\n"
            "• Prefer Spock.bat / Spock-Wizard.bat (avoid PowerShell script policy).\n"
            "• Red PowerShell 'NativeCommandError' lines are often HF Hub warnings "
            "on stderr — check this dialog / status line for the real error.\n"
            "• Set hf_token in config.json (Onboarding) if the repo is gated or rate-limited.\n"
            "• Ensure disk space under .\\models and a working network path to huggingface.co.",
        )

    def _clear_all(self):
        """Clear HF query results / selection — keep hardware scan so Query stays enabled."""
        self.state.model_data = []
        self.state.close_data = []
        self.state.selected_hf_model_id = ""
        self.state.info_card_text = (
            "Select a model from the Models tab to view its details here."
        )
        self.state.status_message = "STATUS: STANDBY"
        self.table.setRowCount(0)
        self.download_status.setText("")
        self.progress.setValue(0)
        has_hw = bool(self.state.hardware_specs)
        self.query_btn.setEnabled(has_hw)
        self.query_embed_btn.setEnabled(has_hw)
        self.export_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.view_info_btn.setEnabled(False)
        self.open_browser_btn.setEnabled(False)
        self._kind_filter = "all"
        if hasattr(self, "filter_edit"):
            self.filter_edit.blockSignals(True)
            self.filter_edit.clear()
            self.filter_edit.blockSignals(False)
            self.filter_embed_btn.setChecked(False)
            self.filter_chat_btn.setChecked(False)
            self.filter_count.setText("")
        self.status_changed.emit(self.state.status_message)

    def _export_pdf(self):
        if not PDF_AVAILABLE:
            QMessageBox.critical(
                self, "Error", "reportlab not installed. Run: pip install reportlab"
            )
            return
        hw = self.state.hardware_report
        model_lines = []
        for r in range(self.table.rowCount()):
            vals = [
                self.table.item(r, c).text() if self.table.item(r, c) else ""
                for c in range(1, 9)
            ]
            model_lines.append(
                f"{vals[0]}  |  {vals[1]}  |  {vals[2]}  |  {vals[3]} GB  |  "
                f"score {vals[4]}  |  ctx {vals[5]}  |  DL: {vals[6]}  |  Likes: {vals[7]}"
            )
        if not hw and not model_lines:
            QMessageBox.warning(
                self, "Warning", "No data to export. Run scan and query first."
            )
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            "Spock-Model-Selector-Report.pdf",
            "PDF files (*.pdf)",
        )
        if not filename:
            return
        try:
            export_report_pdf(filename, hw, model_lines)
            QMessageBox.information(self, "Success", f"PDF saved to:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create PDF:\n{e}")

    def set_openai_compat(self, cfg: Dict[str, Any]) -> None:
        self.openai_compat = dict(cfg or {})
        base = (self.openai_compat.get("openai_compat_base_url") or "").strip()
        self.gemini_base_lbl.setText(f"Base: {base or '(not configured — Connect OpenAI-compatible first)'}")

    def _gemini_selected_id(self) -> str:
        rows = self.gemini_table.selectionModel().selectedRows()
        if not rows:
            return ""
        item = self.gemini_table.item(rows[0].row(), 1)
        return (item.text() if item else "").strip()

    def _gemini_refresh(self) -> None:
        base = (self.openai_compat.get("openai_compat_base_url") or "").strip()
        key = self.openai_compat.get("openai_compat_api_key") or "adc"
        self.set_openai_compat(self.openai_compat)
        self.gemini_status.setText("Refreshing…")
        QApplication.processEvents()
        try:
            rows, detail = list_models_for_ui(base, key)
        except Exception as e:
            rows, detail = [], str(e)
        self._gemini_rows = rows
        self.gemini_table.setRowCount(0)
        for i, row in enumerate(rows, start=1):
            r = self.gemini_table.rowCount()
            self.gemini_table.insertRow(r)
            vals = [
                str(i),
                row.get("id", ""),
                row.get("family", ""),
                row.get("tier", ""),
                row.get("notes", ""),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c == 0:
                    item.setData(Qt.ItemDataRole.DisplayRole, i)
                self.gemini_table.setItem(r, c, item)
        current = (self.openai_compat.get("openai_compat_model") or "").strip()
        if current:
            for r in range(self.gemini_table.rowCount()):
                if self.gemini_table.item(r, 1) and self.gemini_table.item(r, 1).text() == current:
                    self.gemini_table.selectRow(r)
                    break
        self.gemini_status.setText(detail)
        self.status_changed.emit(detail)

    def _gemini_probe_selected(self) -> None:
        mid = self._gemini_selected_id()
        if not mid:
            QMessageBox.information(self, "Gemini", "Select a model row first.")
            return
        base = (self.openai_compat.get("openai_compat_base_url") or "").strip()
        key = self.openai_compat.get("openai_compat_api_key") or "adc"
        if not base:
            QMessageBox.warning(
                self,
                "Gemini",
                "Configure OpenAI-compatible base URL first (Connect OpenAI-compatible).",
            )
            return
        self.gemini_status.setText(f"Probing {mid}…")
        QApplication.processEvents()
        ok, detail = probe_model_chat(base, mid, key)
        note = f"{'✓' if ok else '✗'} {detail}"
        rows = self.gemini_table.selectionModel().selectedRows()
        if rows:
            self.gemini_table.setItem(rows[0].row(), 4, QTableWidgetItem(note))
        self.gemini_status.setText(f"{mid}: {detail}")
        if ok:
            QMessageBox.information(self, "Probe OK", f"{mid}\n{detail}")
        else:
            QMessageBox.warning(self, "Probe failed", f"{mid}\n{detail}")

    def _gemini_use_selected(self) -> None:
        mid = self._gemini_selected_id()
        if not mid:
            QMessageBox.information(self, "Gemini", "Select a model row first.")
            return
        self.openai_compat["openai_compat_model"] = mid
        self.gemini_use_for_ask_ai.emit(mid)
        self.gemini_status.setText(f"Selected for Ask AI: {mid}")
        self.status_changed.emit(f"Ask AI model → {mid}")

    def _gemini_open_docs(self) -> None:
        QDesktopServices.openUrl(
            QUrl(
                "https://docs.cloud.google.com/gemini-enterprise-agent-platform/"
                "models/google-models?hl=en#generally-available-gemini-models"
            )
        )

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))


# ── Model Info ──────────────────────────────────────────────────────────
