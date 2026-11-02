"""Stand-alone Run Wiki Scan window (PyQt6)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from WarpCore import settings_store
from WarpCore.theme import apply_theme_to, theme_by_name
from spock_wiki_adapter.paths import ROOT as DEFAULT_ROOT
from spock_wiki_adapter.wiki_run import build_wiki_agent_run_panel


class WikiScanWindow(QMainWindow):
    def __init__(self, root: Optional[Path] = None) -> None:
        super().__init__()
        self.root = (root or DEFAULT_ROOT).resolve()
        self.db_path = self.root / "ship_computer.db"
        self.config = settings_store.load_app_config(str(self.db_path))
        theme_name = str(self.config.get("theme") or "dark")
        self.theme = theme_by_name(theme_name)

        self.setWindowTitle("Run Wiki Scan")
        self.resize(920, 720)

        panel = build_wiki_agent_run_panel(
            self.theme,
            config=self.config,
            title="Run Wiki Scan",
            source_label="Spock Onboarding",
        )
        self._panel = panel

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(panel)
        self.setCentralWidget(central)

        apply_theme_to(self, self.theme, scope="main")

    def closeEvent(self, event) -> None:  # noqa: N802
        stop = getattr(self._panel, "_stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                pass
        super().closeEvent(event)


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path.cwd()
    if "--root" in args:
        i = args.index("--root")
        if i + 1 < len(args):
            root = Path(args[i + 1])
    app = QApplication(sys.argv)
    win = WikiScanWindow(root=root)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
