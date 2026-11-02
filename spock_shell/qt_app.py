"""Shared QApplication bootstrap for suite mini-apps (WebEngine-safe)."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


def create_app(argv=None) -> QApplication:
    argv = argv if argv is not None else sys.argv
    # Spock-to-bridge imports QWebEngineView; attribute must be set first.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except Exception:
        pass
    app = QApplication(argv)
    app.setQuitOnLastWindowClosed(True)
    try:
        from spock_shell.win_job import ensure_kill_on_close_job

        ensure_kill_on_close_job()
    except Exception:
        pass
    app.aboutToQuit.connect(_reap_on_quit)
    return app


def _reap_on_quit() -> None:
    """Stop llama / RAG this process started. The Windows job kills the rest."""
    try:
        from llama_server_manager import stop_all_owned_in_process

        stop_all_owned_in_process()
    except Exception:
        pass
    try:
        from spock_shell.rag_host import stop_spawned_rag

        stop_spawned_rag()
    except Exception:
        pass
