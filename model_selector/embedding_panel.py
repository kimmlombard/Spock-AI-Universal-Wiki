"""Embedding profile + RAG API panel."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from model_selector_core import (
    acquire_embedding_result,
    embedding_profile_identity,
    merge_embedding_profile,
    probe_embeddings_dim,
    sample_db_embedding_dim,
    sync_acquire_n_ctx_to_recipe,
    write_embedding_env,
)

from .widgets import _action_btn, _panel_stylesheet


class EmbeddingProfilePanel(QWidget):
    """Tune ingest/RAG embeddings + llama-server -b/-ub; start external RAG API."""

    profile_applied = pyqtSignal(dict)
    acquire_adopted = pyqtSignal(dict)  # after USE ACQUIRE RESULT syncs recipe -c
    rag_api_start = pyqtSignal()
    rag_api_stop = pyqtSignal()

    def __init__(
        self,
        theme: dict,
        profile: Optional[Dict[str, Any]] = None,
        rag_api: Optional[Dict[str, Any]] = None,
        db_path: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.db_path = db_path
        self.profile = merge_embedding_profile(profile)
        self.rag_api = dict(rag_api or {})
        self._acquire: Dict[str, Any] = {}
        self._build()
        self.apply_theme()
        self._load_fields()
        self.refresh_from_acquire()

    def _build(self):
        layout = QVBoxLayout(self)
        title = QLabel("Embedding Profile")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #FF9800;")
        layout.addWidget(title)
        hint = QLabel(
            "Chat LLM (LM Studio / instruct GGUF) stays separate. "
            "This profile drives wiki ingest, RAG embeddings, and Launch -b/-ub."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa;")
        layout.addWidget(hint)

        form = QGridLayout()
        self.url_edit = QLineEdit()
        self.dim_spin = QSpinBox()
        self.dim_spin.setRange(64, 16384)
        self.dim_spin.setSingleStep(64)
        self.truncate_spin = QSpinBox()
        self.truncate_spin.setRange(100, 32000)
        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(1, 256)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 64)
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(32, 8192)
        self.ubatch_spin = QSpinBox()
        self.ubatch_spin.setRange(32, 8192)
        self.model_path_edit = QLineEdit()
        self.model_id_edit = QLineEdit()
        self.probe_cb = QCheckBox("Probe dim on Apply (POST /embeddings)")

        rows = [
            ("Embeddings URL", self.url_edit),
            ("Expected dim", self.dim_spin),
            ("Truncate chars", self.truncate_spin),
            ("Batch chunk", self.chunk_spin),
            ("Batch workers", self.workers_spin),
            ("llama -b (batch)", self.batch_spin),
            ("llama -ub (ubatch)", self.ubatch_spin),
            ("Model path", self.model_path_edit),
            ("Model id", self.model_id_edit),
        ]
        for i, (label, widget) in enumerate(rows):
            form.addWidget(QLabel(label), i, 0)
            form.addWidget(widget, i, 1)
        form.addWidget(self.probe_cb, len(rows), 0, 1, 2)
        layout.addLayout(form)

        acquire_row = QHBoxLayout()
        self.acquire_lbl = QLabel("")
        self.acquire_lbl.setWordWrap(True)
        self.acquire_lbl.setStyleSheet("color: #2A9D8F;")
        self.use_acquire_btn = _action_btn("USE ACQUIRE RESULT", "#00897B", "#FFFFFF")
        self.use_acquire_btn.setToolTip(
            "Copy the embedding GGUF from Bringup step 3 Acquire into Model path / "
            "Model id, and write Acquire's embed/chat -c onto the host recipe so "
            "Launch / Bringup step 4 use those context sizes. Re-launch both servers "
            "afterward — a running llama-server keeps its old -c."
        )
        self.use_acquire_btn.clicked.connect(self._adopt_acquire_result)
        acquire_row.addWidget(self.acquire_lbl, 1)
        acquire_row.addWidget(self.use_acquire_btn)
        layout.addLayout(acquire_row)

        note = QLabel(
            "Note: with --embeddings, llama-server may clamp -b to -ub (often 512)."
        )
        note.setStyleSheet("color: #FFC107;")
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        self.apply_btn = _action_btn("APPLY / SAVE", "#6D9E5A", "#FFFFFF")
        self.apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(self.apply_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #aaa;")
        layout.addWidget(self.status_lbl)

        # RAG API section
        rag_box = QGroupBox("External RAG API + Browser Web UI")
        rag_layout = QVBoxLayout(rag_box)
        rag_hint = QLabel(
            "START RAG API serves Spock Ask AI / Deep Dive from templates/webui at "
            "http://HOST:PORT/  (dark teal UI — not llama.cpp WebUI on :8082).\n"
            "JSON: POST /v1/chat/completions with model \"spock-ships-computer\".\n"
            "Optional body fields: spock_mode (ask|deep_dive), spock_path_filter, spock_extension (.py,.ts,…).\n"
            "Chat LLM is separate (Connect llamaccp / OpenAI-compatible → :8081 or Vertex).\n"
            "In-app chat remains on left-nav Ask AI (same LLM backend)."
        )
        rag_hint.setWordWrap(True)
        rag_layout.addWidget(rag_hint)
        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("Host:"))
        self.rag_host = QLineEdit(self.rag_api.get("host", "127.0.0.1"))
        host_row.addWidget(self.rag_host)
        host_row.addWidget(QLabel("Port:"))
        self.rag_port = QSpinBox()
        self.rag_port.setRange(1, 65535)
        self.rag_port.setValue(int(self.rag_api.get("port", 8090)))
        host_row.addWidget(self.rag_port)
        rag_layout.addLayout(host_row)
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API key (optional):"))
        self.rag_key = QLineEdit(self.rag_api.get("api_key", ""))
        self.rag_key.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(self.rag_key)
        rag_layout.addLayout(key_row)
        self.rag_url_lbl = QLabel("")
        self.rag_url_lbl.setStyleSheet("color: #5C6BC0;")
        rag_layout.addWidget(self.rag_url_lbl)
        rag_btns = QHBoxLayout()
        self.rag_start_btn = _action_btn("START RAG API", "#5C6BC0", "#FFFFFF")
        self.rag_start_btn.clicked.connect(self._emit_rag_start)
        self.rag_stop_btn = _action_btn("STOP RAG API", "#C44A4A", "#FFFFFF")
        self.rag_stop_btn.clicked.connect(lambda: self.rag_api_stop.emit())
        self.rag_copy_btn = _action_btn("COPY API URL", "#FF9800")
        self.rag_copy_btn.clicked.connect(self._copy_rag_url)
        self.rag_open_web_btn = _action_btn("OPEN WEB UI", "#2A9D8F", "#FFFFFF")
        self.rag_open_web_btn.setToolTip("Open Ask AI / Deep Dive chat in your browser")
        self.rag_open_web_btn.clicked.connect(self._open_rag_web_ui)
        rag_btns.addWidget(self.rag_start_btn)
        rag_btns.addWidget(self.rag_stop_btn)
        rag_btns.addWidget(self.rag_copy_btn)
        rag_btns.addWidget(self.rag_open_web_btn)
        rag_btns.addStretch()
        rag_layout.addLayout(rag_btns)
        self.rag_status = QLabel("RAG API: stopped")
        rag_layout.addWidget(self.rag_status)
        layout.addWidget(rag_box)
        layout.addStretch()
        self._refresh_rag_url()

    def _load_fields(self):
        p = self.profile
        self.url_edit.setText(str(p.get("embeddings_url", "")))
        self.dim_spin.setValue(int(p.get("embeddings_dim", 4096)))
        self.truncate_spin.setValue(int(p.get("truncate_chars", 1500)))
        self.chunk_spin.setValue(int(p.get("batch_chunk", 32)))
        self.workers_spin.setValue(int(p.get("batch_workers", 8)))
        self.batch_spin.setValue(int(p.get("llama_batch", 512)))
        self.ubatch_spin.setValue(int(p.get("llama_ubatch", 512)))
        self.model_path_edit.setText(str(p.get("model_path", "")))
        self.model_id_edit.setText(str(p.get("model_id", "")))
        self.probe_cb.setChecked(bool(p.get("probe_on_apply", True)))

    def _acquire_root(self) -> Optional[str]:
        return os.path.dirname(self.db_path) if self.db_path else None

    def refresh_from_acquire(self, *, adopt: bool = False, fill: bool = True) -> None:
        """Show (and by default pre-fill) the embedding GGUF from step 3 Acquire.

        ``fill`` writes into empty / stale fields; ``adopt`` overwrites whatever
        is there. Values are only persisted when the user clicks APPLY / SAVE.
        """
        info = acquire_embedding_result(self._acquire_root())
        self._acquire = info
        if not info:
            self.acquire_lbl.setText(
                "Step 3 Acquire: no first_models_last.json yet — run Bringup step 3 "
                "to fill Model path / Model id automatically."
            )
            self.use_acquire_btn.setEnabled(False)
            return

        path = str(info.get("model_path") or "")
        model_id = str(info.get("model_id") or "")
        dim = info.get("embeddings_dim")
        current_path = self.model_path_edit.text().strip()
        current_id = self.model_id_edit.text().strip()
        stale_path = bool(current_path) and not os.path.isfile(current_path)

        changed = False
        if path and (adopt or (fill and (not current_path or stale_path))):
            self.model_path_edit.setText(path)
            changed = True
        if model_id and (adopt or (fill and not current_id)):
            self.model_id_edit.setText(model_id)
            changed = True
        if changed and dim:
            self.dim_spin.setValue(int(dim))

        name = os.path.basename(path) or model_id or "?"
        detail = f"dim {dim}" if dim else (info.get("quant") or "dim not probed yet")
        n_ctx_bits = []
        if info.get("embed_n_ctx"):
            n_ctx_bits.append(f"embed -c {info['embed_n_ctx']}")
        if info.get("chat_n_ctx"):
            n_ctx_bits.append(f"chat -c {info['chat_n_ctx']}")
        if n_ctx_bits:
            detail = f"{detail}; " + ", ".join(n_ctx_bits)
        matches = (
            (not path or self.model_path_edit.text().strip() == path)
            and (not model_id or self.model_id_edit.text().strip() == model_id)
        )
        if matches:
            suffix = (
                " — fields filled from this pick (APPLY / SAVE to keep)."
                if changed
                else " — matches the fields above."
            )
        else:
            suffix = " — differs from the fields above; click USE ACQUIRE RESULT."
        self.acquire_lbl.setText(f"Step 3 Acquire: {name} ({detail}){suffix}")
        self.use_acquire_btn.setEnabled(True if adopt else not matches)

    def _adopt_acquire_result(self) -> None:
        """Adopt Acquire's GGUF + write its -c values onto the host recipe."""
        self.refresh_from_acquire(adopt=True)
        info = self._acquire or {}
        if not info:
            return
        sync_note = ""
        try:
            synced = sync_acquire_n_ctx_to_recipe(
                self.db_path,
                embed_n_ctx=info.get("embed_n_ctx"),
                chat_n_ctx=info.get("chat_n_ctx"),
                created_by="embed-panel",
            )
            recipe = synced.get("recipe") or {}
            if synced.get("updated"):
                sync_note = (
                    f" Host recipe v{synced.get('version')}: "
                    f"{recipe.get('gpu_policy')}, embed -c {recipe.get('embed_n_ctx')}, "
                    f"chat -c {recipe.get('chat_n_ctx')}"
                    + (
                        f", tensor-split {recipe.get('tensor_split')}"
                        if recipe.get("tensor_split")
                        else ""
                    )
                    + ". Re-launch embed (:8080) and chat (:8081) to apply."
                )
            else:
                sync_note = (
                    f" Host recipe already has embed -c {recipe.get('embed_n_ctx')}, "
                    f"chat -c {recipe.get('chat_n_ctx')} "
                    f"({recipe.get('gpu_policy')}). Re-launch if servers are stale."
                )
            self.acquire_adopted.emit(
                {
                    "embed_n_ctx": recipe.get("embed_n_ctx"),
                    "chat_n_ctx": recipe.get("chat_n_ctx"),
                    "gpu_policy": recipe.get("gpu_policy"),
                    "tensor_split": recipe.get("tensor_split"),
                    "updated": bool(synced.get("updated")),
                    "model_path": info.get("model_path"),
                    "model_id": info.get("model_id"),
                }
            )
        except Exception as e:
            sync_note = f" Host recipe -c sync failed: {e}"
        self.status_lbl.setText(
            "Adopted Acquire GGUF into the fields above — APPLY / SAVE to persist."
            + sync_note
        )
        self.acquire_lbl.setText(self.acquire_lbl.text() + sync_note)

    def _collect_profile(self) -> Dict[str, Any]:
        return merge_embedding_profile(
            {
                "embeddings_url": self.url_edit.text().strip(),
                "embeddings_dim": self.dim_spin.value(),
                "truncate_chars": self.truncate_spin.value(),
                "batch_chunk": self.chunk_spin.value(),
                "batch_workers": self.workers_spin.value(),
                "llama_batch": self.batch_spin.value(),
                "llama_ubatch": self.ubatch_spin.value(),
                "model_path": self.model_path_edit.text().strip(),
                "model_id": self.model_id_edit.text().strip(),
                "probe_on_apply": self.probe_cb.isChecked(),
            }
        )

    def collect_rag_api(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.rag_api.get("enabled", False)),
            "host": self.rag_host.text().strip() or "127.0.0.1",
            "port": self.rag_port.value(),
            "api_key": self.rag_key.text(),
        }

    def _apply(self):
        profile = self._collect_profile()
        if profile.get("probe_on_apply"):
            dim = probe_embeddings_dim(profile["embeddings_url"])
            if dim:
                profile["embeddings_dim"] = dim
                self.dim_spin.setValue(dim)
                self.status_lbl.setText(f"Probed dim={dim}")
            else:
                self.status_lbl.setText("Probe failed (server down?); keeping dim as set.")

        db_dim = sample_db_embedding_dim(self.db_path) if self.db_path else None
        if db_dim is not None and db_dim != int(profile["embeddings_dim"]):
            QMessageBox.warning(
                self,
                "Embedding dimension mismatch",
                f"Database embeddings are {db_dim}-dim, but profile expects "
                f"{profile['embeddings_dim']}.\n\n"
                "Vector search will be wrong until you re-embed documents or reset "
                "the DB (same issue as swapping 27B → 9B).",
            )

        write_embedding_env(profile)
        self.profile = profile
        self.rag_api = self.collect_rag_api()
        self.profile_applied.emit(profile)
        self.refresh_from_acquire(fill=False)
        self.status_lbl.setText(
            self.status_lbl.text() + " | Saved to app_config.json + .env"
            if self.status_lbl.text()
            else "Saved to app_config.json + .env"
        )

    def adopt_launched_embedding(self, model_path: str, model_id: str = "") -> None:
        """Write the GGUF just launched on :8080 into Model path and Model id."""
        if not model_path:
            return
        ident = embedding_profile_identity(model_path, model_id=model_id)
        new_path = ident["model_path"]
        new_id = ident["model_id"]
        if not new_path:
            return
        same = (
            os.path.normcase(self.model_path_edit.text().strip())
            == os.path.normcase(new_path)
            and self.model_id_edit.text().strip() == new_id
        )
        if same:
            return
        self.model_path_edit.setText(new_path)
        self.model_id_edit.setText(new_id)
        profile = self._collect_profile()
        write_embedding_env(profile)
        self.profile = profile
        self.profile_applied.emit(profile)
        self.status_lbl.setText(
            "Model path and Model id updated from Launch (:8080): "
            f"{os.path.basename(new_path)} — saved."
        )

    def _refresh_rag_url(self):
        host = self.rag_host.text().strip() or "127.0.0.1"
        port = self.rag_port.value()
        self.rag_url_lbl.setText(
            f"API http://{host}:{port}/v1  ·  Web UI http://{host}:{port}/"
        )

    def _emit_rag_start(self):
        self.rag_api = self.collect_rag_api()
        self._refresh_rag_url()
        self.rag_api_start.emit()

    def _copy_rag_url(self):
        self._refresh_rag_url()
        host = self.rag_host.text().strip() or "127.0.0.1"
        port = self.rag_port.value()
        api = f"http://{host}:{port}/v1"
        QApplication.clipboard().setText(api)
        self.rag_status.setText(f"Copied {api}")

    def _open_rag_web_ui(self):
        host = self.rag_host.text().strip() or "127.0.0.1"
        port = self.rag_port.value()
        # Root serves templates/webui Ask AI / Deep Dive — never open /v1 or :8082.
        url = f"http://{host}:{port}/"
        body = ""
        ctype = ""
        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=3) as resp:
                ctype = str(resp.headers.get("Content-Type") or "")
                body = resp.read(800).decode("utf-8", errors="replace")
        except Exception:
            QMessageBox.warning(
                self,
                "Web UI",
                "RAG API does not appear to be running on that host/port.\n\n"
                "Click START RAG API first, then OPEN WEB UI.\n\n"
                f"Expected Spock Ask AI (templates/webui) at: {url}\n"
                "Do not use llama.cpp WebUI (:8082) for this — that shell is different.",
            )
            return
        # Guard against opening the wrong process (e.g. llama.cpp UI on this port).
        looks_spock = (
            "Spock Ask AI" in body
            or "spock-ships-computer" in body
            or 'id="mode-ask"' in body
            or 'id="mode-deep"' in body
        )
        if not looks_spock:
            QMessageBox.warning(
                self,
                "Web UI",
                "Something responded on that port, but it is not Spock Ask AI "
                "(templates/webui).\n\n"
                f"URL: {url}\n"
                f"Content-Type: {ctype or '(unknown)'}\n\n"
                "Stop whatever else is bound to this port, click START RAG API, "
                "then OPEN WEB UI again.\n"
                "llama.cpp WebUI lives on :8082 (MCP panel) and is not Spock Ask AI.",
            )
            return
        # Cache-bust + no hash: llama.cpp uses #/chat/...; Spock is plain index.html.
        open_url = f"{url}?ui=spock-ask-ai&t={int(time.time())}"
        QMessageBox.information(
            self,
            "Spock Ask AI",
            "Opening the Spock Ask AI page (templates/webui).\n\n"
            f"{open_url}\n\n"
            "You should see a dark teal UI titled \"Spock Ask AI\" with Ask / Deep Dive.\n"
            "If you see a white page with a lightning bolt and \"Hello there\", that is "
            "llama.cpp WebUI (:8082) — wrong shell. Close it and use this URL only "
            "(no #/chat/... in the address bar).",
        )
        from spock_shell.open_url import open_url as _open_url

        _open_url(open_url)
        self.rag_status.setText(f"Opening Spock Ask AI {open_url}")

    def set_rag_running(self, running: bool, url: str = ""):
        if running:
            host = self.rag_host.text().strip() or "127.0.0.1"
            port = self.rag_port.value()
            web = f"http://{host}:{port}/"
            self.rag_status.setText(
                f"RAG API: running at {url or self.rag_url_lbl.text()} · Web UI {web}"
            )
            self.rag_status.setStyleSheet("color: #6D9E5A; font-weight: bold;")
        else:
            self.rag_status.setText("RAG API: stopped")
            self.rag_status.setStyleSheet("color: #aaa;")

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))


# ── Status window (non-modal) ───────────────────────────────────────────
