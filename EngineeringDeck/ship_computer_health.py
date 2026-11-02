"""Ship Computer DB Health — Overview + MCP tool probes for Engineering Maintenance."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spock_shell.paths import ROOT, SHIP_COMPUTER_DB


def _load_mcp_module():
    """Load scripts/mcp_spock_server.py without requiring package install."""
    path = ROOT / "scripts" / "mcp_spock_server.py"
    if not path.is_file():
        raise FileNotFoundError(f"Missing MCP server script: {path}")
    spec = importlib.util.spec_from_file_location("mcp_spock_server_tools", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    # Avoid re-running FastMCP registration side effects on every tab refresh
    existing = sys.modules.get("mcp_spock_server_tools")
    if existing is not None:
        return existing
    sys.modules["mcp_spock_server_tools"] = mod
    spec.loader.exec_module(mod)
    return mod


def _call_mcp_tool(name: str, **kwargs: Any) -> Any:
    """Invoke an MCP tool function (FastMCP wraps defs as FunctionTool; use .fn)."""
    mod = _load_mcp_module()
    tool = getattr(mod, name, None)
    if tool is None:
        raise AttributeError(f"MCP tool not found: {name}")
    fn = getattr(tool, "fn", None)
    if callable(fn):
        return fn(**kwargs) if kwargs else fn()
    if callable(tool):
        return tool(**kwargs) if kwargs else tool()
    raise TypeError(f"MCP tool {name!r} is not callable ({type(tool).__name__})")


def _pretty(data: Any) -> str:
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, indent=2, default=str, ensure_ascii=False)
    except Exception:
        return str(data)


class ShipComputerHealthPanel(QWidget):
    """Overview + one tab per MCP ship-computer health tool."""

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.db_path = SHIP_COMPUTER_DB
        self._build()
        self.apply_theme()
        self.refresh_overview()

    def _make_btn(self, text: str, callback, *, kind: str = "run") -> QPushButton:
        btn = QPushButton(text)
        btn.setMinimumHeight(32)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setProperty("maint_kind", "run" if kind == "run" else "accent")
        btn.clicked.connect(callback)
        return btn

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_spock_health_tab(), "spock_health")
        self.tabs.addTab(
            self._build_tool_tab(
                "spock_status",
                "Full Spock status: RAG/llama/MCP health report + hardware ship-status "
                "(same as GUI Run Spock Status / MCP spock-status).",
                self._run_spock_status,
            ),
            "spock_status",
        )
        self.tabs.addTab(self._build_queue_tab(), "spock_queue")
        self.tabs.addTab(self._build_captains_log_tab(), "spock_captains_log")
        self.tabs.addTab(
            self._build_tool_tab(
                "spock_llmfit_fit",
                "Rank models that fit this machine via local llmfit (tok/s + fit level).",
                self._run_llmfit_fit,
            ),
            "spock_llmfit_fit",
        )
        self.tabs.addTab(self._build_hardware_plan_tab(), "spock_hardware_plan")
        layout.addWidget(self.tabs, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        title = QLabel("SHIP COMPUTER — DATABASE OVERVIEW")
        tf = QFont()
        tf.setPointSize(13)
        tf.setBold(True)
        title.setFont(tf)
        lay.addWidget(title)

        tip = QLabel(
            "Document / queue / captains_log counts for ship_computer.db. "
            "Other tabs run the same probes as MCP tools (spock_health, spock_status, …)."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.stats_display = QTextEdit()
        self.stats_display.setReadOnly(True)
        self.stats_display.setFont(QFont("Consolas", 10))
        lay.addWidget(self.stats_display, 1)

        row = QHBoxLayout()
        row.addWidget(self._make_btn("Refresh Stats", self.refresh_overview, kind="accent"))
        row.addStretch()
        lay.addLayout(row)
        return tab

    def _build_spock_health_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        heading = QLabel("spock_health")
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        lay.addWidget(heading)

        tip = QLabel(
            "Probe Spock RAG API /health, llama :8080/:8081, MCP adapter, and "
            "--ui-mcp-proxy. Embedding Health runs test_embeddings.py against the "
            "configured embeddings endpoint."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #aaa;")
        lay.addWidget(tip)

        row = QHBoxLayout()
        row.addWidget(
            self._make_btn("Run Spock Health", self._run_spock_health, kind="run")
        )
        row.addWidget(
            self._make_btn("Embedding Health", self._run_embedding_health, kind="run")
        )
        row.addStretch()
        lay.addLayout(row)

        out = QTextEdit()
        out.setReadOnly(True)
        out.setFont(QFont("Consolas", 10))
        out.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(out, 1)
        tab._output = out  # type: ignore[attr-defined]
        self._health_out = out
        return tab

    def _build_tool_tab(
        self, name: str, description: str, runner: Callable[[], None]
    ) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        heading = QLabel(name)
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        lay.addWidget(heading)

        tip = QLabel(description)
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #aaa;")
        lay.addWidget(tip)

        row = QHBoxLayout()
        row.addWidget(self._make_btn(f"Run {name}", runner, kind="run"))
        row.addStretch()
        lay.addLayout(row)

        out = QTextEdit()
        out.setReadOnly(True)
        out.setFont(QFont("Consolas", 10))
        out.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(out, 1)
        tab._output = out  # type: ignore[attr-defined]
        return tab

    def _build_queue_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        heading = QLabel("spock_queue")
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        lay.addWidget(heading)
        tip = QLabel("Sample agent_queue rows (optional status filter).")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #aaa;")
        lay.addWidget(tip)

        form = QFormLayout()
        self.queue_limit = QSpinBox()
        self.queue_limit.setRange(1, 200)
        self.queue_limit.setValue(20)
        form.addRow("Limit", self.queue_limit)
        self.queue_status = QLineEdit()
        self.queue_status.setPlaceholderText("optional status filter (e.g. pending)")
        form.addRow("Status", self.queue_status)
        lay.addLayout(form)

        row = QHBoxLayout()
        row.addWidget(self._make_btn("Run spock_queue", self._run_spock_queue, kind="run"))
        row.addStretch()
        lay.addLayout(row)

        out = QTextEdit()
        out.setReadOnly(True)
        out.setFont(QFont("Consolas", 10))
        out.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(out, 1)
        tab._output = out  # type: ignore[attr-defined]
        self._queue_out = out
        return tab

    def _build_captains_log_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        heading = QLabel("spock_captains_log")
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        lay.addWidget(heading)
        tip = QLabel("Recent captains_log entries from ship_computer.db.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #aaa;")
        lay.addWidget(tip)

        form = QFormLayout()
        self.log_limit = QSpinBox()
        self.log_limit.setRange(1, 200)
        self.log_limit.setValue(20)
        form.addRow("Limit", self.log_limit)
        self.log_alert = QLineEdit()
        self.log_alert.setPlaceholderText("optional: GREEN / YELLOW / RED")
        form.addRow("Alert level", self.log_alert)
        self.log_officer = QLineEdit()
        self.log_officer.setPlaceholderText("optional officer filter")
        form.addRow("Officer", self.log_officer)
        lay.addLayout(form)

        row = QHBoxLayout()
        row.addWidget(
            self._make_btn("Run spock_captains_log", self._run_captains_log, kind="run")
        )
        row.addStretch()
        lay.addLayout(row)

        out = QTextEdit()
        out.setReadOnly(True)
        out.setFont(QFont("Consolas", 10))
        out.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(out, 1)
        tab._output = out  # type: ignore[attr-defined]
        self._log_out = out
        return tab

    def _build_hardware_plan_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        heading = QLabel("spock_hardware_plan")
        hf = QFont()
        hf.setPointSize(12)
        hf.setBold(True)
        heading.setFont(hf)
        lay.addWidget(heading)
        tip = QLabel(
            "Plan VRAM/RAM/tok/s for a model via local llmfit plan … --json. "
            "Also returns suggested llama-server -ngl."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #aaa;")
        lay.addWidget(tip)

        form = QFormLayout()
        self.plan_model = QLineEdit()
        self.plan_model.setPlaceholderText("model id or GGUF name (required)")
        form.addRow("Model", self.plan_model)
        self.plan_context = QSpinBox()
        self.plan_context.setRange(512, 1_048_576)
        self.plan_context.setValue(8192)
        form.addRow("Context", self.plan_context)
        self.plan_quant = QLineEdit()
        self.plan_quant.setPlaceholderText("optional quant (e.g. Q4_K_M)")
        form.addRow("Quant", self.plan_quant)
        lay.addLayout(form)

        row = QHBoxLayout()
        row.addWidget(
            self._make_btn("Run spock_hardware_plan", self._run_hardware_plan, kind="run")
        )
        row.addStretch()
        lay.addLayout(row)

        out = QTextEdit()
        out.setReadOnly(True)
        out.setFont(QFont("Consolas", 10))
        out.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(out, 1)
        tab._output = out  # type: ignore[attr-defined]
        self._plan_out = out
        return tab

    def apply_theme(self) -> None:
        accent = self.theme.get("accent", "#5C6BC0")
        accent_hover = self.theme.get("accent_hover", "#3F51B5")
        fg = self.theme.get("fg", "#FFFFFF")
        bg = self.theme.get("bg", "#1e1e1e")
        panel = self.theme.get("panel_bg", "#2d2d2d")
        border = self.theme.get("border", "#444444")
        self.setStyleSheet(
            f"""
            QWidget {{ background-color: {bg}; color: {fg}; }}
            QTextEdit, QLineEdit, QSpinBox {{
                background-color: {panel}; color: {fg};
                border: 1px solid {border}; border-radius: 4px;
            }}
            QPushButton {{
                background-color: {accent}; color: {fg};
                border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {accent_hover}; }}
            QPushButton[maint_kind="run"] {{ background-color: #6D9E5A; color: #FFFFFF; }}
            QPushButton[maint_kind="run"]:hover {{ background-color: #5A8A4A; }}
            QTabWidget::pane {{ border: 1px solid {border}; top: -1px; }}
            QTabBar::tab {{
                background: {panel}; color: {fg}; border: 1px solid {border};
                padding: 8px 12px; margin-right: 2px;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: #5C6BC0; color: #FFFFFF; font-weight: bold; border-color: #5C6BC0;
            }}
            """
        )

    def refresh_overview(self) -> None:
        if not os.path.exists(self.db_path):
            self.stats_display.setPlainText(f"Database not found:\n{self.db_path}")
            return
        try:
            import sqlite3

            conn = sqlite3.connect(self.db_path, timeout=5)
            docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            emb = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL"
            ).fetchone()[0]
            logs = conn.execute("SELECT COUNT(*) FROM captains_log").fetchone()[0]
            queue = conn.execute("SELECT COUNT(*) FROM agent_queue").fetchone()[0]
            quar = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
            conn.close()
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            self.stats_display.setPlainText(
                f"  Database: {os.path.basename(self.db_path)}\n"
                f"  Size:     {size_mb:.1f} MB\n"
                f"  Documents:       {docs:>6d}  ({emb} with embeddings)\n"
                f"  Captains log:    {logs:>6d}\n"
                f"  Agent queue:     {queue:>6d}\n"
                f"  Quarantine:      {quar:>6d}"
            )
            self.status_label.setText("Overview refreshed")
        except Exception as e:
            self.stats_display.setPlainText(f"Error reading database:\n{e}")

    def _set_output(self, widget: QTextEdit, text: str) -> None:
        widget.setPlainText(text)
        sb = widget.verticalScrollBar()
        sb.setValue(0)

    def _run_busy(self, label: str, fn: Callable[[], str], out: QTextEdit) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status_label.setText(f"Running {label}…")
        QApplication.processEvents()
        try:
            text = fn()
            self._set_output(out, text)
            self.status_label.setText(f"{label} complete")
        except Exception as e:
            self._set_output(out, f"ERROR: {e}")
            self.status_label.setText(f"{label} failed")
            QMessageBox.warning(self, label, str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def _run_spock_health(self) -> None:
        out = getattr(self, "_health_out", None) or getattr(
            self.tabs.widget(1), "_output", None
        )

        def _work() -> str:
            from spock_health_report import format_spock_health_report

            data = _call_mcp_tool("spock_health")
            report = format_spock_health_report(data)
            return report + "\n\n--- JSON ---\n" + _pretty(data)

        if out is not None:
            self._run_busy("spock_health", _work, out)

    def _run_embedding_health(self) -> None:
        out = getattr(self, "_health_out", None)
        script = ROOT / "test_embeddings.py"
        if not script.is_file():
            QMessageBox.warning(self, "Embedding Health", f"Not found: {script}")
            return

        def _work() -> str:
            import subprocess

            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                cwd=str(ROOT),
            )
            return ((result.stdout or "") + "\n" + (result.stderr or "")).strip() or (
                f"(exit {result.returncode}, no output)"
            )

        if out is not None:
            self._run_busy("Embedding Health", _work, out)

    def _run_spock_status(self) -> None:
        tab = self.tabs.widget(2)
        out = getattr(tab, "_output", None)

        def _work() -> str:
            data = _call_mcp_tool("spock_status")
            report = ""
            if isinstance(data, dict):
                report = str(data.get("health_report") or "")
                ship = data.get("ship_status_text") or ""
                if ship:
                    report = (report + "\n\n" + ship).strip()
            return (report + "\n\n--- JSON ---\n" + _pretty(data)).strip()

        if out is not None:
            self._run_busy("spock_status", _work, out)

    def _run_spock_queue(self) -> None:
        def _work() -> str:
            status = (self.queue_status.text() or "").strip() or None
            return _pretty(
                _call_mcp_tool(
                    "spock_queue",
                    limit=int(self.queue_limit.value()),
                    status=status,
                )
            )

        self._run_busy("spock_queue", _work, self._queue_out)

    def _run_captains_log(self) -> None:
        def _work() -> str:
            alert = (self.log_alert.text() or "").strip().upper() or None
            if alert and alert not in ("GREEN", "YELLOW", "RED"):
                raise ValueError("Alert level must be GREEN, YELLOW, RED, or empty")
            officer = (self.log_officer.text() or "").strip() or None
            return _pretty(
                _call_mcp_tool(
                    "spock_captains_log",
                    limit=int(self.log_limit.value()),
                    alert_level=alert,
                    officer=officer,
                )
            )

        self._run_busy("spock_captains_log", _work, self._log_out)

    def _run_llmfit_fit(self) -> None:
        tab = self.tabs.widget(5)
        out = getattr(tab, "_output", None)

        def _work() -> str:
            return _pretty(_call_mcp_tool("spock_llmfit_fit", limit=10))

        if out is not None:
            self._run_busy("spock_llmfit_fit", _work, out)

    def _run_hardware_plan(self) -> None:
        def _work() -> str:
            model = (self.plan_model.text() or "").strip()
            if not model:
                raise ValueError("Model is required")
            quant = (self.plan_quant.text() or "").strip() or None
            return _pretty(
                _call_mcp_tool(
                    "spock_hardware_plan",
                    model=model,
                    context=int(self.plan_context.value()),
                    quant=quant,
                )
            )

        self._run_busy("spock_hardware_plan", _work, self._plan_out)
