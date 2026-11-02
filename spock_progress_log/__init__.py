"""Scrollable PyQt6 progress / status log modal and embeddable panel."""

from spock_progress_log.panel import ProgressLogPanel

__all__ = ["ProgressLogPanel", "run_progress_log"]


def __getattr__(name: str):
    if name == "run_progress_log":
        from spock_progress_log.__main__ import run_progress_log

        return run_progress_log
    raise AttributeError(name)
