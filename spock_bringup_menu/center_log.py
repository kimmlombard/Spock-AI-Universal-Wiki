"""Center workspace: step checklist + embedded progress log."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from spock_bringup_menu.steps import STEPS
from spock_progress_log.panel import ProgressLogPanel


class BringupCenterPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._states: Dict[int, str] = {s.id: " " for s in STEPS if s.kind != "exit"}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        title = QLabel("Spock Bringup — progress")
        tf = QFont()
        tf.setPointSize(13)
        tf.setBold(True)
        title.setFont(tf)
        lay.addWidget(title)

        tip = QLabel(
            "Pick a step on the left. CLI steps stream here; Ask AI opens in this "
            "pane; suite apps open in their own windows and are logged below."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #aaa;")
        lay.addWidget(tip)

        self.checklist = QTextEdit()
        self.checklist.setReadOnly(True)
        self.checklist.setMaximumHeight(200)
        self.checklist.setFont(QFont("Consolas", 10))
        lay.addWidget(self.checklist)

        self.progress = ProgressLogPanel(self)
        lay.addWidget(self.progress, 1)

        self._refresh_checklist()

    def _refresh_checklist(self) -> None:
        lines = ["Step checklist:", ""]
        for s in STEPS:
            if s.kind == "exit":
                continue
            mark = self._states.get(s.id, " ")
            if mark == "ok":
                tag = "[ok]"
            elif mark == "fail":
                tag = "[fail]"
            elif mark == "run":
                tag = "[..]"
            else:
                tag = "[  ]"
            lines.append(f"  {tag} {s.id:>2d}. {s.label}")
        self.checklist.setPlainText("\n".join(lines))

    def set_step_state(self, step_id: int, state: str) -> None:
        if step_id in self._states:
            self._states[step_id] = state
            self._refresh_checklist()

    def mark_running(self, step_id: int) -> None:
        self.set_step_state(step_id, "run")

    def mark_result(self, step_id: int, ok: bool) -> None:
        self.set_step_state(step_id, "ok" if ok else "fail")

    def append_launch(self, line: str) -> None:
        self.progress.append_line(line)

    def start_cli(self, *, title: str, command: list, cwd: Path) -> bool:
        if self.progress.is_running:
            return False
        self.progress.clear_log()
        return self.progress.start(title=title, command=command, cwd=cwd)
