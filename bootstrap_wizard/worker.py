"""Run bootstrap.ps1 with -EmitEvents and stream JSONL / log lines."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal


class BootstrapRunner(QThread):
    """Spawn powershell bootstrap.ps1; emit parsed events + raw lines."""

    line_read = pyqtSignal(str)
    event_received = pyqtSignal(dict)
    finished_rc = pyqtSignal(int)

    def __init__(
        self,
        install_root: Path,
        *,
        only_step: str = "",
        from_step: str = "",
        heavy_deps: bool = False,
        validate: bool = False,
        skip_wizard: bool = True,
        extra_args: Optional[List[str]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.install_root = Path(install_root)
        self.only_step = only_step
        self.from_step = from_step
        self.heavy_deps = heavy_deps
        self.validate = validate
        self.skip_wizard = skip_wizard
        self.extra_args = list(extra_args or [])
        self._proc: Optional[subprocess.Popen] = None
        self._running = True

    def stop(self) -> None:
        self._running = False
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass

    def run(self) -> None:
        ps1 = self.install_root / "bootstrap.ps1"
        if not ps1.is_file():
            self.line_read.emit(f"ERROR: missing {ps1}")
            self.finished_rc.emit(1)
            return

        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1),
            "-NonInteractive",
            "-EmitEvents",
            "-NoHandOffGui",
            "-InstallRoot",
            str(self.install_root),
            "-SkipAcquire",
        ]
        if self.skip_wizard:
            args.append("-SkipWizard")
        if self.heavy_deps:
            args.append("-HeavyDeps")
        else:
            args.append("-SkipHeavyDeps")
        if self.validate:
            args.append("-Validate")
        else:
            args.append("-SkipValidate")
        if self.only_step:
            args.extend(["-OnlyStep", self.only_step])
        if self.from_step:
            args.extend(["-FromStep", self.from_step])
        args.extend(self.extra_args)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            self._proc = subprocess.Popen(
                args,
                cwd=str(self.install_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
        except OSError as e:
            self.line_read.emit(f"ERROR: failed to start powershell: {e}")
            self.finished_rc.emit(1)
            return

        assert self._proc.stdout is not None
        stream = io.TextIOWrapper(
            self._proc.stdout, encoding="utf-8", errors="replace"
        )
        try:
            while self._running:
                line = stream.readline()
                if not line:
                    break
                text = line.rstrip("\n\r")
                self.line_read.emit(text)
                if text.startswith("{") and '"event"' in text:
                    try:
                        payload = json.loads(text)
                        if isinstance(payload, dict):
                            self.event_received.emit(payload)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            self.line_read.emit(f"[reader] {e}")
        finally:
            try:
                rc = self._proc.wait(timeout=5)
            except Exception:
                rc = self._proc.poll()
                if rc is None:
                    rc = -1
            self.finished_rc.emit(int(rc if rc is not None else -1))
