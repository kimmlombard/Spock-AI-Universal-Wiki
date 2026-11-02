"""Stand-alone Embedding Profile / RAG API window (PyQt6)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QScrollArea, QVBoxLayout, QWidget

from WarpCore import settings_store
from WarpCore.config_defaults import merge_embedding_profile
from WarpCore.theme import apply_theme_to, theme_by_name
from spock_rag_adapter.embedding_panel import EmbeddingProfilePanel
from spock_rag_adapter.paths import ROOT as DEFAULT_ROOT, SHIP_COMPUTER_DB
from spock_rag_adapter.rag_host import RagAdapterHost, is_rag_up, rag_bind


class EmbeddingRagWindow(QMainWindow):
    def __init__(self, root: Optional[Path] = None) -> None:
        super().__init__()
        self.root = (root or DEFAULT_ROOT).resolve()
        self.db_path = self.root / "ship_computer.db"
        self.config = settings_store.load_app_config(str(self.db_path))
        theme_name = str(self.config.get("theme") or "dark")
        self.theme = theme_by_name(theme_name)

        self.setWindowTitle("Embedding Profile / RAG API")
        self.resize(860, 820)

        self.rag_host = RagAdapterHost(
            self.config,
            self._save_config,
            parent=self,
        )

        panel = EmbeddingProfilePanel(
            self.theme,
            profile=merge_embedding_profile(self.config.get("embedding_profile")),
            rag_api=self.config.get("rag_api") or {},
            db_path=str(self.db_path if self.db_path.is_file() else SHIP_COMPUTER_DB),
        )
        panel.profile_applied.connect(self.rag_host.on_profile_applied)
        panel.rag_api_start.connect(self.rag_host.start_rag)
        panel.rag_api_stop.connect(self.rag_host.stop_rag)
        self.rag_host.panel = panel

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(12, 12, 12, 12)
        inner_lay.addWidget(panel)
        scroll.setWidget(inner)
        self.setCentralWidget(scroll)

        apply_theme_to(self, self.theme, scope="main")

        host, port = rag_bind(self.config)
        if is_rag_up(host, port):
            panel.set_rag_running(True, f"http://{host}:{port}/v1")

        rag = self.config.get("rag_api") or {}
        if rag.get("enabled") and not is_rag_up(host, port):
            QTimer.singleShot(400, self.rag_host.start_rag)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(8000)
        self._status_timer.timeout.connect(self.rag_host.refresh_panel)
        # Pick up a step 3 Acquire that finishes while this window is open.
        self._status_timer.timeout.connect(self._refresh_acquire)
        self._status_timer.start()

    def _refresh_acquire(self) -> None:
        panel = getattr(self.rag_host, "panel", None)
        refresh = getattr(panel, "refresh_from_acquire", None)
        if callable(refresh):
            refresh(fill=False)

    def _save_config(self) -> None:
        settings_store.save_app_config(str(self.db_path), self.config, by="rag_adapter")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._status_timer.isActive():
            self._status_timer.stop()
        super().closeEvent(event)


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path.cwd()
    if "--root" in args:
        i = args.index("--root")
        if i + 1 < len(args):
            root = Path(args[i + 1])
    app = QApplication(sys.argv)
    win = EmbeddingRagWindow(root=root)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
