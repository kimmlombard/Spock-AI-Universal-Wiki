"""Named Spock configuration profiles, shared by every suite mini-app.

Profiles live in the ``spock_profile`` table of ``ship_computer.db``. The
payload shape is deliberately the same one the old monolith wrote, so a profile
saved in one app loads in any other:

    {"config": {...}, "servers": [...], "launch_ui": {...},
     "rag_was_running": bool, "mcp_was_running": bool,
     "webui_was_running": bool, "lm_studio": {...}}

An app only fills in the parts it owns. Engineering Deck has no Launch panel,
so it writes an empty ``launch_ui``; loading that profile elsewhere simply
restarts nothing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spock_shell.paths import SHIP_COMPUTER_DB, ensure_root_on_path

ensure_root_on_path()

from model_selector_core import (  # noqa: E402
    merge_embedding_profile,
    write_embedding_env,
)
from spock_profile_store import (  # noqa: E402
    count_profiles,
    delete_profiles,
    find_profile_by_name,
    get_profile,
    insert_profile,
    list_profile_summaries,
    list_profiles,
    stardate as profile_stardate,
    upsert_profile,
)
from WarpCore.config_defaults import merge_mcp_settings, merge_uieg_config  # noqa: E402
from WarpCore.search import set_embeddings_url  # noqa: E402

def prompts_enabled() -> bool:
    """False in headless / smoke runs, where a modal prompt would hang."""
    if os.environ.get("SPOCK_PROFILE_PROMPTS", "").strip().lower() in ("0", "off", "no"):
        return False
    return os.environ.get("QT_QPA_PLATFORM", "").strip().lower() != "offscreen"


_SESSION_LOADED_ENV = "SPOCK_PROFILE_SESSION_LOADED"


def profile_load_answered() -> bool:
    """True once something upstream has already asked about loading a profile.

    The orchestrator launches mini-apps as child processes with a copied
    environment, so marking the answer here stops every station re-asking the
    same question for one session.
    """
    return os.environ.get(_SESSION_LOADED_ENV, "").strip() == "1"


def mark_profile_load_answered() -> None:
    os.environ[_SESSION_LOADED_ENV] = "1"


def last_saved_profile_name() -> str:
    try:
        from WarpCore import settings_store

        val = settings_store.get(SHIP_COMPUTER_DB, "app.last_profile_name")
        return str(val or "").strip()
    except Exception:
        return ""


def remember_profile_name(name: str) -> None:
    label = (name or "").strip()
    if not label:
        return
    try:
        from WarpCore import settings_store

        settings_store.set(
            SHIP_COMPUTER_DB, "app.last_profile_name", label, by="app"
        )
    except Exception:
        pass


def confirm_replace_profile(parent: Optional[QWidget], name: str) -> bool:
    existing = find_profile_by_name(SHIP_COMPUTER_DB, name)
    if existing is None:
        return True
    if not prompts_enabled():
        return True
    reply = QMessageBox.question(
        parent,
        "Replace profile",
        f'A profile named "{name}" already exists.\nReplace it with the current settings?',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes


__all__ = [
    "LoadProfileDialog",
    "SaveProfileDialog",
    "ProfileReviewPanel",
    "open_manage_profiles_dialog",
    "apply_profile_payload",
    "build_profile_payload",
    "harvest_live_config",
    "mark_profile_load_answered",
    "maybe_load_profile",
    "pick_profile_payload",
    "profile_load_answered",
    "prompt_save_profile",
    "prompts_enabled",
    "save_profile_interactive",
    "warn_embedding_vs_wiki_scan",
]


# ── dialogs ──────────────────────────────────────────────────────────────
class SaveProfileDialog(QDialog):
    """Exit prompt: save a named profile, skip, or cancel the close."""

    RESULT_CANCEL = 0
    RESULT_SAVE = 1
    RESULT_SKIP = 2

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        default_name: str = "",
        *,
        allow_cancel: bool = True,
        prompt: str = "",
    ):
        super().__init__(parent)
        self._choice = self.RESULT_CANCEL if allow_cancel else self.RESULT_SKIP
        self.setWindowTitle("Save configuration profile")
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                prompt
                or "Save the current Spock configuration as a profile?\n"
                "(Ask AI provider, RAG, MCP, Embedding Profile, running servers)"
            )
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Profile name:"))
        self.name_edit = QLineEdit(default_name or profile_stardate())
        row.addWidget(self.name_edit)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(10)
        layout.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setStyleSheet("color: #aaa;")
        layout.addWidget(self.status)

        btns = QHBoxLayout()
        btns.addStretch()
        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        btns.addWidget(self.save_btn)
        self.skip_btn = QPushButton("Don't save")
        self.skip_btn.clicked.connect(self._on_skip)
        btns.addWidget(self.skip_btn)
        self.cancel_btn: Optional[QPushButton] = None
        if allow_cancel:
            self.cancel_btn = QPushButton("Cancel")
            self.cancel_btn.clicked.connect(self._on_cancel)
            btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

    def _set_busy(self, message: str = "Saving…") -> None:
        # Local feedback only — do not stack app override cursors (Windows sticks them).
        self.progress.setVisible(True)
        self.status.setText(message)
        self.save_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        if self.cancel_btn is not None:
            self.cancel_btn.setEnabled(False)
        self.name_edit.setEnabled(False)
        QApplication.processEvents()

    def _on_save(self):
        self._set_busy("Saving profile…")
        self._choice = self.RESULT_SAVE
        self.accept()

    def _on_skip(self):
        self._choice = self.RESULT_SKIP
        self.accept()

    def _on_cancel(self):
        self._choice = self.RESULT_CANCEL
        self.reject()

    @property
    def choice(self) -> int:
        return self._choice

    def profile_name(self) -> str:
        return (self.name_edit.text() or "").strip() or profile_stardate()


class LoadProfileDialog(QDialog):
    """Picker of saved profiles (newest first)."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        profiles: Optional[List[Tuple]] = None,
    ):
        super().__init__(parent)
        self._selected_id: Optional[int] = None
        self.setWindowTitle("Load configuration profile")
        self.setModal(True)
        self.setMinimumSize(480, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a profile to restore:"))
        self.list = QListWidget()
        for pid, name, sd, _created in profiles or []:
            extra = ""
            try:
                rec = get_profile(SHIP_COMPUTER_DB, int(pid))
                payload = (rec or {}).get("payload") or {}
                cfg = payload.get("config") or {}
                provider = str(cfg.get("ask_ai_provider") or "").strip()
                model = str(
                    cfg.get("openai_compat_model")
                    or cfg.get("lm_studio_model")
                    or cfg.get("ollama_model")
                    or ""
                ).strip()
                from spock_shell.embedding_corpus import (
                    model_basename,
                    profile_embedding_path,
                )

                gguf = model_basename(profile_embedding_path(payload))
                chat_path = str(cfg.get("chat_model_path") or "").strip()
                if not chat_path:
                    for srv in payload.get("servers") or []:
                        if not isinstance(srv, dict):
                            continue
                        if str(srv.get("role") or "").lower() == "chat":
                            chat_path = str(srv.get("model_path") or "").strip()
                            break
                chat_gguf = model_basename(chat_path)
                bits = [bit for bit in (provider, model, gguf, chat_gguf) if bit]
                if bits:
                    extra = "  —  " + " · ".join(bits)
            except Exception:
                extra = ""
            item = QListWidgetItem(f"{name}  ·  {sd}{extra}")
            item.setData(Qt.ItemDataRole.UserRole, int(pid))
            self.list.addItem(item)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(self._on_load)
        layout.addWidget(self.list)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(10)
        layout.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setStyleSheet("color: #aaa;")
        layout.addWidget(self.status)

        btns = QHBoxLayout()
        btns.addStretch()
        self.load_btn = QPushButton("Load")
        self.load_btn.setDefault(True)
        self.load_btn.clicked.connect(self._on_load)
        btns.addWidget(self.load_btn)
        self.fresh_btn = QPushButton("Start fresh")
        self.fresh_btn.clicked.connect(self.reject)
        btns.addWidget(self.fresh_btn)
        layout.addLayout(btns)

    def _set_busy(self, message: str = "Loading…") -> None:
        # Local feedback only — parent busy_scope owns the app wait cursor.
        self.progress.setVisible(True)
        self.status.setText(message)
        self.load_btn.setEnabled(False)
        self.fresh_btn.setEnabled(False)
        self.list.setEnabled(False)
        QApplication.processEvents()

    def _on_load(self):
        item = self.list.currentItem()
        if item is None:
            QMessageBox.information(self, "Load profile", "Select a profile first.")
            return
        self._set_busy("Loading profile… preparing restore")
        self._selected_id = int(item.data(Qt.ItemDataRole.UserRole))
        self.accept()

    @property
    def selected_id(self) -> Optional[int]:
        return self._selected_id


class ProfileReviewPanel(QWidget):
    """List, preview, and delete named profiles in ship_computer.db."""

    def __init__(self, db_path: str = "", parent=None):
        super().__init__(parent)
        self.db_path = db_path or SHIP_COMPUTER_DB
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(
            QLabel("Saved Spock configuration profiles (ship_computer.db → spock_profile):")
        )
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.currentItemChanged.connect(self._show_detail)
        lay.addWidget(self.list, 1)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(140)
        lay.addWidget(self.detail)
        btns = QHBoxLayout()
        self.load_btn = QPushButton("Load Selected Profile")
        self.load_btn.clicked.connect(self._load_selected)
        del_btn = QPushButton("Delete selected")
        del_btn.clicked.connect(self._delete_selected)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        btns.addWidget(self.load_btn)
        btns.addWidget(del_btn)
        btns.addWidget(refresh_btn)
        btns.addStretch()
        lay.addLayout(btns)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        self.detail.clear()
        try:
            rows = list_profile_summaries(self.db_path)
        except Exception as e:
            QMessageBox.warning(self, "Profiles", f"Could not list profiles:\n{e}")
            return
        for rec in rows:
            bits = [
                rec.get("name") or "",
                rec.get("stardate") or "",
                rec.get("embedding_model_name") or "",
                rec.get("ask_ai_provider") or "",
            ]
            label = "  ·  ".join(b for b in bits if b)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, rec)
            self.list.addItem(item)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def _show_detail(self, current, _previous=None) -> None:
        rec = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if not isinstance(rec, dict):
            self.detail.clear()
            return
        lines = [
            f"Name: {rec.get('name') or '—'}",
            f"Stardate: {rec.get('stardate') or '—'}",
            f"Ask AI: {rec.get('ask_ai_provider') or '—'}",
            f"Chat model: {rec.get('chat_model') or '—'}",
            f"Embedding GGUF: {rec.get('embedding_model_path') or rec.get('embedding_model_name') or '—'}",
            f"Embeddings URL: {rec.get('embeddings_url') or '—'}",
        ]
        self.detail.setPlainText("\n".join(lines))

    def _selected_profile_id(self) -> Optional[int]:
        items = self.list.selectedItems()
        if not items:
            current = self.list.currentItem()
            items = [current] if current is not None else []
        if len(items) != 1:
            return None
        rec = items[0].data(Qt.ItemDataRole.UserRole) or {}
        try:
            return int(rec.get("id"))
        except (TypeError, ValueError):
            return None

    def _load_selected(self) -> None:
        """Restore the selected profile into Spock_Console and start needed services."""
        profile_id = self._selected_profile_id()
        if profile_id is None:
            QMessageBox.information(
                self,
                "Load profile",
                "Select exactly one profile to load.",
            )
            return

        from spock_shell.busy_ui import busy_scope

        self.load_btn.setEnabled(False)
        done_name = ""
        error_title = ""
        error_text = ""
        try:
            with busy_scope(self, "Loading selected profile…"):
                try:
                    row = get_profile(self.db_path, profile_id)
                except Exception as e:
                    error_title, error_text = (
                        "Load profile",
                        f"Could not read profile:\n{e}",
                    )
                    return
                if not row:
                    error_title, error_text = "Load profile", "Profile not found."
                    return
                payload = row.get("payload") or {}
                if not isinstance(payload, dict):
                    error_title, error_text = (
                        "Load profile",
                        "Profile payload is empty.",
                    )
                    return

                from spock_shell.config import load_config, save_config
                from spock_shell.mcp_host import McpAdapterHost

                win = self.window()
                config = getattr(win, "config", None)
                if not isinstance(config, dict):
                    config = load_config()

                llama_manager = getattr(win, "server_manager", None) or getattr(
                    win, "manager", None
                )
                if llama_manager is None:
                    try:
                        from llama_server_manager import LlamaServerManager

                        llama_manager = LlamaServerManager()
                        try:
                            win.server_manager = llama_manager
                        except Exception:
                            pass
                    except Exception:
                        llama_manager = None

                mcp_host = McpAdapterHost(
                    config, lambda: save_config(config), parent=self
                )

                def _start_mcp(mcp_cfg: Dict[str, Any]) -> None:
                    mcp_host.start_adapter(
                        quiet=True,
                        transport=str(mcp_cfg.get("transport") or "streamable-http"),
                        http_host=str(mcp_cfg.get("http_host") or "127.0.0.1"),
                        http_port=int(mcp_cfg.get("http_port") or 8765),
                    )

                def _on_theme(name: str) -> None:
                    change = getattr(win, "change_theme", None)
                    if callable(change):
                        change(name)

                apply_profile_payload(
                    payload,
                    config,
                    save_config=lambda: save_config(config),
                    parent=self,
                    llama_manager=llama_manager,
                    start_mcp=_start_mcp,
                    on_theme=_on_theme,
                )
                remember_profile_name(str(row.get("name") or ""))
                done_name = str(row.get("name") or profile_id)
        finally:
            self.load_btn.setEnabled(True)

        if error_text:
            QMessageBox.warning(self, error_title or "Load profile", error_text)
            return
        if done_name:
            QMessageBox.information(
                self,
                "Load profile",
                f'Loaded "{done_name}".\n'
                "Settings were written to Spock_Console; "
                "llama / RAG / MCP / WebUI were started only when needed "
                "(existing listeners were reused).",
            )

    def _delete_selected(self) -> None:
        ids = []
        for item in self.list.selectedItems():
            rec = item.data(Qt.ItemDataRole.UserRole) or {}
            try:
                ids.append(int(rec.get("id")))
            except (TypeError, ValueError):
                pass
        if not ids:
            QMessageBox.information(self, "Profiles", "Select one or more profiles.")
            return
        reply = QMessageBox.question(
            self,
            "Delete profiles",
            f"Delete {len(ids)} profile(s)? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            n = delete_profiles(self.db_path, ids)
        except Exception as e:
            QMessageBox.critical(self, "Profiles", f"Delete failed:\n{e}")
            return
        QMessageBox.information(self, "Profiles", f"Deleted {n} profile(s).")
        self.refresh()


def open_manage_profiles_dialog(parent: Optional[QWidget] = None) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("Manage profiles")
    dlg.setMinimumSize(640, 480)
    dlg.setModal(True)
    lay = QVBoxLayout(dlg)
    lay.addWidget(ProfileReviewPanel(SHIP_COMPUTER_DB, dlg))
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dlg.accept)
    row = QHBoxLayout()
    row.addStretch()
    row.addWidget(close_btn)
    lay.addLayout(row)
    dlg.exec()


# ── payload ──────────────────────────────────────────────────────────────
def _servers_from_ready_json(root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fallback embed/chat GGUF snapshot from spock_ready_last.json (Bringup status)."""
    try:
        from spock_shell.paths import ROOT as SPOCK_ROOT

        base = Path(root) if root else Path(SPOCK_ROOT)
    except Exception:
        base = Path(root) if root else Path.cwd()
    path = base / "spock_ready_last.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    servers: List[Dict[str, Any]] = []
    for role, key in (("embedding", "embed"), ("chat", "chat")):
        block = data.get(key) if isinstance(data.get(key), dict) else {}
        model_path = str(block.get("model_path") or "").strip()
        if not model_path.lower().endswith(".gguf"):
            continue
        try:
            port = int(block.get("port") or (8080 if role == "embedding" else 8081))
        except (TypeError, ValueError):
            port = 8080 if role == "embedding" else 8081
        try:
            n_ctx = int(block.get("n_ctx") or 8192)
        except (TypeError, ValueError):
            n_ctx = 8192
        servers.append(
            {
                "role": role,
                "port": port,
                "model_path": model_path,
                "ngl": "-1",
                "n_ctx": n_ctx,
                "gpu_name": "",
                "llama_batch": 512,
                "llama_ubatch": 512,
                "owned": False,
                "running": bool(block.get("reachable")),
            }
        )
    return servers


def _live_servers(llama_manager: Any) -> List[Dict[str, Any]]:
    """Snapshot running embed/chat llama-servers worth restoring."""
    servers: List[Dict[str, Any]] = []
    if llama_manager is not None:
        try:
            instances = llama_manager.list_instances(refresh_discovered=True)
        except Exception:
            instances = []
        for inst in instances:
            if not getattr(inst, "is_alive", False):
                continue
            model_path = (getattr(inst, "model_path", "") or "").strip()
            # Only real embed/chat GGUFs — not --ui-mcp-proxy / empty discoveries.
            if not model_path.lower().endswith(".gguf"):
                continue
            role = (getattr(inst, "role", "") or "unknown").strip().lower()
            if role not in ("embedding", "chat"):
                continue
            servers.append(
                {
                    "role": role,
                    "port": int(getattr(inst, "port", 0) or 0),
                    "model_path": model_path,
                    "ngl": str(
                        inst.ngl if getattr(inst, "ngl", None) is not None else "-1"
                    ),
                    "n_ctx": int(getattr(inst, "n_ctx", 0) or 8192),
                    "gpu_name": getattr(inst, "gpu_label", "") or "",
                    "llama_batch": int(getattr(inst, "llama_batch", 0) or 512),
                    "llama_ubatch": int(getattr(inst, "llama_ubatch", 0) or 512),
                    "split_mode": str(getattr(inst, "split_mode", "") or ""),
                    "tensor_split": str(getattr(inst, "tensor_split", "") or ""),
                    "n_parallel": getattr(inst, "n_parallel", None),
                    "owned": bool(getattr(inst, "owned", False)),
                    "running": True,
                }
            )
    if servers:
        return servers
    return _servers_from_ready_json()


def _apply_server_paths_to_config(
    config: Dict[str, Any], servers: List[Dict[str, Any]]
) -> None:
    """Keep embedding_profile + chat_model_path aligned with live/ready GGUFs."""
    embed_path = ""
    chat_path = ""
    for srv in servers:
        role = str(srv.get("role") or "").lower()
        path = str(srv.get("model_path") or "").strip()
        if not path:
            continue
        if role == "embedding":
            embed_path = path
        elif role == "chat":
            chat_path = path
    if embed_path:
        ep = config.get("embedding_profile")
        if not isinstance(ep, dict):
            ep = {}
            config["embedding_profile"] = ep
        ep["model_path"] = embed_path
        ep.setdefault("model_id", Path(embed_path).name)
    if chat_path:
        config["chat_model_path"] = chat_path
        config["chat_model_name"] = Path(chat_path).name


def _launch_ui(launch_panel: Any) -> Dict[str, Any]:
    if launch_panel is None:
        return {}
    try:
        out = {
            "ngl": launch_panel.ngl_edit.text().strip(),
            "n_ctx": int(launch_panel.n_ctx_spin.value()),
            "gpu_name": launch_panel.gpu_combo.currentText(),
            "port": launch_panel.port_edit.text().strip(),
        }
        if hasattr(launch_panel, "gpu_policy_combo"):
            out["gpu_policy"] = launch_panel.gpu_policy_combo.currentData()
            out["tensor_split"] = launch_panel.tensor_split_edit.text().strip()
            out["split_mode"] = launch_panel.split_mode_combo.currentText()
            out["embed_np"] = int(launch_panel.embed_np_spin.value())
        return out
    except Exception:
        return {}


def _lm_studio_block(config: Dict[str, Any]) -> Dict[str, Any]:
    """Probe LM Studio only when Ask AI actually uses it."""
    host = str(config.get("lm_studio_host") or "localhost")
    try:
        port = int(config.get("lm_studio_port") or 1234)
    except (TypeError, ValueError):
        port = 1234
    key = str(config.get("lm_studio_key") or "")
    preferred_model = str(config.get("lm_studio_model") or "").strip()

    if str(config.get("ask_ai_provider") or "") != "LM Studio":
        snap = {
            "reachable": False,
            "detail": "skipped (Ask AI provider is not LM Studio)",
            "loaded": [],
        }
    else:
        try:
            from lm_studio_api import snapshot as lm_snapshot

            snap = lm_snapshot(host, port, key)
        except Exception as e:
            snap = {"reachable": False, "detail": str(e), "loaded": []}
        if not preferred_model:
            for entry in snap.get("loaded") or []:
                if str(entry.get("type") or "llm") == "embedding":
                    continue
                preferred_model = str(
                    entry.get("key") or entry.get("instance_id") or ""
                )
                if preferred_model:
                    break
    return {
        "reachable": bool(snap.get("reachable")),
        "detail": snap.get("detail"),
        "host": host,
        "port": port,
        "loaded": snap.get("loaded") or [],
        "preferred_model": preferred_model,
    }


def build_profile_payload(
    config: Dict[str, Any],
    *,
    llama_manager: Any = None,
    launch_panel: Any = None,
    rag_running: bool = False,
    mcp_running: bool = False,
    webui_running: bool = False,
) -> Dict[str, Any]:
    """Snapshot config plus whatever live state the calling app can see."""
    try:
        config_copy = json.loads(json.dumps(config))
    except (TypeError, ValueError):
        config_copy = dict(config)
    if not rag_running:
        try:
            from spock_shell.rag_host import is_rag_up, rag_bind

            host, port = rag_bind(config)
            rag_running = is_rag_up(host, port)
        except Exception:
            rag_running = False
    servers = _live_servers(llama_manager)
    _apply_server_paths_to_config(config_copy, servers)
    return {
        "config": config_copy,
        "servers": servers,
        "launch_ui": _launch_ui(launch_panel),
        "rag_was_running": bool(rag_running),
        "mcp_was_running": bool(mcp_running),
        "webui_was_running": bool(webui_running),
        "lm_studio": _lm_studio_block(config),
    }


def harvest_live_config(
    config: Dict[str, Any],
    *,
    configure_panel: Any = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Refresh `config` from ship_computer.db, then overlay live Configure widgets.

    The hub process does not own the Configure form. Without this, a Save-on-exit
    snapshot would freeze whatever the hub loaded at startup and write a newer
    profile that wipes OpenAI-compatible settings another station just saved.
    """
    try:
        from spock_shell.config import load_config

        config.update(load_config())
    except Exception:
        pass
    if configure_panel is not None:
        collect = getattr(configure_panel, "collect_all", None)
        if callable(collect):
            try:
                config.update(collect())
            except Exception:
                pass
    if persist:
        try:
            from spock_shell.config import save_config

            save_config(config)
        except Exception:
            pass
    return config


# ── restore ──────────────────────────────────────────────────────────────
def _restore_launch_ui(launch_panel: Any, launch_ui: Dict[str, Any]) -> None:
    if launch_panel is None or not launch_ui:
        return
    if launch_ui.get("ngl"):
        launch_panel.ngl_edit.setText(str(launch_ui["ngl"]))
    if launch_ui.get("n_ctx"):
        try:
            launch_panel.n_ctx_spin.setValue(int(launch_ui["n_ctx"]))
        except (TypeError, ValueError):
            pass
    if launch_ui.get("port"):
        launch_panel.port_edit.setText(str(launch_ui["port"]))
    gpu_name = str(launch_ui.get("gpu_name") or "").strip()
    if gpu_name:
        combo = launch_panel.gpu_combo
        index = combo.findText(gpu_name)
        if index >= 0:
            combo.setCurrentIndex(index)
    if hasattr(launch_panel, "gpu_policy_combo") and launch_ui.get("gpu_policy"):
        idx = launch_panel.gpu_policy_combo.findData(launch_ui.get("gpu_policy"))
        if idx >= 0:
            launch_panel.gpu_policy_combo.setCurrentIndex(idx)
    if hasattr(launch_panel, "tensor_split_edit") and launch_ui.get("tensor_split"):
        launch_panel.tensor_split_edit.setText(str(launch_ui["tensor_split"]))
    if hasattr(launch_panel, "split_mode_combo") and launch_ui.get("split_mode"):
        sm_i = launch_panel.split_mode_combo.findText(str(launch_ui["split_mode"]))
        if sm_i >= 0:
            launch_panel.split_mode_combo.setCurrentIndex(sm_i)
    if hasattr(launch_panel, "embed_np_spin") and launch_ui.get("embed_np") is not None:
        try:
            launch_panel.embed_np_spin.setValue(int(launch_ui["embed_np"]))
        except (TypeError, ValueError):
            pass


def _restore_servers(
    llama_manager: Any,
    servers: List[Dict[str, Any]],
    mcp_cfg: Dict[str, Any],
    gpu_list: List[str],
) -> Tuple[List[str], int]:
    """Relaunch at most one embedding and one chat server. Returns (missing, skipped)."""
    missing: List[str] = []
    skipped = 0
    if llama_manager is None:
        return missing, skipped
    try:
        webui_port = int(mcp_cfg.get("webui_port") or 8082)
    except (TypeError, ValueError):
        webui_port = 8082

    restored_roles = set()
    for srv in servers or []:
        if not isinstance(srv, dict) or not srv.get("running", True):
            continue
        model_path = str(srv.get("model_path") or "").strip()
        try:
            port = int(srv.get("port") or 0)
        except (TypeError, ValueError):
            continue
        role_hint = str(srv.get("role") or "").strip().lower()
        # Skip WebUI proxy / non-GGUF placeholders (restored via webui_autostart).
        if (
            role_hint in ("webui", "ui-mcp-proxy", "proxy")
            or port == webui_port
            or not model_path.lower().endswith(".gguf")
        ):
            continue
        if not os.path.isfile(model_path):
            missing.append(model_path)
            continue
        if port < 1 or port > 65535 or llama_manager.port_in_use(port):
            continue
        role = role_hint if role_hint not in ("", "unknown") else None
        if not role:
            from model_selector_core import is_embedding_gguf_path

            role = "embedding" if is_embedding_gguf_path(model_path) else "chat"
        if role in restored_roles:
            skipped += 1
            continue
        split_mode = str(srv.get("split_mode") or "").strip()
        tensor_split = str(srv.get("tensor_split") or "").strip()
        n_parallel = srv.get("n_parallel")
        ngl = str(srv.get("ngl") or "-1").strip() or "-1"
        ngl_source = ""
        pin_cuda = None
        cuda_device = ""
        ov: Dict[str, Any] = {}
        # Prefer per-server saved split; else current host recipe.
        if not tensor_split or n_parallel is None or not split_mode or ngl == "-1":
            try:
                from WarpCore.host_recipe import (
                    effective_recipe,
                    launch_plan_for_role,
                )
                from spock_shell.paths import SHIP_COMPUTER_DB

                # Live-probe based: a recipe saved on another machine names GPU
                # indexes and splits this host may not have. Pinned app.launch.*
                # flags ride along, so a saved -ngl applies to restores too.
                plan = effective_recipe(SHIP_COMPUTER_DB, created_by="bridge")
                ov = launch_plan_for_role(
                    SHIP_COMPUTER_DB, plan.get("recipe"), role or "chat"
                )
                if not tensor_split:
                    tensor_split = str(ov.get("tensor_split") or "")
                if not split_mode:
                    split_mode = str(ov.get("split_mode") or "")
                if n_parallel is None:
                    n_parallel = ov.get("n_parallel")
                if ngl == "-1" and str(ov.get("ngl") or "-1") != "-1":
                    ngl = str(ov["ngl"])
                    ngl_source = str(ov.get("ngl_source") or "")
                pin_cuda = ov.get("pin_cuda")
                cuda_device = str(ov.get("cuda_device") or "")
            except Exception:
                pass
        if "flash_attn" not in ov:
            try:
                from WarpCore.host_recipe import (
                    effective_recipe,
                    launch_plan_for_role,
                )
                from spock_shell.paths import SHIP_COMPUTER_DB

                plan = effective_recipe(SHIP_COMPUTER_DB, created_by="bridge")
                ov = launch_plan_for_role(
                    SHIP_COMPUTER_DB, plan.get("recipe"), role or "chat"
                )
            except Exception:
                pass
        ok = llama_manager.launch(
            model_path=model_path,
            port=port,
            ngl=ngl,
            gpu_list=gpu_list,
            gpu_name=str(srv.get("gpu_name") or ""),
            llama_batch=int(srv.get("llama_batch") or 512),
            llama_ubatch=int(srv.get("llama_ubatch") or 512),
            role=role,
            n_ctx=int(srv.get("n_ctx") or 8192),
            split_mode=split_mode,
            tensor_split=tensor_split,
            n_parallel=n_parallel,
            pin_cuda=pin_cuda,
            cuda_device=cuda_device,
            ngl_source=ngl_source,
            flash_attn=ov.get("flash_attn"),
            cache_type_k=ov.get("cache_type_k"),
            cache_type_v=ov.get("cache_type_v"),
            n_cpu_moe=int(ov.get("n_cpu_moe") or 0),
            reasoning=str(ov.get("reasoning") or ""),
        )
        if ok:
            restored_roles.add(role)
    return missing, skipped


def apply_profile_payload(
    payload: Dict[str, Any],
    config: Dict[str, Any],
    *,
    save_config: Callable[[], None],
    parent: Optional[QWidget] = None,
    llama_manager: Any = None,
    launch_panel: Any = None,
    mcp_panel: Any = None,
    webui_panel: Any = None,
    gpu_list: Optional[List[str]] = None,
    start_rag: Optional[Callable[[], None]] = None,
    start_mcp: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_theme: Optional[Callable[[str], None]] = None,
) -> None:
    """Restore settings from a profile, then start what the app can start."""
    if not isinstance(payload, dict):
        return

    from spock_shell.busy_ui import heartbeat, pause_busy_for_dialog

    heartbeat("Applying profile settings…")
    for key, value in (payload.get("config") or {}).items():
        config[key] = value

    config["embedding_profile"] = merge_embedding_profile(
        config.get("embedding_profile")
    )
    rag = config.get("rag_api") or {}
    config["rag_api"] = {
        "enabled": bool(rag.get("enabled", False)),
        "host": rag.get("host", "127.0.0.1"),
        "port": int(rag.get("port", 8090)),
        "api_key": rag.get("api_key", ""),
    }
    config["uieg"] = merge_uieg_config(config.get("uieg"))
    mcp_cfg = merge_mcp_settings(config.get("mcp"))
    config["mcp"] = mcp_cfg
    try:
        save_config()
    except Exception:
        pass
    heartbeat("Wrote Spock_Console settings…")

    ep = config["embedding_profile"]
    set_embeddings_url(ep.get("embeddings_url") or "http://localhost:8080/embeddings")
    write_embedding_env(ep)

    for panel in (mcp_panel, webui_panel):
        if panel is None:
            continue
        try:
            panel.apply_settings(mcp_cfg)
        except Exception:
            pass

    if on_theme is not None and config.get("theme"):
        try:
            on_theme(str(config["theme"]))
        except Exception:
            pass

    try:
        from spock_shell.bridge_host import apply_provider_config

        apply_provider_config(config)
    except Exception:
        pass

    if launch_panel is not None:
        try:
            launch_panel.set_embedding_profile(ep)
        except Exception:
            pass
        _restore_launch_ui(launch_panel, payload.get("launch_ui") or {})

    heartbeat("Starting llama-server instances…")
    missing, skipped = _restore_servers(
        llama_manager, payload.get("servers") or [], mcp_cfg, list(gpu_list or [])
    )
    if skipped:
        with pause_busy_for_dialog():
            QMessageBox.information(
                parent,
                "Load profile",
                f"Skipped {skipped} extra llama-server(s) from the profile.\n"
                "Spock keeps at most one embedding and one chat instance.",
            )
    if missing:
        shown = "\n".join(missing[:8])
        extra = "" if len(missing) <= 8 else f"\n…and {len(missing) - 8} more"
        with pause_busy_for_dialog():
            QMessageBox.warning(
                parent,
                "Load profile",
                f"Some llama-server models were missing and were skipped:\n{shown}{extra}",
            )

    try:
        from spock_shell.embedding_corpus import live_vs_corpus, profile_embedding_path

        heartbeat("Checking embedding model…")
        report = live_vs_corpus(
            str(ep.get("embeddings_url") or ""),
            profile_model_path=profile_embedding_path(payload)
            or str(ep.get("model_path") or ""),
            profile_model_id=str(ep.get("model_id") or ""),
        )
        # Warn on hard live≠KB mismatch; profile-only staleness is non-blocking.
        if report.get("mismatch") and report.get("message") and parent is not None:
            with pause_busy_for_dialog():
                QMessageBox.warning(
                    parent, "Embedding model", report["message"]
                )
    except Exception:
        pass

    want_rag = bool(payload.get("rag_was_running")) or bool(
        (config.get("rag_api") or {}).get("enabled")
    )
    if want_rag:
        heartbeat("Starting RAG API…")
        started_ok = True
        detail = ""
        try:
            if start_rag is not None:
                start_rag()
            else:
                from spock_shell.rag_host import spawn_rag_api

                started_ok, detail = spawn_rag_api(config)
        except Exception as e:
            started_ok, detail = False, str(e)
        if not started_ok:
            with pause_busy_for_dialog():
                QMessageBox.warning(
                    parent, "Load profile", f"Could not start RAG API:\n{detail}"
                )
        else:
            config.setdefault("rag_api", {})["enabled"] = True
            try:
                save_config()
            except Exception:
                pass

    want_mcp = bool(payload.get("mcp_was_running")) or bool(
        mcp_cfg.get("adapter_autostart") or mcp_cfg.get("webui_autostart")
    )
    if want_mcp and start_mcp is not None:
        heartbeat("Starting MCP adapter…")
        try:
            start_mcp(mcp_cfg)
        except Exception as e:
            with pause_busy_for_dialog():
                QMessageBox.warning(
                    parent, "Load profile", f"Could not start MCP adapter:\n{e}"
                )

    want_webui = bool(payload.get("webui_was_running")) or bool(
        mcp_cfg.get("webui_autostart")
    )
    if want_webui:
        heartbeat("Starting WebUI proxy…")
        try:
            if webui_panel is not None:
                ok, detail = webui_panel.start_ui_mcp_proxy(quiet=True)
            else:
                from mcp_panel import spawn_ui_mcp_proxy

                ok, detail, _proc = spawn_ui_mcp_proxy(mcp_cfg)
            if not ok:
                with pause_busy_for_dialog():
                    QMessageBox.warning(
                        parent,
                        "Load profile",
                        f"Could not start llama.cpp WebUI:\n{detail}",
                    )
        except Exception as e:
            with pause_busy_for_dialog():
                QMessageBox.warning(
                    parent, "Load profile", f"Could not start llama.cpp WebUI:\n{e}"
                )
    heartbeat("Finishing…")


# ── orchestration ────────────────────────────────────────────────────────
def save_profile_interactive(
    parent: Optional[QWidget],
    payload: Dict[str, Any],
    *,
    prompt: str = "",
) -> Optional[int]:
    """Ask for a name and store the payload. Returns the new profile id."""
    warn_embedding_vs_wiki_scan(parent, payload)
    sd = profile_stardate()
    dlg = SaveProfileDialog(
        parent, default_name=sd, allow_cancel=False, prompt=prompt
    )
    dlg.exec()
    if dlg.choice != SaveProfileDialog.RESULT_SAVE:
        return None
    name = dlg.profile_name()
    if not confirm_replace_profile(parent, name):
        return None
    from spock_shell.busy_ui import busy_scope

    try:
        with busy_scope(parent, "Saving configuration profile…"):
            pid, _replaced = upsert_profile(
                SHIP_COMPUTER_DB, name, payload, profile_stardate=sd
            )
            remember_profile_name(name)
        QMessageBox.information(
            parent,
            "Save profile",
            f'Saved profile "{name}".',
        )
        return pid
    except Exception as e:
        QMessageBox.critical(parent, "Save profile", f"Could not save profile:\n{e}")
        return None


def prompt_save_profile(
    parent: Optional[QWidget],
    payload: Dict[str, Any],
) -> bool:
    """Exit-time prompt. Returns False when the user cancels the close."""
    if not prompts_enabled():
        return True
    warn_embedding_vs_wiki_scan(parent, payload)
    sd = profile_stardate()
    dlg = SaveProfileDialog(parent, default_name=sd)
    dlg.exec()
    if dlg.choice == SaveProfileDialog.RESULT_CANCEL:
        return False
    if dlg.choice == SaveProfileDialog.RESULT_SAVE:
        name = dlg.profile_name()
        if not confirm_replace_profile(parent, name):
            return True
        from spock_shell.busy_ui import busy_scope

        try:
            with busy_scope(parent, "Saving configuration profile…"):
                upsert_profile(
                    SHIP_COMPUTER_DB, name, payload, profile_stardate=sd
                )
                remember_profile_name(name)
        except Exception as e:
            reply = QMessageBox.question(
                parent,
                "Save profile",
                f"Could not save profile:\n{e}\n\nExit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes
    return True


def pick_profile_payload(parent: Optional[QWidget]) -> Optional[Dict[str, Any]]:
    """Manual Load: pick a profile and return its payload (no restore)."""
    try:
        if count_profiles(SHIP_COMPUTER_DB) <= 0:
            QMessageBox.information(
                parent,
                "Load profile",
                "No saved profiles in ship_computer.db yet.",
            )
            return None
        profiles = list_profiles(SHIP_COMPUTER_DB)
    except Exception as e:
        QMessageBox.critical(parent, "Load profile", f"Could not list profiles:\n{e}")
        return None
    dlg = LoadProfileDialog(parent, profiles=profiles)
    if dlg.exec() != QDialog.DialogCode.Accepted or dlg.selected_id is None:
        return None
    try:
        row = get_profile(SHIP_COMPUTER_DB, dlg.selected_id)
    except Exception as e:
        QMessageBox.critical(parent, "Load profile", f"Could not read profile:\n{e}")
        return None
    if not row:
        QMessageBox.warning(parent, "Load profile", "Profile not found.")
        return None
    return row.get("payload") or {}


def warn_embedding_vs_wiki_scan(
    parent: Optional[QWidget], payload: Dict[str, Any]
) -> None:
    """Warn if saved/live embed GGUF differs from last wiki_agent scan corpus."""
    if parent is None or not prompts_enabled():
        return
    try:
        from spock_shell.embedding_corpus import (
            live_vs_corpus,
            profile_embedding_path,
        )

        cfg = (payload or {}).get("config") or {}
        ep = cfg.get("embedding_profile") or {}
        report = live_vs_corpus(
            str(ep.get("embeddings_url") or ""),
            profile_model_path=profile_embedding_path(payload)
            or str(ep.get("model_path") or ""),
            profile_model_id=str(ep.get("model_id") or ""),
        )
        if not report.get("message"):
            return
        if report.get("mismatch") or report.get("profile_mismatch"):
            QMessageBox.warning(
                parent,
                "Embedding model vs Wiki Scan",
                report["message"],
            )
    except Exception:
        pass


def maybe_load_profile(parent: Optional[QWidget]) -> Optional[Dict[str, Any]]:
    """Ask whether to restore a saved profile. Returns the chosen payload."""
    if not prompts_enabled() or profile_load_answered():
        return None
    try:
        if count_profiles(SHIP_COMPUTER_DB) <= 0:
            return None
        profiles = list_profiles(SHIP_COMPUTER_DB)
    except Exception:
        return None
    mark_profile_load_answered()
    reply = QMessageBox.question(
        parent,
        "Load configuration",
        "Load from a previous configuration profile?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return None
    dlg = LoadProfileDialog(parent, profiles=profiles)
    if dlg.exec() != QDialog.DialogCode.Accepted or dlg.selected_id is None:
        return None
    try:
        row = get_profile(SHIP_COMPUTER_DB, dlg.selected_id)
    except Exception as e:
        QMessageBox.critical(parent, "Load profile", f"Could not read profile:\n{e}")
        return None
    if not row:
        QMessageBox.warning(parent, "Load profile", "Profile not found.")
        return None
    return row.get("payload") or {}
