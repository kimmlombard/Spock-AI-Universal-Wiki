"""Spock-Engineering-Deck — PyQt Ask AI + Deep Dive."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from PyQt6.QtCore import QTimer

from model_selector_core import merge_embedding_profile
from EngineeringDeck.ask_panel import AskAiPanel
from spock_shell.bridge_host import make_llm_client
from spock_shell.config import save_config
from spock_shell.markdown_home import build_markdown_home, reload_markdown_home
from spock_shell.mcp_host import McpAdapterHost
from spock_shell.paths import SHIP_COMPUTER_DB, ensure_root_on_path
from spock_shell.profiles import (
    apply_profile_payload,
    build_profile_payload,
    harvest_live_config,
    maybe_load_profile,
    prompt_save_profile,
    save_profile_interactive,
)
from spock_shell.theme import THEMES
from spock_shell.window import NavItem, SuiteShellWindow

# Same curated overview as Engineering Maintenance (Ask AI / Deep Dive lives here;
# maintenance tabs are in Spock-Engineering-Maintenance).
HELPER_MD = "AIHelperDocuments/Spock-Engineering-Maintenance-HELPER.md"


class EngineeringDeckWindow(SuiteShellWindow):
    app_title = "Spock-Engineering-Deck"
    app_subtitle = "In-app Ask AI and Deep Dive over ship_computer.db (local PyQt)."

    def __init__(self, parent=None):
        ensure_root_on_path()
        self._ask = None
        self._configure = None
        super().__init__(parent)
        self._mcp_host = McpAdapterHost(
            self.config, lambda: save_config(self.config), parent=self
        )
        # Prompt once the window is on screen, not mid-construction.
        QTimer.singleShot(0, self._offer_profile_load)

    def on_ready(self) -> None:
        self.show_home()

    def build_home_widget(self):
        return build_markdown_home(
            self.theme,
            HELPER_MD,
            fallback_title=self.app_title,
            fallback_subtitle=self.app_subtitle,
        )

    def show_home(self) -> None:
        reload_markdown_home(self._home, self.theme)
        super().show_home()

    def _ensure_ask(self):
        if self._ask is not None:
            return self._ask
        from WarpCore.search import hybrid_search

        emb = lambda: merge_embedding_profile(self.config.get("embedding_profile")).get(
            "embeddings_url", "http://localhost:8080/embeddings"
        )
        self._ask = AskAiPanel(
            self.theme,
            get_llm=lambda: make_llm_client(self.config),
            hybrid_search_fn=hybrid_search,
            get_emb_url=emb,
            get_config=lambda: self.config,
        )
        self.stack.addWidget(self._ask)
        return self._ask

    def _ensure_configure(self):
        if self._configure is not None:
            return self._configure
        from spock_shell.configure_ai import ConfigureAiPanel

        self._configure = ConfigureAiPanel(
            self.theme,
            self.config,
            lambda: save_config(self.config),
            db_path=SHIP_COMPUTER_DB,
            mcp_host=self._mcp_host,
        )
        self._configure.save_profile_requested.connect(self._save_profile)
        self.stack.addWidget(self._configure)
        return self._configure

    # --- profiles ---
    def _profile_payload(self) -> Dict[str, Any]:
        try:
            mcp_running = bool(self._mcp_host.running_pids())
        except Exception:
            mcp_running = False
        webui = getattr(self._configure, "webui_panel", None)
        try:
            webui_running = bool(webui is not None and webui.is_webui_running())
        except Exception:
            webui_running = False
        harvest_live_config(
            self.config,
            configure_panel=self._configure,
        )
        return build_profile_payload(
            self.config,
            llama_manager=getattr(self, "server_manager", None),
            mcp_running=mcp_running,
            webui_running=webui_running,
        )

    def _save_profile(self) -> None:
        save_profile_interactive(
            self,
            self._profile_payload(),
            prompt=(
                "Save these AI settings as a named profile?\n"
                "(Ask AI provider, RAG, MCP, Embedding Profile)"
            ),
        )

    def _offer_profile_load(self) -> None:
        payload = maybe_load_profile(self)
        if not payload:
            QTimer.singleShot(1500, self._maybe_autostart_from_config)
            QTimer.singleShot(5000, self._verify_mcp_autostart)
            return
        self._pending_profile_payload = payload
        QTimer.singleShot(0, self._apply_pending_profile_payload)

    def _apply_pending_profile_payload(self) -> None:
        payload = getattr(self, "_pending_profile_payload", None)
        self._pending_profile_payload = None
        if not payload:
            return
        from spock_shell.busy_ui import busy_scope, clear_override_cursors

        with busy_scope(self, "Loading configuration profile…"):
            apply_profile_payload(
                payload,
                self.config,
                save_config=lambda: save_config(self.config),
                parent=self,
                llama_manager=getattr(self, "server_manager", None),
                mcp_panel=getattr(self._configure, "mcp_panel", None),
                webui_panel=getattr(self._configure, "webui_panel", None),
                start_mcp=lambda mcp_cfg: self._mcp_host.start_adapter(
                    quiet=True,
                    transport=str(mcp_cfg.get("transport") or "streamable-http"),
                    http_host=str(mcp_cfg.get("http_host") or "127.0.0.1"),
                    http_port=int(mcp_cfg.get("http_port") or 8765),
                ),
                on_theme=self._apply_profile_theme,
            )
            if self._configure is not None:
                self.stack.removeWidget(self._configure)
                self._configure.deleteLater()
                self._configure = None
        clear_override_cursors()
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.information(
            self,
            "Load profile",
            "Profile loaded. Settings restored; services were started only when needed.",
        )
        QTimer.singleShot(2000, self._maybe_autostart_from_config)
        QTimer.singleShot(5000, self._verify_mcp_autostart)

    def _maybe_autostart_from_config(self) -> None:
        from spock_shell.profiles import prompts_enabled

        if not prompts_enabled():
            return
        mcp = self.config.get("mcp") or {}
        need_adapter = bool(
            mcp.get("adapter_autostart") or mcp.get("webui_autostart")
        )
        if need_adapter:
            try:
                self._mcp_host.ensure_http_adapter_async()
            except Exception as e:
                print(f"[profile] MCP adapter autostart failed: {e}")

    def _verify_mcp_autostart(self) -> None:
        mcp = self.config.get("mcp") or {}
        need_adapter = bool(
            mcp.get("adapter_autostart") or mcp.get("webui_autostart")
        )
        if not need_adapter:
            return
        from spock_shell.proc_guard import tcp_open

        port = int(mcp.get("http_port") or 8765)
        host = str(mcp.get("http_host") or "127.0.0.1")
        if tcp_open(host, port):
            return
        try:
            self._mcp_host.ensure_http_adapter_async()
        except Exception as e:
            print(f"[profile] MCP autostart verify failed: {e}")

    def _apply_profile_theme(self, theme_name: str) -> None:
        if theme_name not in THEMES or theme_name == self.current_theme:
            return
        if getattr(self, "theme_combo", None) is not None:
            self.theme_combo.setCurrentText(theme_name)
        else:
            self.change_theme(theme_name)

    def closeEvent(self, event):
        if not prompt_save_profile(self, self._profile_payload()):
            event.ignore()
            return
        mcp = getattr(self, "_mcp_host", None)
        kill_mcp = getattr(mcp, "kill_processes", None)
        if callable(kill_mcp):
            try:
                kill_mcp()
            except Exception:
                pass
        super().closeEvent(event)

    def nav_steps(self) -> Sequence[NavItem]:
        return [
            ("Home", self.show_home),
            ("1 Ask AI", lambda: self.show_center(self._ensure_ask())),
            ("2 Configure Spock AI", lambda: self.show_center(self._ensure_configure())),
            ("-----", None),
            ("AI Helper", self.open_ai_helper),
            ("Ship Status", self.open_status),
            ("About", self.open_about),
            ("Exit", self.close),
        ]
