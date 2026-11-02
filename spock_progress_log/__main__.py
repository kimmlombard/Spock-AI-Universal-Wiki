"""Run a command and stream its output into a scrollable PyQt6 modal.

Usage:
  python -m spock_progress_log --title "Bring up" -- python -u -m spock_bringup up
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)

from spock_progress_log.panel import ProgressLogPanel


class ProgressLogDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        command: list[str],
        cwd: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "Spock progress")
        self.resize(780, 520)
        self.setMinimumSize(520, 320)

        layout = QVBoxLayout(self)
        self.panel = ProgressLogPanel(self)
        layout.addWidget(self.panel, stretch=1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.close_btn = QPushButton("Close")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setDefault(True)
        row.addWidget(self.close_btn)
        layout.addLayout(row)

        self.panel.finished.connect(self._on_panel_finished)
        self.panel.start(title=title, command=command, cwd=cwd)

    def _on_panel_finished(self, _code: int) -> None:
        self.close_btn.setEnabled(True)
        self.close_btn.setFocus(Qt.FocusReason.OtherFocusReason)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.panel.is_running:
            self.panel.stop()
        super().closeEvent(event)

    @property
    def exit_code(self) -> int:
        return self.panel.exit_code


def run_progress_log(*, title: str, command: list[str], cwd: Path) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = ProgressLogDialog(title=title, command=command, cwd=cwd)
    dlg.exec()
    return dlg.exit_code


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(
        prog="spock_progress_log",
        description="Stream a command into a scrollable PyQt6 log modal",
    )
    p.add_argument("--title", default="Spock progress")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command after --  e.g. -- python -u -m spock_bringup up",
    )
    args = p.parse_args(argv)
    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print(
            "Usage: python -m spock_progress_log --title T -- cmd args...",
            file=sys.stderr,
        )
        return 2
    root = args.root.resolve()
    return run_progress_log(title=args.title, command=cmd, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
