"""Spock-UIE-Wiki-KB main orchestrator — lite launch hub for suite mini-apps."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QLabel,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spock_shell.brave_search import build_brave_search_panel
from spock_shell.markdown_home import build_markdown_home, reload_markdown_home
from spock_shell.paths import ROOT, ensure_root_on_path
from spock_shell.widgets import SidePanel
from spock_shell.window import NavItem, SuiteShellWindow

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

HELPER_MD = "AIHelperDocuments/Spock-UIE-Wiki-KB-HELPER.md"

# Left-nav launchers: (button label without .py, script relative to repo root).
# First-models / onboarding wizard stay out of this lite hub.
SUITE_LAUNCHERS: List[Tuple[str, str]] = [
    ("spock_navigation", "spock_navigation.py"),
    ("spock_uieg", "spock_uieg.py"),
    ("spock_maintenance", "spock_maintenance.py"),
]


def _venv_python(root: Path) -> str:
    win = root / ".venv" / "Scripts" / "python.exe"
    if win.is_file():
        return str(win)
    nix = root / ".venv" / "bin" / "python"
    if nix.is_file():
        return str(nix)
    return sys.executable


def _terminate_process_tree(pid: int, timeout: float = 8.0) -> None:
    """Terminate pid and descendants (llama-server children of a suite script)."""
    if psutil is None:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        return
    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    kids = parent.children(recursive=True)
    for child in kids:
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    try:
        parent.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    _, alive = psutil.wait_procs(kids + [parent], timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


class UieWikiKbOrchestratorWindow(SuiteShellWindow):
    """Lite hub that opens each stand-alone Spock suite entry in its own process."""

    app_title = "Spock-UIE-Wiki-KB"
    app_subtitle = (
        "Lite orchestrator — open Navigation, UIEG, or Maintenance as "
        "stand-alone suite mini-apps."
    )

    def __init__(self, parent=None):
        ensure_root_on_path()
        self._root = Path(ROOT)
        self._brave: Optional[QWidget] = None
        self._launch_log: Optional[QTextEdit] = None
        self._log_panel: Optional[QWidget] = None
        self._suite_procs: List[subprocess.Popen] = []
        # Skip LlamaServerManager construction in SuiteShellWindow (startup lag).
        self.server_manager = None
        super().__init__(parent)

    def on_ready(self) -> None:
        self.show_home()

    def closeEvent(self, event):  # noqa: N802
        # No save-profile prompt on the lite hub.
        self._reap_suite_children()
        try:
            from spock_shell.rag_host import stop_spawned_rag

            stop_spawned_rag()
        except Exception:
            pass
        super().closeEvent(event)

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
        steps: List[NavItem] = [("Home", self.show_home)]
        for label, script in SUITE_LAUNCHERS:
            steps.append((label, lambda *_, s=script: self._launch_suite(s)))
        steps.extend(
            [
                ("-----", None),
                ("Launch log", self._show_launch_log),
                ("Exit", self.close),
            ]
        )
        return steps

    def build_right_dock(self, layout: QVBoxLayout) -> None:
        search = SidePanel("Search", self.theme)
        search.add_button("Google Search", self._show_brave_search)
        layout.addWidget(search)
        super().build_right_dock(layout)

    def _build_ui(self) -> None:
        super()._build_ui()
        self._log_panel = self._build_launch_log_panel()
        self.stack.addWidget(self._log_panel)

    def _build_launch_log_panel(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        title = QLabel("Suite launch log")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lay.addWidget(title)
        tip = QLabel(
            "Left-nav entries start each stand-alone script in a new process. "
            "This hub stays open so you can launch more stations."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self._launch_log = QTextEdit()
        self._launch_log.setReadOnly(True)
        self._launch_log.setFont(QFont("Consolas", 10))
        self._launch_log.setPlainText(
            "No launches yet. Pick a suite script from the left Navigation panel."
        )
        lay.addWidget(self._launch_log, 1)
        return wrap

    def _show_launch_log(self) -> None:
        if self._log_panel is not None:
            self.show_center(self._log_panel)

    def _append_log(self, line: str) -> None:
        if self._launch_log is None:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        cur = self._launch_log.toPlainText().strip()
        if cur.startswith("No launches yet"):
            cur = ""
        block = f"[{stamp}] {line}"
        self._launch_log.setPlainText((cur + "\n" + block).strip() if cur else block)

    def _launch_suite(self, script_name: str) -> None:
        script = self._root / script_name
        if not script.is_file():
            QMessageBox.warning(
                self,
                "Missing script",
                f"Not found:\n{script}",
            )
            self._append_log(f"FAIL {script_name} — file missing")
            self._show_launch_log()
            return
        python = _venv_python(self._root)
        try:
            proc = subprocess.Popen(
                [python, str(script)],
                cwd=str(self._root),
            )
        except OSError as e:
            QMessageBox.warning(self, "Launch failed", str(e))
            self._append_log(f"FAIL {script_name} — {e}")
            self._show_launch_log()
            return
        self._suite_procs.append(proc)
        self._append_log(f"OK   {script_name}  pid={proc.pid}  via {python}")
        self._show_launch_log()

    def _reap_suite_children(self) -> None:
        """Terminate mini-apps this hub started, including their llama-server children."""
        still: List[subprocess.Popen] = []
        for proc in self._suite_procs:
            if proc.poll() is not None:
                continue
            _terminate_process_tree(proc.pid)
            if proc.poll() is None:
                still.append(proc)
        self._suite_procs = still

    def _show_brave_search(self) -> None:
        if self._brave is None:
            self._brave = build_brave_search_panel(self.theme)
            self.stack.addWidget(self._brave)
        self.show_center(self._brave)
