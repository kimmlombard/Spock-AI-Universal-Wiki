"""Spock-Navigation-Station main window."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from llama_server_manager import LlamaServerManager
from model_selector_core import merge_embedding_profile, write_embedding_env
from model_selector_panels import ModelInfoPanel, ModelSelectorState, ModelsPanel
from NavigationStation.steps.configure import build_configure_step
from NavigationStation.steps.hardware import build_hardware_step
from NavigationStation.steps.launch import build_launch_step
from NavigationStation.steps.status import build_status_step
from rag_api_server import RagApiServer
from ScienceStation.ships_logs import build_ships_logs_panel
from spock_wiki_adapter.wiki_run import build_wiki_agent_run_panel
from spock_shell.brave_search import build_brave_search_panel
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
from spock_shell.widgets import SidePanel
from spock_shell.window import NavItem, SuiteShellWindow

try:
    from WarpCore.search import set_embeddings_url
except Exception:  # pragma: no cover
    def set_embeddings_url(url: str) -> None:
        pass


HELPER_MD = "AIHelperDocuments/Spock-Navigation-Station-HELPER.md"


class NavigationStationWindow(SuiteShellWindow):
    app_title = "Spock-Navigation-Station"
    app_subtitle = (
        "Hardware → HF Models → Launch → Configure Spock AI → "
        "Spock Status → Wiki Scan → Ship's Logs → Ask AI."
    )

    def __init__(self, parent=None):
        ensure_root_on_path()
        self.state = ModelSelectorState()
        self.server_manager = LlamaServerManager()
        self.rag_api_server: Optional[RagApiServer] = None
        self._llm = None
        self._steps: Dict[str, Any] = {}
        self._hw_scanned_once = False
        self._logs = None
        self._ask = None
        # Built in _build_steps: self.config only exists after the shell __init__.
        self.mcp_host: Optional[McpAdapterHost] = None
        super().__init__(parent)
        # Prompt once the window is on screen, not mid-construction.
        QTimer.singleShot(0, self._offer_profile_load)

    def on_ready(self) -> None:
        self._build_steps()
        # Home HELPER doc is already current; ensure stack stays on it at start.
        self.show_home()
        # One hardware probe per session. Panels read state.hardware_specs; only
        # SCAN HARDWARE re-probes.
        QTimer.singleShot(0, self._probe_hardware_once)

    def build_home_widget(self) -> QWidget:
        return build_markdown_home(
            self.theme,
            HELPER_MD,
            fallback_title=self.app_title,
            fallback_subtitle=self.app_subtitle,
        )

    def show_home(self) -> None:
        reload_markdown_home(self._home, self.theme)
        super().show_home()

    def nav_steps(self) -> Sequence[NavItem]:
        # AI Helper / Ship Status / About / Google Search live on the right Tools dock.
        return [
            ("Home", self.show_home),
            ("1 Hardware", self._show_hardware),
            ("2 HF Models", self._show_models),
            ("3 Launch", self._show_launch),
            ("4 Configure Spock AI", self._show_configure),
            ("5 Spock Status", self._show_status),
            ("6 Run Wiki Scan", self._show_run),
            ("7 Ship's Logs", self._show_ships_logs),
            ("8 Run Ask AI", self._show_ask_ai),
            ("-----", None),
            ("Exit", self.close),
        ]

    def build_right_dock(self, layout: QVBoxLayout) -> None:
        search = SidePanel("Search", self.theme)
        search.add_button("Google Search", self._show_brave_search)
        layout.addWidget(search)
        super().build_right_dock(layout)

    def _probe_hardware_once(self) -> None:
        """Launch probe: scan, then create the host recipe if none exists yet."""
        if self._hw_scanned_once:
            return
        self._hw_scanned_once = True
        panel = getattr(self._steps.get("hardware"), "_panel", None)
        if panel is not None:
            panel._start_scan()

    def _show_hardware(self) -> None:
        # Display only — the launch probe already filled state, and re-scanning
        # on every visit costs 3 nvidia-smi spawns plus an NVML pass.
        self.show_center(self._steps["hardware"])

    def _show_launch(self) -> None:
        w = self._steps["launch"]
        panel = getattr(w, "_panel", None)
        if panel is not None:
            panel._populate_gpus()
            panel._update_buttons()
        self.show_center(w)

    def _show_run(self) -> None:
        self.show_center(self._steps["run"])

    def _openai_compat_from_config(self) -> Dict[str, Any]:
        """Slice Ask AI OpenAI-compatible fields for the Gemini (Vertex) tab."""
        c = self.config
        return {
            "openai_compat_base_url": (c.get("openai_compat_base_url") or "").strip(),
            "openai_compat_api_key": c.get("openai_compat_api_key") or "",
            "openai_compat_model": (c.get("openai_compat_model") or "").strip(),
            "openai_compat_n_ctx": c.get("openai_compat_n_ctx"),
            "openai_compat_max_tokens": c.get("openai_compat_max_tokens"),
        }

    def _sync_models_openai_compat(self, _provider: str = "") -> None:
        models = self._steps.get("models")
        if models is not None:
            models.set_openai_compat(self._openai_compat_from_config())

    def _on_gemini_use_for_ask_ai(self, model_id: str) -> None:
        mid = (model_id or "").strip()
        if not mid:
            return
        self.config["openai_compat_model"] = mid
        self.config["ask_ai_provider"] = "OpenAI-compatible"
        save_config(self.config)
        configure = self._steps.get("configure")
        if configure is not None:
            tab = (getattr(configure, "connectors", None) or {}).get(
                "OpenAI-compatible"
            )
            model_edit = getattr(tab, "model", None)
            if model_edit is not None:
                model_edit.setText(mid)
            refresh = getattr(configure, "refresh_active_provider", None)
            if callable(refresh):
                refresh()

    def _show_models(self) -> None:
        # Query HF Hub needs hardware_specs, which the launch probe supplies.
        # Only a failed probe leaves this empty — say so instead of rescanning
        # on every visit; SCAN HARDWARE on 1 Hardware is the retry.
        self._enable_hf_query_buttons()
        models = self._steps.get("models")
        if models is not None:
            # Pick up Vertex / OpenAI-compatible settings saved on step 4.
            models.set_openai_compat(self._openai_compat_from_config())
            if not self.state.hardware_specs:
                models.download_status.setText(
                    "Hardware probe unavailable — run SCAN HARDWARE on 1 Hardware, "
                    "then return here to query the Hub."
                )
        self.show_center(self._steps["models"])

    def _show_model_info(self) -> None:
        self._show_model_info_for(self.state.selected_hf_model_id)

    def _show_model_info_for(self, model_id: str = "") -> None:
        mid = (model_id or self.state.selected_hf_model_id or "").strip()
        panel = self._steps["model_info"]
        if mid:
            panel.load_model(mid)
        else:
            panel._refresh_from_state()
        self.show_center(panel)

    def _show_ships_logs(self) -> None:
        if self._logs is None:
            self._logs = build_ships_logs_panel(self.theme, SHIP_COMPUTER_DB)
            self.stack.addWidget(self._logs)
        select = getattr(self._logs, "select_table", None)
        if callable(select):
            select("documents")
        self.show_center(self._logs)

    def _show_ask_ai(self) -> None:
        if self._ask is None:
            from EngineeringDeck.ask_panel import AskAiPanel
            from WarpCore.search import hybrid_search

            self._ask = AskAiPanel(
                self.theme,
                get_llm=lambda: make_llm_client(self.config),
                hybrid_search_fn=hybrid_search,
                get_emb_url=lambda: merge_embedding_profile(
                    self.config.get("embedding_profile")
                ).get("embeddings_url", "http://localhost:8080/embeddings"),
                get_config=lambda: self.config,
            )
            self.stack.addWidget(self._ask)
        self.show_center(self._ask)
        self._maybe_offer_ships_path_to_ask()

    def _maybe_offer_ships_path_to_ask(self) -> None:
        if self._logs is None or self._ask is None:
            return
        if not hasattr(self, "_offered_ask_path_filters"):
            self._offered_ask_path_filters = set()
        from spock_shell.ask_path_handoff import offer_copy_ships_path_to_ask

        offer_copy_ships_path_to_ask(
            self,
            logs=self._logs,
            ask=self._ask,
            db_path=SHIP_COMPUTER_DB,
            offered=self._offered_ask_path_filters,
        )

    def _after_llama_gui_launch(self, message: str) -> None:
        """Refresh the Configure Spock AI Active Provider line after a GUI launch."""
        configure = self._steps.get("configure")
        probe = getattr(configure, "probe_active_provider", None)
        if not callable(probe):
            return
        probe()
        label = getattr(configure, "active_lbl", None)
        if label is not None and message:
            label.setText(f"{message}<br>{label.text()}")

    def _show_configure(self) -> None:
        w = self._steps["configure"]
        self.show_center(w)
        mcp = getattr(w, "mcp_panel", None)
        if mcp is not None:
            QTimer.singleShot(0, mcp.refresh_status)
            cfg = self.config.get("mcp") or {}
            if self.mcp_host is not None:
                transport = str(cfg.get("transport") or "streamable-http").strip().lower()
                if transport in ("http", "streamable-http", "streamable_http", "sse"):
                    QTimer.singleShot(300, self.mcp_host.ensure_http_adapter_async)
        webui = getattr(w, "webui_panel", None)
        if webui is not None:
            QTimer.singleShot(0, webui.refresh_status)

    def _show_status(self) -> None:
        step = self._steps["status"]
        console = getattr(step, "_console", None)
        if console is not None:
            console.config = self.config
            console.refresh()
        self.show_center(step)

    def _show_brave_search(self) -> None:
        self.show_center(self._steps["brave"])

    def _build_steps(self) -> None:
        self._steps["hardware"] = build_hardware_step(self.theme, self.state)
        models = ModelsPanel(
            self.theme,
            self.state,
            openai_compat=self._openai_compat_from_config(),
        )
        models.request_show_info.connect(self._show_model_info_for)
        models.gemini_use_for_ask_ai.connect(self._on_gemini_use_for_ask_ai)
        self._steps["models"] = models
        self._steps["model_info"] = ModelInfoPanel(self.theme, self.state)
        self._steps["launch"] = build_launch_step(
            self.theme, self.state, self.server_manager
        )
        hw_panel = getattr(self._steps["hardware"], "_panel", None)
        launch_panel = getattr(self._steps["launch"], "_panel", None)
        if hw_panel is not None:
            hw_panel.scan_complete.connect(lambda _specs: self._on_hardware_scanned())
            if launch_panel is not None:
                hw_panel.scan_complete.connect(
                    lambda _specs: launch_panel._populate_gpus()
                )
        if launch_panel is not None:
            launch_panel.request_model_info.connect(self._show_model_info)
        if self.state.hardware_specs:
            self._enable_hf_query_buttons()
        self.mcp_host = McpAdapterHost(
            self.config, lambda: save_config(self.config), parent=self
        )
        configure = build_configure_step(
            self.theme,
            self.config,
            self.mcp_host,
            on_profile_applied=self._on_profile_applied,
            on_rag_start=self.start_rag_api,
            on_rag_stop=self.stop_rag_api,
            save_config=lambda: save_config(self.config),
        )
        configure.save_profile_requested.connect(self._save_profile)
        configure.provider_changed.connect(self._sync_models_openai_compat)
        self._steps["configure"] = configure
        if launch_panel is not None:
            launch_panel.llama_gui_launched.connect(self._after_llama_gui_launch)
        emb = getattr(configure, "embedding_panel", None)
        if emb is not None and launch_panel is not None:
            emb.acquire_adopted.connect(
                lambda _payload: launch_panel.reload_host_recipe()
            )
            launch_panel.embedding_model_launched.connect(
                emb.adopt_launched_embedding
            )
        self._steps["status"] = build_status_step(self.theme, self.config)
        self._steps["run"] = build_wiki_agent_run_panel(
            self.theme,
            config=self.config,
            title="6 Run Wiki Scan",
            source_label="Navigation Station",
        )
        self._steps["brave"] = build_brave_search_panel(self.theme)
        for w in self._steps.values():
            self.stack.addWidget(w)

    def _on_hardware_scanned(self) -> None:
        self._enable_hf_query_buttons()
        self._ensure_host_recipe()

    def _ensure_host_recipe(self) -> None:
        """Create/confirm recipe on first probe; report drift, never silent-apply."""
        try:
            from WarpCore import host_recipe as hr
            from spock_shell.host_recipe_ui import create_or_confirm_host_recipe
            from spock_shell.profiles import prompts_enabled

            live = hr.probe_hardware()
            current = hr.get_current_recipe(SHIP_COMPUTER_DB)
            if current is None or hr.needs_primary_ai_gpu_prompt(
                live, current.get("recipe")
            ):
                if not prompts_enabled():
                    self.state.status_message = (
                        "Host recipe needs primary AI GPU — open Bringup or "
                        "Maintenance → Recipe to confirm"
                    )
                    return
                row = create_or_confirm_host_recipe(
                    self,
                    SHIP_COMPUTER_DB,
                    reason="Host recipe (Navigation Station probe)",
                    created_by="navigation",
                    confirm_title="Create host recipe"
                    if current is None
                    else "Confirm primary AI GPU",
                    confirm_body=(
                        "No host recipe yet. Create Launch defaults from this probe?"
                        if current is None
                        else "Confirm which GPU should run embedding and chat."
                    ),
                )
                if row is None:
                    self.state.status_message = (
                        "Host recipe not saved — confirm primary AI GPU in "
                        "Bringup or Maintenance → Recipe"
                    )
                    return
                self.state.status_message = (
                    "Host recipe ready "
                    f"(AI GPU {(row.get('recipe') or {}).get('embed_gpu_index')})"
                )
                return
            drift = hr.hardware_drift(current, live=live)
            if drift:
                # Launch and model sizing fall back to a live proposal meanwhile.
                self.state.status_message = (
                    "Saved host recipe is for other hardware — using this probe; "
                    "save it in Maintenance → Recipe: " + "; ".join(drift)
                )
        except Exception as e:  # pragma: no cover - recipe is advisory here
            self.state.status_message = f"Host recipe unavailable: {e}"
            return

    def _enable_hf_query_buttons(self) -> None:
        models = self._steps.get("models")
        if models is None:
            return
        enabled = bool(self.state.hardware_specs)
        models.query_btn.setEnabled(enabled)
        models.query_embed_btn.setEnabled(enabled)

    def _rag_panel(self):
        """Embedding Profile panel — RAG host/port/key live on a Configure tab."""
        return getattr(self._steps.get("configure"), "embedding_panel", None)

    # --- profiles ---
    def _profile_payload(self) -> Dict[str, Any]:
        try:
            mcp_running = bool(self.mcp_host and self.mcp_host.running_pids())
        except Exception:
            mcp_running = False
        webui = getattr(self._steps.get("configure"), "webui_panel", None)
        try:
            webui_running = bool(webui is not None and webui.is_webui_running())
        except Exception:
            webui_running = False
        harvest_live_config(
            self.config,
            configure_panel=self._steps.get("configure"),
        )
        return build_profile_payload(
            self.config,
            llama_manager=self.server_manager,
            rag_running=self.rag_api_server is not None,
            mcp_running=mcp_running,
            webui_running=webui_running,
        )

    def _save_profile(self) -> None:
        save_profile_interactive(
            self,
            self._profile_payload(),
            prompt=(
                "Save these settings as a named profile?\n"
                "(Ask AI provider, RAG, MCP, Embedding Profile, running servers)"
            ),
        )

    def _offer_profile_load(self) -> None:
        payload = maybe_load_profile(self)
        if not payload:
            QTimer.singleShot(1500, self._maybe_autostart_from_config)
            QTimer.singleShot(5000, self._verify_mcp_autostart)
            return
        # Let the Load dialog finish closing before blocking the UI.
        self._pending_profile_payload = payload
        QTimer.singleShot(0, self._apply_pending_profile_payload)

    def _apply_pending_profile_payload(self) -> None:
        payload = getattr(self, "_pending_profile_payload", None)
        self._pending_profile_payload = None
        if not payload:
            return
        from spock_shell.busy_ui import busy_scope, clear_override_cursors

        with busy_scope(self, "Loading configuration profile…") as session:
            apply_profile_payload(
                payload,
                self.config,
                save_config=lambda: save_config(self.config),
                parent=self,
                llama_manager=self.server_manager,
                launch_panel=getattr(self._steps.get("launch"), "_panel", None),
                mcp_panel=getattr(self._steps.get("configure"), "mcp_panel", None),
                webui_panel=getattr(self._steps.get("configure"), "webui_panel", None),
                start_rag=self.start_rag_api,
                start_mcp=lambda mcp_cfg: self.mcp_host.start_adapter(
                    quiet=True,
                    transport=str(mcp_cfg.get("transport") or "streamable-http"),
                    http_host=str(mcp_cfg.get("http_host") or "127.0.0.1"),
                    http_port=int(mcp_cfg.get("http_port") or 8765),
                ),
                on_theme=self._apply_profile_theme,
            )
            session.pulse("Rebuilding Configure…")
            self._rebuild_configure_step()
        clear_override_cursors()
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.information(
            self,
            "Load profile",
            "Profile loaded. Settings restored; services were started only when needed.",
        )
        QTimer.singleShot(1500, self._maybe_autostart_from_config)
        QTimer.singleShot(5000, self._verify_mcp_autostart)

    def _verify_mcp_autostart(self) -> None:
        """Retry MCP HTTP once if autostart was expected but :8765 is still down."""
        mcp = self.config.get("mcp") or {}
        # WebUI MCP tools need the HTTP adapter even when only webui_autostart is set.
        need_adapter = bool(
            mcp.get("adapter_autostart") or mcp.get("webui_autostart")
        )
        if not need_adapter or self.mcp_host is None:
            return
        from spock_shell.proc_guard import tcp_open

        port = int(mcp.get("http_port") or 8765)
        host = str(mcp.get("http_host") or "127.0.0.1")
        if tcp_open(host, port):
            return
        try:
            self.mcp_host.ensure_http_adapter_async()
        except Exception as e:
            print(f"[profile] MCP autostart verify failed: {e}")

    def _maybe_autostart_from_config(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        from spock_shell.profiles import prompts_enabled

        if not prompts_enabled():
            return

        rag = self.config.get("rag_api") or {}
        if rag.get("enabled") and self.rag_api_server is None:
            try:
                self.start_rag_api()
            except Exception as e:
                QMessageBox.warning(
                    self, "RAG API", f"Could not start RAG API:\n{e}"
                )
        mcp = self.config.get("mcp") or {}
        # WebUI MCP connection requires :8765 — start adapter with WebUI too.
        need_adapter = bool(
            mcp.get("adapter_autostart") or mcp.get("webui_autostart")
        )
        if self.mcp_host is not None and need_adapter:
            try:
                self.mcp_host.ensure_http_adapter_async()
            except Exception as e:
                print(f"[profile] MCP adapter autostart failed: {e}")
        if mcp.get("webui_autostart"):
            webui = getattr(self._steps.get("configure"), "webui_panel", None)
            try:
                if webui is not None and not webui.is_webui_running():
                    webui.start_ui_mcp_proxy(quiet=True)
            except Exception:
                pass

    def _rebuild_configure_step(self) -> None:
        """Configure caches widget values, so rebuild it from the restored config."""
        old = self._steps.get("configure")
        if old is None:
            return
        self.stack.removeWidget(old)
        old.deleteLater()
        configure = build_configure_step(
            self.theme,
            self.config,
            self.mcp_host,
            on_profile_applied=self._on_profile_applied,
            on_rag_start=self.start_rag_api,
            on_rag_stop=self.stop_rag_api,
            save_config=lambda: save_config(self.config),
        )
        configure.save_profile_requested.connect(self._save_profile)
        configure.provider_changed.connect(self._sync_models_openai_compat)
        self._steps["configure"] = configure
        self.stack.addWidget(configure)
        self._sync_models_openai_compat()
        emb = getattr(configure, "embedding_panel", None)
        launch_panel = getattr(self._steps.get("launch"), "_panel", None)
        if emb is not None and launch_panel is not None:
            emb.acquire_adopted.connect(
                lambda _payload: launch_panel.reload_host_recipe()
            )
        if self.rag_api_server is not None:
            configure.embedding_panel.set_rag_running(
                True, self.rag_api_server.base_url
            )

    def _apply_profile_theme(self, theme_name: str) -> None:
        if theme_name not in THEMES or theme_name == self.current_theme:
            return
        if getattr(self, "theme_combo", None) is not None:
            self.theme_combo.setCurrentText(theme_name)
        else:
            self.change_theme(theme_name)

    def _on_profile_applied(self, profile: dict) -> None:
        self.config["embedding_profile"] = merge_embedding_profile(profile)
        panel = self._rag_panel()
        if panel is not None:
            self.config["rag_api"] = panel.collect_rag_api()
        set_embeddings_url(self.config["embedding_profile"].get("embeddings_url"))
        write_embedding_env(self.config["embedding_profile"])
        save_config(self.config)

    def start_rag_api(self) -> None:
        ensure_root_on_path()
        panel = self._rag_panel()
        if panel is not None:
            self.config["rag_api"] = panel.collect_rag_api()
            save_config(self.config)
        cfg = self.config.get("rag_api") or {}
        host = cfg.get("host", "127.0.0.1")
        port = int(cfg.get("port", 8090))
        api_key = cfg.get("api_key", "")
        import time as _time

        from spock_shell.paths import ROOT
        from spock_shell.proc_guard import exclusive_start, pids_running_script, tcp_open
        from spock_shell.rag_host import is_rag_up, rag_url

        def _attach_existing() -> bool:
            if self.rag_api_server is not None:
                self.config.setdefault("rag_api", {})["enabled"] = True
                save_config(self.config)
                if panel is not None:
                    panel.set_rag_running(True, self.rag_api_server.base_url)
                return True
            if is_rag_up(host, port):
                self.config.setdefault("rag_api", {})["enabled"] = True
                save_config(self.config)
                if panel is not None:
                    panel.set_rag_running(True, rag_url(host, port))
                return True
            return False

        with exclusive_start("rag_api") as locked:
            if _attach_existing():
                return
            existing = pids_running_script(ROOT / "_start_rag_api.py")
            if existing or tcp_open(str(host), int(port)):
                deadline = _time.time() + 8.0
                while _time.time() < deadline:
                    if _attach_existing():
                        return
                    _time.sleep(0.4)
                if existing:
                    self.config.setdefault("rag_api", {})["enabled"] = True
                    save_config(self.config)
                    if panel is not None:
                        panel.set_rag_running(True, rag_url(host, port))
                    return
            if not locked:
                return

            self.stop_rag_api(persist=False)

            from deep_dive import (
                build_documents_filter_clause,
                packing_opts_from_config,
                run_http_deep_dive,
            )
            from model_selector_core import merge_embedding_profile as _mep
            from WarpCore.search import hybrid_search
            from spock_shell.embedding_corpus import guarded_hybrid_search

            search = guarded_hybrid_search(hybrid_search)

            emb = _mep(self.config.get("embedding_profile")).get(
                "embeddings_url", "http://localhost:8080/embeddings"
            )
            self._llm = make_llm_client(self.config)

            def build_filter(
                path_contains: str,
                extension: str = "",
                exclude_generated: bool = True,
            ) -> str:
                return build_documents_filter_clause(
                    path_contains or "",
                    extension or "",
                    exclude_generated=bool(exclude_generated),
                )

            def deep_dive(**kwargs):
                client = kwargs.get("llm") or self._llm
                try:
                    from deep_dive import packing_opts_for_llm

                    opts = packing_opts_for_llm(self.config, client)
                except Exception:
                    opts = packing_opts_from_config(self.config)
                return run_http_deep_dive(
                    question=kwargs.get("question") or "",
                    filter_clause=kwargs.get("filter_clause") or "",
                    history=kwargs.get("history") or [],
                    llm=client,
                    embeddings_url=kwargs.get("embeddings_url") or emb,
                    db_path=kwargs.get("db_path") or SHIP_COMPUTER_DB,
                    hybrid_search_fn=search,
                    n_ctx=int(opts["n_ctx"]),
                    max_out_tokens=int(opts["max_out_tokens"]),
                    ask_ai_provider=str(opts["ask_ai_provider"]),
                    chat_url=str(opts["chat_url"]),
                )

            self.rag_api_server = RagApiServer(
                host=host,
                port=port,
                db_path=SHIP_COMPUTER_DB,
                api_key=api_key,
                get_embeddings_url=lambda: emb,
                get_llm_client=lambda: self._llm,
                hybrid_search_fn=search,
                build_filter_fn=build_filter,
                deep_dive_fn=deep_dive,
            )
            try:
                self.rag_api_server.start()
            except OSError as e:
                self.rag_api_server = None
                raise RuntimeError(f"Failed to start RAG API: {e}") from e
            self.config.setdefault("rag_api", {})["enabled"] = True
            save_config(self.config)
            if panel is not None:
                panel.set_rag_running(True, self.rag_api_server.base_url)

    def stop_rag_api(self, persist: bool = True) -> None:
        if self.rag_api_server is not None:
            try:
                self.rag_api_server.stop()
            except Exception:
                pass
            self.rag_api_server = None
        if persist:
            self.config.setdefault("rag_api", {})["enabled"] = False
            try:
                save_config(self.config)
            except Exception:
                pass
        panel = self._rag_panel()
        if panel is not None:
            panel.set_rag_running(False)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Snapshot before teardown so the profile records what was still running.
        if not prompt_save_profile(self, self._profile_payload()):
            event.ignore()
            return
        self.stop_rag_api(persist=False)
        # wiki_agent.py is a daemon: leaving it orphaned keeps embedding the KB.
        stop_scan = getattr(self._steps.get("run"), "_stop", None)
        if callable(stop_scan):
            try:
                stop_scan()
            except Exception:
                pass
        mcp = getattr(self, "mcp_host", None)
        kill_mcp = getattr(mcp, "kill_processes", None)
        if callable(kill_mcp):
            try:
                kill_mcp()
            except Exception:
                pass
        try:
            from mcp_panel import stop_ui_mcp_proxy

            stop_ui_mcp_proxy()
        except Exception:
            pass
        super().closeEvent(event)
