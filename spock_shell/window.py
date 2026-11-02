"""Suite shell: left nav + center stack + AI Helper / Status / About (skeleton-v2)."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spock_shell.about import AboutDialog
from spock_shell.ai_helper import open_ai_helper
from spock_shell.config import load_config, save_config
from spock_shell.status_panel import StatusConsole
from spock_shell.theme import THEMES, main_stylesheet
from spock_shell.widgets import ModernButton, SidePanel

NavItem = Tuple[str, Optional[Callable[[], None]]]


class SuiteShellWindow(QMainWindow):
    """Base window for every Spock suite mini-app.

    Subclasses set ``app_title``, ``nav_steps`` (center work steps), and may
    override ``build_right_dock`` / ``on_ready``.
    """

    app_title: str = "Spock Suite"
    app_subtitle: str = "Shared shell — pick a step on the left"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = load_config()
        theme_name = str(self.config.get("theme") or "light")
        if theme_name not in THEMES:
            theme_name = "light"
        self.current_theme = theme_name
        self.theme = THEMES[theme_name]
        self._status_win: Optional[StatusConsole] = None
        self._ship_status_win = None
        self._ai_helper_win: Optional[QWidget] = None
        self._step_ids: List[str] = []
        # Shared so Ship Status (Live Monitor) works in every suite wizard.
        try:
            from llama_server_manager import LlamaServerManager

            if not hasattr(self, "server_manager") and not hasattr(self, "manager"):
                self.server_manager = LlamaServerManager()
        except Exception:
            pass
        self.setWindowTitle(self.app_title)
        # Wider default so Configure Spock AI tabs 6–9 stay reachable under WSLg scaling.
        self.setGeometry(40, 40, 1600, 900)
        self._build_ui()
        self.apply_theme()
        self.on_ready()

    # --- hooks for mini-apps ---
    def nav_steps(self) -> Sequence[NavItem]:
        """Return (label, callback_or_None). None = separator."""
        return [
            ("Home", self.show_home),
            ("-----", None),
            ("AI Helper", self.open_ai_helper),
            ("About", self.open_about),
            ("Exit", self.close),
        ]

    def build_home_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        title = QLabel(self.app_title)
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        sub = QLabel(self.app_subtitle)
        sub.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addStretch()
        return w

    def build_right_dock(self, layout: QVBoxLayout) -> None:
        color = SidePanel("Color Scheme", self.theme)
        color.layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setCurrentText(self.current_theme)
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        color.layout.addWidget(self.theme_combo)
        layout.addWidget(color)

    def on_ready(self) -> None:
        pass

    # --- UI ---
    def _build_ui(self) -> None:
        # Three-pane splitter (nav | center | tools) — drag the handles to
        # resize panels the same way the old Spock-UIE-Wiki-KB monolith did.
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        self.splitter.setOpaqueResize(True)

        left = QFrame()
        left.setObjectName("SuiteNavPane")
        left.setMinimumWidth(160)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)
        nav_title = QLabel("Navigation")
        nav_title.setObjectName("SuitePaneTitle")
        left_lay.addWidget(nav_title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        nav_layout = QVBoxLayout(content)
        nav_layout.setContentsMargins(10, 10, 10, 10)
        nav_layout.setSpacing(8)
        self._nav_buttons: List[ModernButton] = []
        for label, cb in self.nav_steps():
            if label.startswith("---") or cb is None:
                sep = QLabel("-----")
                sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
                nav_layout.addWidget(sep)
                continue
            btn = ModernButton(label, self.theme)
            btn.clicked.connect(cb)
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)
        nav_layout.addStretch()
        scroll.setWidget(content)
        left_lay.addWidget(scroll, 1)

        self.stack = QStackedWidget()
        self._home = self.build_home_widget()
        self.stack.addWidget(self._home)

        right = QFrame()
        right.setObjectName("SuiteToolsPane")
        right.setMinimumWidth(180)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        tools_title = QLabel("Tools")
        tools_title.setObjectName("SuitePaneTitle")
        right_lay.addWidget(tools_title)
        rscroll = QScrollArea()
        rscroll.setWidgetResizable(True)
        rscroll.setFrameShape(QFrame.Shape.NoFrame)
        rcontent = QWidget()
        rlayout = QVBoxLayout(rcontent)
        rlayout.setContentsMargins(8, 8, 8, 8)
        common = SidePanel("Suite", self.theme)
        common.add_button("AI Helper", self.open_ai_helper)
        common.add_button("Ship Status", self.open_status)
        common.add_button("About", self.open_about)
        rlayout.addWidget(common)
        self.build_right_dock(rlayout)
        rlayout.addStretch()
        rscroll.setWidget(rcontent)
        right_lay.addWidget(rscroll, 1)

        self.splitter.addWidget(left)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        # Match ~1600px default so Configure Spock AI tabs 6–9 stay on-screen
        # under WSLg scaling (same usable center width as a stretched Navigation).
        self.splitter.setSizes([220, 1140, 240])
        self.setCentralWidget(self.splitter)

        # Bottom-right size grip so the whole window corners resize like before.
        status = QStatusBar()
        status.setSizeGripEnabled(True)
        self.setStatusBar(status)

    def show_home(self) -> None:
        self.stack.setCurrentWidget(self._home)

    def show_center(self, widget: QWidget) -> None:
        if self.stack.indexOf(widget) < 0:
            self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)

    def open_ai_helper(self) -> None:
        self._ai_helper_win = open_ai_helper(self, self.theme, self.config)

    def open_status(self) -> None:
        """Open Ship Status (Live Monitor). Subclasses with a llama manager use it."""
        manager = getattr(self, "server_manager", None) or getattr(
            self, "manager", None
        )
        if manager is not None:
            from model_selector_panels import LlmStatusWindow

            if getattr(self, "_ship_status_win", None) is None:
                self._ship_status_win = LlmStatusWindow(
                    self.theme,
                    manager,
                    parent=None,
                    get_lm_config=lambda: {
                        "host": self.config.get("lm_studio_host", "localhost"),
                        "port": int(self.config.get("lm_studio_port") or 1234),
                        "context_length": int(
                            self.config.get("lm_studio_context_length") or 32768
                        ),
                    },
                    get_spock_health_context=lambda: {
                        "api_base": (
                            f"http://{(self.config.get('rag_api') or {}).get('host', '127.0.0.1')}:"
                            f"{int((self.config.get('rag_api') or {}).get('port', 8090))}"
                        ),
                        "db_path": __import__(
                            "spock_shell.paths", fromlist=["SHIP_COMPUTER_DB"]
                        ).SHIP_COMPUTER_DB,
                        "embeddings_url": (
                            (self.config.get("embedding_profile") or {}).get(
                                "embeddings_url"
                            )
                            or "http://localhost:8080/embeddings"
                        ),
                        **{
                            k: self.config.get(k)
                            for k in (
                                "llama_host",
                                "llama_port",
                                "rag_api",
                                "mcp",
                                "embedding_profile",
                            )
                        },
                    },
                    window_title="Ship Status",
                    show_lm_studio_tab=False,
                )
            else:
                self._ship_status_win.theme = self.theme
                self._ship_status_win.apply_theme()
            self._ship_status_win.show()
            self._ship_status_win.raise_()
            # Match monolith: Refresh Live Monitor as soon as the window appears.
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(0, self._ship_status_win.refresh_inst_btn.click)
            return

        if self._status_win is None:
            self._status_win = StatusConsole(self.theme, self.config)
        else:
            self._status_win.config = self.config
            self._status_win.theme = self.theme
            self._status_win.apply_theme()
        self._status_win.setWindowTitle("Ship Status")
        self._status_win.show()
        self._status_win.raise_()
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(0, self._status_win.refresh)

    def open_about(self) -> None:
        AboutDialog(self.theme, self.app_title, self).exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        mgr = getattr(self, "server_manager", None) or getattr(self, "manager", None)
        stop_owned = getattr(mgr, "stop_owned", None)
        if callable(stop_owned):
            try:
                stop_owned()
            except Exception:
                pass
        super().closeEvent(event)

    def change_theme(self, theme_name: str) -> None:
        if theme_name not in THEMES:
            return
        self.current_theme = theme_name
        self.theme = THEMES[theme_name]
        self.config["theme"] = theme_name
        try:
            save_config(self.config)
        except Exception:
            pass
        self.apply_theme()

    def apply_theme(self) -> None:
        self.setStyleSheet(main_stylesheet(self.theme))
        for btn in self.findChildren(ModernButton):
            btn.theme = self.theme
            btn.apply_theme()
        for panel in self.findChildren(SidePanel):
            panel.theme = self.theme
            panel.apply_theme()
