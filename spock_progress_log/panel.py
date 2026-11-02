"""Reusable PyQt6 progress log panel (QProcess streaming)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from PyQt6.QtCore import QProcess, QProcessEnvironment, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _enriched_path() -> str:
    """Merge User + Machine PATH so GUI-spawned children see installed Python/winget."""
    parts: List[str] = []
    for key in ("PATH", "Path"):
        cur = os.environ.get(key)
        if cur:
            parts.extend(cur.split(os.pathsep))
            break
    if sys.platform == "win32":
        try:
            import winreg

            for hive, sub in (
                (winreg.HKEY_CURRENT_USER, r"Environment"),
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                ),
            ):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        val, _ = winreg.QueryValueEx(k, "Path")
                    if val:
                        parts.extend(str(val).split(os.pathsep))
                except OSError:
                    pass
        except Exception:
            pass
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            parts.extend(
                [
                    os.path.join(local, "Python", "bin"),
                    os.path.join(local, "Programs", "Python", "Launcher"),
                    os.path.join(local, "Microsoft", "WindowsApps"),
                ]
            )
        parts.extend(
            [
                r"C:\Windows\System32",
                r"C:\Windows\System32\WindowsPowerShell\v1.0",
            ]
        )
    # Dedupe preserving order
    seen = set()
    out: List[str] = []
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return os.pathsep.join(out)



class ProgressLogPanel(QWidget):
    """Embeddable log + status that runs a command via QProcess."""

    finished = pyqtSignal(int)  # exit code

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._exit_code = 1
        self._line_buf = ""
        self._running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.title_lbl = QLabel("Progress")
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        self.title_lbl.setFont(f)
        self.title_lbl.setStyleSheet("color: #FF9800;")
        layout.addWidget(self.title_lbl)

        self.status = QLabel("Idle")
        self.status.setStyleSheet("color: #90CAF9;")
        layout.addWidget(self.status)

        from spock_shell.busy_ui import make_progress_bar

        self.progress_bar = make_progress_bar()
        layout.addWidget(self.progress_bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.log.setStyleSheet(
            "QPlainTextEdit {"
            " background:#1E1E1E; color:#E0E0E0;"
            " border:1px solid #444; border-radius:4px;"
            " padding:8px; font-family: Consolas, 'Courier New', monospace;"
            " font-size: 11pt;"
            "}"
        )
        layout.addWidget(self.log, stretch=1)

        row = QHBoxLayout()
        self.exit_lbl = QLabel("")
        row.addWidget(self.exit_lbl, stretch=1)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        row.addWidget(self.stop_btn)
        layout.addLayout(row)

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_ready)
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)

    @property
    def exit_code(self) -> int:
        return self._exit_code

    @property
    def is_running(self) -> bool:
        return self._running

    def clear_log(self) -> None:
        self.log.clear()
        self.exit_lbl.setText("")
        self.status.setText("Idle")
        self.status.setStyleSheet("color: #90CAF9;")
        from spock_shell.busy_ui import set_busy

        set_busy(self.progress_bar, False)

    def append_line(self, text: str) -> None:
        if not text.endswith("\n"):
            text = text + "\n"
        self._append_text(text)

    def start(
        self,
        *,
        title: str,
        command: List[str],
        cwd: Path,
    ) -> bool:
        """Start a command. Returns False if already running or command empty."""
        if self._running:
            return False
        if not command:
            self._append_text("No command specified.\n")
            self._finish_ui(2)
            self.finished.emit(2)
            return False

        self.title_lbl.setText(title or "Progress")
        self._exit_code = 1
        self._line_buf = ""
        self._running = True
        self.stop_btn.setEnabled(True)
        self.exit_lbl.setText("")

        self.proc.setWorkingDirectory(str(cwd))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONPATH", str(cwd) + os.pathsep + env.value("PYTHONPATH", ""))
        env.insert("PATH", _enriched_path())
        env.insert("Path", env.value("PATH"))
        self.proc.setProcessEnvironment(env)

        self._append_text(f"$ {' '.join(command)}\n\n")
        self.status.setText("Running...")
        self.status.setStyleSheet("color: #90CAF9;")
        from spock_shell.busy_ui import set_busy

        set_busy(self.progress_bar, True)
        self.proc.start(command[0], command[1:])
        if not self.proc.waitForStarted(8000):
            self._append_text(f"Failed to start: {command[0]}\n")
            self._finish_ui(2)
            self.finished.emit(2)
            return False
        return True

    def stop(self) -> None:
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()
            self.proc.waitForFinished(3000)

    def _on_ready(self) -> None:
        raw = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not raw:
            return
        self._line_buf += raw.replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in self._line_buf:
            line, self._line_buf = self._line_buf.split("\n", 1)
            self._append_text(line + "\n")

    def _on_finished(self, code: int, _status) -> None:
        if self._line_buf:
            self._append_text(self._line_buf)
            self._line_buf = ""
        self._finish_ui(int(code))
        self.finished.emit(int(code))

    def _on_error(self, error) -> None:
        self._append_text(f"\n[process error] {error}\n")

    def _append_text(self, text: str) -> None:
        self.log.moveCursor(QTextCursor.MoveOperation.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.MoveOperation.End)
        self.log.ensureCursorVisible()

    def _finish_ui(self, code: int) -> None:
        self._exit_code = code
        self._running = False
        self.stop_btn.setEnabled(False)
        from spock_shell.busy_ui import set_busy

        set_busy(self.progress_bar, False)
        if code == 0:
            self.status.setText("Finished OK")
            self.status.setStyleSheet("color: #81C784;")
            self.exit_lbl.setText("exit: 0")
        else:
            self.status.setText("Finished with errors")
            self.status.setStyleSheet("color: #E57373;")
            self.exit_lbl.setText(f"exit: {code}")
