"""Wiki Agent run panel — stream wiki_agent.py (daemon) without freezing Qt."""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from typing import Any, Dict, Optional

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spock_shell.paths import ROOT, SHIP_COMPUTER_DB

# CSI / OSC style ANSI sequences from wiki_agent.console()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?\x07|\x1b\[[\?][0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _styled_btn(text: str, bg: str, fg: str = "#FFFFFF") -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(
        f"QPushButton {{ background:{bg}; color:{fg}; padding:10px 16px; "
        f"border:none; border-radius:4px; font-weight:bold; }}"
        f"QPushButton:disabled {{ background:#555; color:#999; }}"
    )
    return btn


class ProcessOutputReader(QThread):
    """Reads subprocess stdout line-by-line on a worker thread."""

    line_read = pyqtSignal(str)
    finished_rc = pyqtSignal(int)

    def __init__(self, process: subprocess.Popen, parent=None):
        super().__init__(parent)
        self.process = process
        self._running = True

    def run(self) -> None:
        assert self.process.stdout is not None
        stream = io.TextIOWrapper(
            self.process.stdout, encoding="utf-8", errors="replace"
        )
        try:
            while self._running:
                line = stream.readline()
                if not line:
                    break
                self.line_read.emit(strip_ansi(line.rstrip("\n")))
        except Exception as e:
            self.line_read.emit(f"[reader] {e}")
        finally:
            try:
                rc = self.process.wait(timeout=2)
            except Exception:
                rc = self.process.poll()
                if rc is None:
                    rc = -1
            self.finished_rc.emit(int(rc if rc is not None else -1))

    def stop(self) -> None:
        self._running = False


def _embedding_env(config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    env = os.environ.copy()
    config = config or {}
    try:
        from model_selector_core import merge_embedding_profile, write_embedding_env

        profile = merge_embedding_profile(config.get("embedding_profile"))
        emb_url = profile.get("embeddings_url", "http://localhost:8080/embeddings")
        env["EMBEDDINGS_URL"] = str(emb_url)
        env["EMBEDDINGS_DIM"] = str(profile.get("embeddings_dim", 4096))
        env["EMBEDDINGS_TRUNCATE"] = str(profile.get("truncate_chars", 1500))
        env["EMBEDDINGS_BATCH_CHUNK"] = str(profile.get("batch_chunk", 32))
        env["EMBEDDINGS_BATCH_WORKERS"] = str(profile.get("batch_workers", 8))
        write_embedding_env(profile)
        if profile.get("model_path"):
            env["SPOCK_EMBED_MODEL_PATH"] = str(profile.get("model_path") or "")
        if profile.get("model_id"):
            env["SPOCK_EMBED_MODEL_ID"] = str(profile.get("model_id") or "")
    except Exception:
        env.setdefault("EMBEDDINGS_URL", "http://localhost:8080/embeddings")
    env.setdefault("WIKI_AGENT_EXTENSIONS", "all")
    env["PYTHONUNBUFFERED"] = "1"
    # Prefer plain text if the agent ever respects these.
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    return env


def _show_output_dialog(parent: QWidget, title: str, text: str) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumSize(750, 500)
    dlg.setModal(True)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(10, 10, 10, 10)
    viewer = QTextEdit()
    viewer.setReadOnly(True)
    viewer.setFont(QFont("Consolas", 10))
    viewer.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
    viewer.setPlainText(text)
    layout.addWidget(viewer)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    copy_btn = QPushButton("Copy")
    copy_btn.setMinimumWidth(70)
    copy_btn.clicked.connect(
        lambda: QApplication.clipboard().setText(text)  # type: ignore[arg-type]
    )
    btn_row.addWidget(copy_btn)
    close_btn = QPushButton("Close")
    close_btn.setMinimumWidth(70)
    close_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)
    dlg.exec()


def build_wiki_agent_run_panel(
    theme: Dict[str, str],
    *,
    config: Optional[Dict[str, Any]] = None,
    title: str = "4 Run Wiki Scan",
    source_label: str = "Science Station",
) -> QWidget:
    """Center pane: Run Wiki Scan / Stop Scan + Embedding Status + live log.

    ``title``/``source_label`` let other mini-apps host this step under their
    own step number without forking the panel.
    """
    wrap = QWidget()
    lay = QVBoxLayout(wrap)

    title_lbl = QLabel(title)
    title_lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
    lay.addWidget(title_lbl)

    # Controls at top of middle pane
    row = QHBoxLayout()
    run_btn = _styled_btn("Run Wiki Scan", "#5C6BC0")
    stop_btn = _styled_btn("Stop Scan", "#C44A4A")
    stop_btn.setEnabled(False)
    status_btn = _styled_btn("Embedding Status", "#6D9E5A")
    status_btn.setToolTip(
        "Run wiki_agent_status.py (ingest queue / embed progress) — "
        "same as Ship Status → Live Monitor → Embedding Status"
    )
    clear_emb_btn = _styled_btn("Clear Embeddings (re-embed)", "#C44A4A")
    clear_emb_btn.setToolTip(
        "Same as Engineering Maintenance → Database → Clear Embeddings (re-embed).\n"
        "Nulls document vectors and clears kb_embedding_corpus; keeps documents.\n"
        "Then launch the new GGUF on :8080 and Run Wiki Scan."
    )
    scan_roots_btn = _styled_btn("Run Update Scan Roots", "#00897B")
    scan_roots_btn.setToolTip(
        "Add or remove folders that Wiki Agent / ingest should scan "
        "(same as Engineering Maintenance → Scan Roots)."
    )
    list_roots_btn = _styled_btn("Run List Roots", "#00897B")
    list_roots_btn.setToolTip(
        "Show configured scan roots (same list as Update Scan Roots), "
        "with document counts under each root."
    )
    row.addWidget(run_btn)
    row.addWidget(stop_btn)
    row.addWidget(status_btn)
    row.addWidget(clear_emb_btn)
    row.addWidget(scan_roots_btn)
    row.addWidget(list_roots_btn)
    row.addStretch()
    lay.addLayout(row)

    continuous = QCheckBox("Continuous watch (until Stop Scan)")
    continuous.setChecked(False)
    continuous.setToolTip(
        "Off (default): scan once — bootstrap + ingest + update_index, then exit "
        "when the queue is empty (no need to click Stop Scan).\n"
        "On: keep the file watcher running and print STATUS until you click Stop Scan."
    )
    lay.addWidget(continuous)

    tip = QLabel(
        "Starts <code>wiki_agent.py</code>. "
        "Default is <b>scan once</b> (auto-exits when idle so you know it finished). "
        "Check <b>Continuous watch</b> to keep indexing new/changed files until "
        "<b>Stop Scan</b>. Needs embeddings at the configured embed port."
    )
    tip.setWordWrap(True)
    tip.setTextFormat(Qt.TextFormat.RichText)
    lay.addWidget(tip)

    from spock_shell.busy_ui import make_progress_bar, set_busy

    progress = make_progress_bar()
    lay.addWidget(progress)

    status = QLabel("Idle")
    status.setStyleSheet("font-weight: bold;")
    lay.addWidget(status)

    log = QTextEdit()
    log.setReadOnly(True)
    log.setFont(QFont("Consolas", 10))
    log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
    log.setStyleSheet(
        "QTextEdit { background:#1a1a1a; color:#e8e8e8; "
        "border:1px solid #444; border-radius:4px; padding:8px; }"
    )
    lay.addWidget(log, 1)

    state: Dict[str, Any] = {"process": None, "reader": None, "once": True}

    def _append(line: str) -> None:
        clean = strip_ansi(line)
        if not clean and line:
            return
        log.append(clean)
        sb = log.verticalScrollBar()
        sb.setValue(sb.maximum())
        if "SCAN_COMPLETE" in clean:
            status.setText("Scan complete — finishing…")

    def _on_done(rc: int) -> None:
        if state.get("once") and rc == 0:
            status.setText("Scan complete")
        elif state.get("once") and rc != 0:
            status.setText(f"Scan ended (exit {rc})")
        else:
            status.setText(f"Stopped (exit {rc})")
        run_btn.setEnabled(True)
        stop_btn.setEnabled(False)
        continuous.setEnabled(True)
        state["process"] = None
        state["reader"] = None
        set_busy(progress, False)

    def _stop() -> None:
        reader = state.get("reader")
        proc = state.get("process")
        if reader is not None:
            reader.stop()
        pid = None
        if proc is not None and proc.poll() is None:
            try:
                pid = int(proc.pid)
            except (TypeError, ValueError, AttributeError):
                pid = None
        from spock_shell.process_tree import stop_wiki_scan

        info = stop_wiki_scan(
            ROOT,
            proc_pid=pid,
            db_path=SHIP_COMPUTER_DB,
        )
        n = len(info.get("killed_pids") or [])
        q = int(info.get("queue_cancelled") or 0)
        _append(
            f"[{source_label}] Wiki scan stopped "
            f"(killed {n} process tree(s), cancelled {q} queue job(s))."
        )
        state["process"] = None
        state["reader"] = None
        run_btn.setEnabled(True)
        stop_btn.setEnabled(False)
        continuous.setEnabled(True)
        status.setText("Stopped")
        set_busy(progress, False)
        from spock_shell.busy_ui import clear_override_cursors

        clear_override_cursors()

    def _run() -> None:
        if state.get("process") is not None and state["process"].poll() is None:
            QMessageBox.information(
                wrap, "Wiki Scan", "Already running — use Stop Scan first."
            )
            return
        script = ROOT / "wiki_agent.py"
        py = ROOT / ".venv" / "Scripts" / "python.exe"
        exe = str(py) if py.is_file() else sys.executable
        if not script.is_file():
            QMessageBox.warning(wrap, "Wiki Scan", f"Missing {script}")
            return

        env = _embedding_env(config)
        emb = env.get("EMBEDDINGS_URL", "")
        once = not continuous.isChecked()
        state["once"] = once
        mode_flag = "--once" if once else "--continuous"
        try:
            from spock_shell.embedding_corpus import record_from_live_server

            profile = {}
            try:
                from model_selector_core import merge_embedding_profile

                profile = merge_embedding_profile((config or {}).get("embedding_profile"))
            except Exception:
                profile = {}
            ok, msg, row = record_from_live_server(
                emb or "http://localhost:8080/embeddings",
                embeddings_dim=int(profile.get("embeddings_dim") or env.get("EMBEDDINGS_DIM") or 4096),
                model_id=str(profile.get("model_id") or ""),
            )
            if not ok:
                QMessageBox.warning(wrap, "Wiki Scan", msg)
                return
            live_path = str((row or {}).get("model_path") or "")
            if live_path:
                env["SPOCK_EMBED_MODEL_PATH"] = live_path
            log.clear()
            _append(f"$ {exe} -u {script} {mode_flag}")
            _append(f"EMBEDDINGS_URL={emb}")
            _append(f"Embedding GGUF: {(row or {}).get('model_name') or live_path or '—'}")
            _append(msg)
            if once:
                _append(
                    "(scan-once — exits when queue is idle after bootstrap + update_index)\n"
                )
            else:
                _append(
                    "(continuous watch — STATUS while idle; use Stop Scan to exit)\n"
                )
        except Exception as e:
            QMessageBox.warning(
                wrap,
                "Wiki Scan",
                f"Could not record the live embedding model:\n{e}",
            )
            return

        try:
            proc = subprocess.Popen(
                [exe, "-u", str(script), mode_flag],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                bufsize=0,
            )
        except Exception as e:
            QMessageBox.critical(wrap, "Wiki Scan", str(e))
            return

        state["process"] = proc
        reader = ProcessOutputReader(proc, wrap)
        reader.line_read.connect(_append)
        reader.finished_rc.connect(_on_done)
        state["reader"] = reader
        reader.start()
        mode_lbl = "scan-once" if once else "continuous"
        status.setText(f"Running ({mode_lbl}, PID {proc.pid}) · {emb}")
        run_btn.setEnabled(False)
        stop_btn.setEnabled(True)
        continuous.setEnabled(False)
        set_busy(progress, True)

    def _embedding_status() -> None:
        script = ROOT / "wiki_agent_status.py"
        if not script.is_file():
            QMessageBox.warning(wrap, "Embedding Status", f"Not found: {script}")
            return
        py = ROOT / ".venv" / "Scripts" / "python.exe"
        exe = str(py) if py.is_file() else sys.executable
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = subprocess.run(
                [exe, str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                cwd=str(ROOT),
                env=_embedding_env(config),
            )
            output = (result.stdout or "") + (
                f"\n{result.stderr}" if result.stderr else ""
            )
            _show_output_dialog(
                wrap,
                "Embedding Status (wiki_agent_status.py)",
                strip_ansi(output.strip() or "(no output)"),
            )
        except subprocess.TimeoutExpired:
            QMessageBox.warning(
                wrap, "Timeout", "wiki_agent_status.py timed out after 120s"
            )
        except Exception as e:
            QMessageBox.warning(wrap, "Embedding Status", str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def _update_scan_roots() -> None:
        from wiki_maintenance import ScanRootsDialog

        dialog = ScanRootsDialog(theme or {}, parent=wrap)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            status.setText("Scan roots updated")
            _append("[Scan Roots] Updated scan roots (saved to Spock Console / scan_config.json).")

    def _list_roots() -> None:
        try:
            from db_maintenance import format_configured_scan_roots

            text = format_configured_scan_roots(SHIP_COMPUTER_DB)
        except Exception as e:
            QMessageBox.warning(wrap, "List Roots", str(e))
            return
        QMessageBox.information(wrap, "Scan Roots", text)
        _append("[Scan Roots] Listed configured scan roots.")

    def _clear_embeddings() -> None:
        proc = state.get("process")
        if proc is not None and proc.poll() is None:
            QMessageBox.information(
                wrap,
                "Clear Embeddings",
                "Stop the running Wiki Scan first, then clear embeddings.",
            )
            return
        reply = QMessageBox.question(
            wrap,
            "Clear Embeddings (re-embed)",
            "Clear all document embeddings and kb_embedding_corpus?\n\n"
            "This keeps documents, settings, and profiles.\n"
            "It does NOT wipe captains_log / queue (unlike Reset content).\n\n"
            "Afterward: launch the new embedding GGUF on :8080, then Run Wiki Scan.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            status.setText("Clear embeddings cancelled")
            return
        from spock_shell.busy_ui import busy_scope, clear_override_cursors

        try:
            from spock_rag_adapter.reembed import clear_embeddings, format_clear_result

            with busy_scope(wrap, "Clearing embeddings…"):
                result = clear_embeddings(SHIP_COMPUTER_DB)
            clear_override_cursors()
            _show_output_dialog(
                wrap, "Clear Embeddings (re-embed)", format_clear_result(result)
            )
            status.setText(
                f"Cleared embeddings "
                f"({result.get('embeddings_before')} → {result.get('embeddings_after')})"
            )
            _append(
                f"[Clear Embeddings] {result.get('embeddings_before')} → "
                f"{result.get('embeddings_after')} "
                f"(docs kept: {result.get('documents_total')})"
            )
        except Exception as e:
            clear_override_cursors()
            QMessageBox.warning(wrap, "Clear Embeddings", str(e))
            status.setText(f"Clear embeddings error: {e}")

    run_btn.clicked.connect(_run)
    stop_btn.clicked.connect(_stop)
    status_btn.clicked.connect(_embedding_status)
    clear_emb_btn.clicked.connect(_clear_embeddings)
    scan_roots_btn.clicked.connect(_update_scan_roots)
    list_roots_btn.clicked.connect(_list_roots)

    wrap._run = _run  # type: ignore[attr-defined]
    wrap._stop = _stop  # type: ignore[attr-defined]
    wrap._status = status  # type: ignore[attr-defined]
    wrap._log = log  # type: ignore[attr-defined]
    wrap._state = state  # type: ignore[attr-defined]
    return wrap
