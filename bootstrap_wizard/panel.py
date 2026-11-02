"""Center panel: step checklist, progress bar, live log, action buttons."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bootstrap_wizard.steps import ALL_STEPS, FULL_DEPS_MARKER, PHASE_A_STEPS
from bootstrap_wizard.worker import BootstrapRunner


def _btn(text: str, color: str) -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(
        f"QPushButton {{ background:{color}; color:#fff; padding:8px 14px; "
        f"border:none; border-radius:4px; font-weight:bold; }}"
        f"QPushButton:disabled {{ background:#555; color:#999; }}"
    )
    return b


class BootstrapControlPanel(QWidget):
    """Progress + live log control surface for bootstrap.ps1."""

    def __init__(
        self,
        install_root: Path,
        theme: Optional[dict] = None,
        parent=None,
        *,
        on_busy: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__(parent)
        self.install_root = Path(install_root)
        self.theme = theme or {}
        self._on_busy = on_busy
        self._runner: Optional[BootstrapRunner] = None
        self._status: Dict[str, str] = {sid: "pending" for sid, _ in ALL_STEPS}
        self._failed_step: Optional[str] = None
        self._build()
        self._refresh_checklist()
        self._detect_phase_a_done()
        self._detect_full_deps()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        title = QLabel("Bootstrap Control — progress, live log, status")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lay.addWidget(title)

        tip = QLabel(
            f"Install root: {self.install_root}\n"
            "Phase A (Python/venv/light PyQt) usually already finished in the console.\n"
            "Required next: full requirements.txt (includes torch) — Science Station will "
            "not work without it. Then: Launch First Models → Onboarding."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        lay.addWidget(self.progress)

        self.checklist = QListWidget()
        self.checklist.setMinimumHeight(180)
        lay.addWidget(self.checklist)

        self.deps_banner = QLabel()
        self.deps_banner.setWordWrap(True)
        lay.addWidget(self.deps_banner)

        opts = QHBoxLayout()
        self.chk_heavy = QCheckBox(
            "Install full requirements.txt (torch… — required for Science Station)"
        )
        self.chk_heavy.setChecked(True)
        self.chk_validate = QCheckBox("Run health check after")
        self.chk_validate.setChecked(True)
        opts.addWidget(self.chk_heavy)
        opts.addWidget(self.chk_validate)
        opts.addStretch(1)
        lay.addLayout(opts)

        row = QHBoxLayout()
        self.btn_remaining = _btn("Start full install + health", "#1565C0")
        self.btn_remaining.clicked.connect(self._start_remaining)
        self.btn_retry = _btn("Retry failed step", "#FF9800")
        self.btn_retry.clicked.connect(self._retry_failed)
        self.btn_retry.setEnabled(False)
        self.btn_first = _btn("Launch First Models", "#FF9800")
        self.btn_first.clicked.connect(self._launch_first_models)
        self.btn_onboard = _btn("Launch Onboarding Wizard", "#00897B")
        self.btn_onboard.clicked.connect(self._launch_onboarding)
        self.btn_health = _btn("Run health check", "#5C6BC0")
        self.btn_health.clicked.connect(self._run_health)
        self.btn_log = _btn("Open bootstrap.log", "#6D9E5A")
        self.btn_log.clicked.connect(self._open_log)
        for b in (
            self.btn_remaining,
            self.btn_retry,
            self.btn_first,
            self.btn_onboard,
            self.btn_health,
            self.btn_log,
        ):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 10))
        self.log.setMinimumHeight(280)
        self.log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        lay.addWidget(self.log, 1)
        self._refresh_deps_banner()

    def _marker_path(self) -> Path:
        return self.install_root / FULL_DEPS_MARKER

    def _full_deps_ok(self) -> bool:
        return self._status.get("pip_full") == "ok"

    def _probe_torch_installed(self) -> bool:
        """True if venv can import torch (Science Station baseline)."""
        py = self._venv_python()
        try:
            r = subprocess.run(
                [
                    py,
                    "-c",
                    "import torch; print(getattr(torch, '__version__', 'ok'))",
                ],
                cwd=str(self.install_root),
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return r.returncode == 0 and bool((r.stdout or "").strip())
        except (OSError, subprocess.TimeoutExpired):
            return False

    def mark_full_deps_ok(self, *, source: str = "phase_b") -> None:
        """Record successful full requirements install (UI + marker file)."""
        self._status["pip_full"] = "ok"
        if self._status.get("validate") == "pending":
            # leave validate unless health file exists
            health = self.install_root / "bootstrap_health_last.txt"
            if health.is_file():
                self._status["validate"] = "ok"
        try:
            self._marker_path().write_text(
                f"ok\nsource={source}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        self.progress.setValue(max(self.progress.value(), 92))
        self._refresh_checklist()
        self._refresh_deps_banner()
        self._append_log("INFO", f"Full requirements marked complete ({source}).")

    def _detect_full_deps(self) -> None:
        if self._marker_path().is_file():
            self._status["pip_full"] = "ok"
            self._append_log(
                "INFO",
                f"Found {FULL_DEPS_MARKER} — full requirements already completed.",
            )
        elif self._probe_torch_installed():
            self.mark_full_deps_ok(source="torch_import_probe")
            return
        else:
            self._append_log(
                "WARN",
                "Full requirements (torch) not detected yet. "
                "Run “Start full install + health” before Science Station.",
            )
        health = self.install_root / "bootstrap_health_last.txt"
        if health.is_file() and self._status.get("pip_full") == "ok":
            self._status["validate"] = "ok"
            self.progress.setValue(max(self.progress.value(), 95))
        self._refresh_checklist()
        self._refresh_deps_banner()

    def _refresh_deps_banner(self) -> None:
        if not hasattr(self, "deps_banner"):
            return
        if self._full_deps_ok():
            self.deps_banner.setText(
                "✓ Full requirements (torch) detected — Science Station deps look ready."
            )
            self.deps_banner.setStyleSheet(
                "QLabel { background:#1b5e20; color:#e8f5e9; padding:8px; border-radius:4px; }"
            )
            self.chk_heavy.setChecked(False)
            self.btn_remaining.setText("Re-run full install / health")
        else:
            self.deps_banner.setText(
                "⚠ Full requirements NOT complete — Science Station needs torch. "
                "Leave the checkbox checked and click “Start full install + health” "
                "(runs in a detached console, then reopens this window)."
            )
            self.deps_banner.setStyleSheet(
                "QLabel { background:#5d4037; color:#fff3e0; padding:8px; "
                "border-radius:4px; font-weight:bold; }"
            )
            self.chk_heavy.setChecked(True)
            self.btn_remaining.setText("Start full install + health")

    def _confirm_proceed_without_full_deps(self, destination: str) -> bool:
        """Gate First Models / Onboarding if torch/full pip missing."""
        if self._full_deps_ok():
            return True
        # Re-probe in case user installed outside this session
        if self._probe_torch_installed():
            self.mark_full_deps_ok(source="torch_import_probe")
            return True

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Full requirements still required")
        msg.setText(
            f"Full requirements.txt (including torch) is not installed yet.\n\n"
            f"Science Station and several suite tools will fail without it.\n"
            f"You asked to open: {destination}\n\n"
            f"Recommended: install full requirements now (detached console, ~several minutes)."
        )
        install_btn = msg.addButton(
            "Install full requirements now",
            QMessageBox.ButtonRole.AcceptRole,
        )
        continue_btn = msg.addButton(
            "Continue anyway (not recommended)",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(install_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == install_btn:
            self.chk_heavy.setChecked(True)
            self.chk_validate.setChecked(True)
            self._start_remaining()
            return False
        if clicked == continue_btn:
            self._append_log(
                "WARN",
                f"User continued to {destination} without full requirements (torch).",
            )
            return True
        return False

    def _detect_phase_a_done(self) -> None:
        venv_py = self.install_root / ".venv" / "Scripts" / "python.exe"
        if venv_py.is_file():
            for sid, _ in PHASE_A_STEPS:
                self._status[sid] = "ok"
            self.progress.setValue(70)
            self._append_log(
                "INFO",
                "Detected existing .venv — Phase A steps marked complete.",
            )
        self._refresh_checklist()

    def _refresh_checklist(self) -> None:
        self.checklist.clear()
        icons = {
            "pending": "○",
            "running": "●",
            "ok": "✓",
            "failed": "✗",
            "skipped": "–",
        }
        for sid, title in ALL_STEPS:
            st = self._status.get(sid, "pending")
            item = QListWidgetItem(f"{icons.get(st, '?')}  {title}  [{sid}]  ({st})")
            self.checklist.addItem(item)

    def _set_busy(self, busy: bool) -> None:
        for b in (
            self.btn_remaining,
            self.btn_retry,
            self.btn_first,
            self.btn_onboard,
            self.btn_health,
        ):
            b.setEnabled(not busy)
        if not busy:
            self.btn_retry.setEnabled(bool(self._failed_step))
        if self._on_busy:
            self._on_busy(busy)

    def _append_log(self, level: str, message: str) -> None:
        fmt = QTextCharFormat()
        color = {
            "ERROR": "#ff8a80",
            "WARN": "#ffd54f",
            "INFO": "#e0e0e0",
        }.get(level.upper(), "#e0e0e0")
        fmt.setForeground(QColor(color))
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"[{level}] {message}\n", fmt)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()

    def _on_line(self, line: str) -> None:
        if line.startswith("{") and '"event"' in line:
            return  # shown via event handler
        # Human Write-Host / Write-Log lines
        level = "INFO"
        if "[ERROR]" in line:
            level = "ERROR"
        elif "[WARN]" in line:
            level = "WARN"
        self._append_log(level, line)

    def _on_event(self, ev: dict) -> None:
        et = str(ev.get("event") or "")
        if et == "step_start":
            sid = str(ev.get("id") or "")
            if sid in self._status:
                self._status[sid] = "running"
                self._refresh_checklist()
            title = ev.get("title") or sid
            self._append_log("INFO", f"STEP START: {title}")
        elif et == "step_end":
            sid = str(ev.get("id") or "")
            ok = bool(ev.get("ok"))
            if sid in self._status:
                self._status[sid] = "ok" if ok else "failed"
                self._refresh_checklist()
            if not ok:
                self._failed_step = sid
                self.btn_retry.setEnabled(True)
            self._append_log(
                "INFO" if ok else "ERROR",
                f"STEP END: {sid} → {'ok' if ok else 'failed'}",
            )
        elif et == "progress":
            try:
                self.progress.setValue(int(ev.get("percent") or 0))
            except (TypeError, ValueError):
                pass
        elif et == "log":
            self._append_log(
                str(ev.get("level") or "INFO"),
                str(ev.get("message") or ""),
            )
        elif et == "error":
            self._failed_step = str(ev.get("id") or self._failed_step or "")
            self._append_log("ERROR", str(ev.get("message") or "error"))
        elif et == "done":
            self._append_log("INFO", f"DONE: {ev}")

    def _on_finished(self, rc: int) -> None:
        self._runner = None
        self._set_busy(False)
        self._append_log(
            "INFO" if rc == 0 else "WARN",
            f"bootstrap.ps1 exited with code {rc}",
        )
        # Persist a short completion banner in the log (window stays open).
        if rc == 0:
            self._append_log(
                "INFO",
                "=== Run finished. Review the log above; this window stays open. ===",
            )
            health = self.install_root / "bootstrap_health_last.txt"
            if health.is_file():
                self._append_log("INFO", f"Health report file: {health}")
                try:
                    for line in health.read_text(encoding="utf-8", errors="replace").splitlines()[:40]:
                        self._append_log("INFO", line)
                except OSError:
                    pass
            QMessageBox.information(
                self,
                "Bootstrap step finished",
                "The requested bootstrap step finished.\n"
                "This window stays open so you can review the live log.\n\n"
                f"Exit code: {rc}\nLog: {self.install_root / 'bootstrap.log'}",
            )
        else:
            QMessageBox.warning(
                self,
                "Bootstrap step failed",
                f"bootstrap.ps1 exited with code {rc}.\n"
                "See the live log and bootstrap.log. Use Retry if a step failed.",
            )

    def _start_runner(self, **kwargs) -> None:
        if self._runner and self._runner.isRunning():
            QMessageBox.information(self, "Busy", "A bootstrap run is already in progress.")
            return
        self._set_busy(True)
        self._runner = BootstrapRunner(self.install_root, **kwargs)
        self._runner.line_read.connect(self._on_line)
        self._runner.event_received.connect(self._on_event)
        self._runner.finished_rc.connect(self._on_finished)
        self._runner.start()

    def _start_remaining(self) -> None:
        self._failed_step = None
        heavy = self.chk_heavy.isChecked()
        validate = self.chk_validate.isChecked()
        if not heavy and not validate:
            if not self._full_deps_ok():
                QMessageBox.warning(
                    self,
                    "Full install required",
                    "Science Station needs full requirements.txt (torch).\n\n"
                    "Check “Install full requirements…” and click "
                    "“Start full install + health”.",
                )
                self.chk_heavy.setChecked(True)
                return
            QMessageBox.information(
                self,
                "Nothing selected",
                "Check 'Install full requirements' and/or 'Run health check', "
                "or use Launch First Models / Onboarding when ready.",
            )
            return

        if not heavy and not self._full_deps_ok():
            reply = QMessageBox.question(
                self,
                "Skip full requirements?",
                "You unchecked full requirements, but torch is not installed yet.\n\n"
                "Science Station will not work without the full install.\n\n"
                "Install full requirements now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.chk_heavy.setChecked(True)
                heavy = True
            else:
                self._append_log(
                    "WARN",
                    "User skipped full requirements — health-only run.",
                )

        # Full requirements reinstalls PyQt/torch into the same venv that is
        # running this GUI — that kills the window mid-flight. Run detached.
        if heavy:
            self._start_detached_phase_b(heavy=True, validate=validate)
            return

        # Health-only: safe to run in-process under the GUI.
        self._start_runner(
            from_step="validate",
            heavy_deps=False,
            validate=True,
            skip_wizard=True,
        )

    def _start_detached_phase_b(self, *, heavy: bool, validate: bool) -> None:
        job = self.install_root / "bootstrap_phase_b_job.ps1"
        if not job.is_file():
            QMessageBox.warning(
                self,
                "Missing job script",
                f"Not found:\n{job}\n\nPull latest cursor/nav-station-suite-ux.",
            )
            return
        reply = QMessageBox.question(
            self,
            "Install full requirements (required)",
            "Full requirements install (torch + the rest of requirements.txt) is "
            "required for Science Station.\n\n"
            "It reinstalls packages (including PyQt) in this venv, so this window "
            "will close. A console job will run pip"
            + (" + health check" if validate else "")
            + ", then reopen this wizard with a summary.\n\n"
            "Typical time: several minutes. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(job),
            "-InstallRoot",
            str(self.install_root),
        ]
        if heavy:
            args.append("-HeavyDeps")
        if validate:
            args.append("-Validate")

        try:
            subprocess.Popen(
                args,
                cwd=str(self.install_root),
                env=os.environ.copy(),
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        except OSError as e:
            QMessageBox.warning(self, "Launch failed", str(e))
            return

        self._append_log(
            "INFO",
            "Detached Phase B full-install job started; closing this window.",
        )
        # Quit so pip can safely replace packages in this venv.
        app = QApplication.instance()
        win = self.window()
        if win is not None:
            win.close()
        if app is not None:
            app.quit()

    def _retry_failed(self) -> None:
        if not self._failed_step:
            return
        sid = self._failed_step
        self._status[sid] = "pending"
        self._refresh_checklist()
        kwargs = {
            "only_step": sid,
            "skip_wizard": True,
            "heavy_deps": sid == "pip_full",
            "validate": sid == "validate",
        }
        self._start_runner(**kwargs)

    def _venv_python(self) -> str:
        p = self.install_root / ".venv" / "Scripts" / "python.exe"
        return str(p) if p.is_file() else sys.executable

    def _launch_first_models(self) -> None:
        if not self._confirm_proceed_without_full_deps("First Models"):
            return
        script = self.install_root / "SpockFirstModels.py"
        if not script.is_file():
            QMessageBox.warning(self, "Missing", f"Not found:\n{script}")
            return
        try:
            subprocess.Popen(
                [self._venv_python(), str(script)],
                cwd=str(self.install_root),
                env=os.environ.copy(),
            )
            self._append_log("INFO", f"Launched {script.name} (pre-Onboarding LLM bootstrap)")
        except OSError as e:
            QMessageBox.warning(self, "Launch failed", str(e))

    def _launch_onboarding(self) -> None:
        if not self._confirm_proceed_without_full_deps("Onboarding Wizard"):
            return
        script = self.install_root / "SpockOnboardingWizard.py"
        if not script.is_file():
            QMessageBox.warning(self, "Missing", f"Not found:\n{script}")
            return
        self._status["onboarding"] = "running"
        self._refresh_checklist()
        try:
            subprocess.Popen(
                [self._venv_python(), str(script)],
                cwd=str(self.install_root),
                env=os.environ.copy(),
            )
            self._status["onboarding"] = "ok"
            self._append_log("INFO", f"Launched {script.name}")
        except OSError as e:
            self._status["onboarding"] = "failed"
            self._failed_step = "onboarding"
            QMessageBox.warning(self, "Launch failed", str(e))
            self._refresh_checklist()
        self._refresh_checklist()

    def _run_health(self) -> None:
        self._status["validate"] = "running"
        self._refresh_checklist()
        self._start_runner(
            only_step="validate",
            validate=True,
            heavy_deps=False,
            skip_wizard=True,
        )

    def _open_log(self) -> None:
        log = self.install_root / "bootstrap.log"
        if not log.is_file():
            # script dir may differ when InstallRoot == clone
            alt = Path(__file__).resolve().parent.parent / "bootstrap.log"
            log = alt if alt.is_file() else log
        if not log.is_file():
            QMessageBox.information(self, "Log", f"No log yet at:\n{log}")
            return
        try:
            os.startfile(str(log))  # type: ignore[attr-defined]
        except OSError as e:
            QMessageBox.warning(self, "Open log", str(e))
