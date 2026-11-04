"""Spock-Science-Station — Wiki Agent / ingest."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from llama_server_manager import LlamaServerManager
from model_selector_panels import (
    LaunchPanel,
    ModelInfoPanel,
    ModelSelectorState,
    ModelsPanel,
)
from model_selector_core import merge_embedding_profile
from NavigationStation.steps.hardware import build_hardware_step
from ScienceStation.ships_logs import build_ships_logs_panel
from ScienceStation.wiki_run import build_wiki_agent_run_panel
from spock_shell.brave_search import build_brave_search_panel
from spock_shell.bridge_host import make_llm_client
from spock_shell.config import save_config
from spock_shell.markdown_home import build_markdown_home, reload_markdown_home
from spock_shell.paths import SHIP_COMPUTER_DB, ensure_root_on_path
from spock_shell.widgets import SidePanel
from spock_shell.window import NavItem, SuiteShellWindow

HELPER_MD = "AIHelperDocuments/Spock-Science-Station-HELPER.md"


class ScienceStationWindow(SuiteShellWindow):
    app_title = "Spock-Science-Station"
    app_subtitle = (
        "Hardware → HF Models → Launch embed/chat → RUN Wiki Agent → "
        "Ship's Logs → Ask AI."
    )

    def __init__(self, parent=None):
        ensure_root_on_path()
        self.state = ModelSelectorState()
        self.server_manager = LlamaServerManager()
        self.manager = self.server_manager  # Ship Status / Launch compatibility
        self._steps: Dict[str, Any] = {}
        self._hw_scanned_once = False
        self._logs = None
        self._ask = None
        super().__init__(parent)

    def on_ready(self) -> None:
        self._build_steps()
        self.show_home()

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
            ("4 Run Wiki Scan", lambda: self.show_center(self._steps["run"])),
            ("5 Ship's Logs", self._show_ships_logs),
            ("6 Run Ask AI", self._show_ask_ai),
            ("-----", None),
            ("Exit", self.close),
        ]

    def _show_ships_logs(self) -> None:
        """Captains Log / Agents Queue / Documents / Quarantine, tabbed."""
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

    def build_right_dock(self, layout: QVBoxLayout) -> None:
        search = SidePanel("Search", self.theme)
        search.add_button("Google Search", self._show_brave_search)
        layout.addWidget(search)
        super().build_right_dock(layout)

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

    def _on_gemini_use_for_ask_ai(self, model_id: str) -> None:
        mid = (model_id or "").strip()
        if not mid:
            return
        self.config["openai_compat_model"] = mid
        self.config["ask_ai_provider"] = "OpenAI-compatible"
        save_config(self.config)

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
        launch = LaunchPanel(self.theme, self.state, self.server_manager)
        launch.request_model_info.connect(self._show_model_info)
        self._steps["launch"] = launch
        self._steps["model_info"] = ModelInfoPanel(self.theme, self.state)
        self._steps["run"] = build_wiki_agent_run_panel(
            self.theme, config=self.config
        )
        self._steps["brave"] = build_brave_search_panel(self.theme)

        hw_panel = getattr(self._steps["hardware"], "_panel", None)
        if hw_panel is not None:
            hw_panel.scan_complete.connect(
                lambda _specs: self._on_hardware_scanned()
            )
            # Keep Launch GPU list in sync after scan (same as Navigation).
            hw_panel.scan_complete.connect(lambda _specs: launch._populate_gpus())

        for w in self._steps.values():
            self.stack.addWidget(w)

        # If state already has specs (restored), unlock HF Query buttons.
        if self.state.hardware_specs:
            self._enable_hf_query_buttons()

    def _on_hardware_scanned(self) -> None:
        self._enable_hf_query_buttons()

    def _enable_hf_query_buttons(self) -> None:
        models = self._steps.get("models")
        if models is None:
            return
        enabled = bool(self.state.hardware_specs)
        models.query_btn.setEnabled(enabled)
        models.query_embed_btn.setEnabled(enabled)

    def _show_hardware(self) -> None:
        w = self._steps["hardware"]
        self.show_center(w)
        panel = getattr(w, "_panel", None)
        if panel is not None and not self._hw_scanned_once:
            self._hw_scanned_once = True
            QTimer.singleShot(0, panel._start_scan)

    def _show_models(self) -> None:
        self._enable_hf_query_buttons()
        models = self._steps.get("models")
        if models is not None:
            models.set_openai_compat(self._openai_compat_from_config())
        self.show_center(self._steps["models"])

    def _show_launch(self) -> None:
        launch = self._steps["launch"]
        launch._populate_gpus()
        launch._update_buttons()
        self.show_center(launch)

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

    def _show_brave_search(self) -> None:
        self.show_center(self._steps["brave"])

    def closeEvent(self, event) -> None:  # noqa: N802
        run = self._steps.get("run")
        stop = getattr(run, "_stop", None) if run is not None else None
        if callable(stop):
            try:
                stop()
            except Exception:
                pass
        super().closeEvent(event)
