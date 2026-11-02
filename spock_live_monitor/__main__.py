"""Stand-alone Ship Status / Live Monitor (PyQt6)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spock_health_report import discover_suite_service_rows
from spock_onboarding.health import probe_embed_chat
from spock_onboarding.live_snapshot import get_live_monitor_snapshot
from spock_onboarding.llama_process import (
    discover_llama_servers,
    format_pid_gpu,
)
from spock_onboarding.spock_status import run_spock_status_text


def _btn(text: str, bg: str) -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(
        f"QPushButton {{ background:{bg}; color:#FFFFFF; padding:8px 12px; "
        f"border:none; border-radius:4px; font-weight:600; }}"
    )
    return b


class LiveMonitorWindow(QMainWindow):
    def __init__(self, root: Optional[Path] = None) -> None:
        super().__init__()
        self.root = Path(root) if root else Path.cwd()
        self.setWindowTitle("Ship Status")
        self.resize(920, 780)
        self._monitor_labels: Dict[str, Dict[str, QLabel]] = {}
        self._closing = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        title = QLabel("Live Monitor")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #FF9800;")
        layout.addWidget(title)

        ctrl = QHBoxLayout()
        self.monitor_btn = _btn("Stop Monitor", "#6D9E5A")
        self.monitor_btn.clicked.connect(self._toggle_monitor)
        ctrl.addWidget(self.monitor_btn)

        self.spock_status_btn = _btn("Run Spock Status", "#00897B")
        self.spock_status_btn.setToolTip(
            "Same report as Ship Status -> Run Spock Status "
            "(RAG API, llama :8080/:8081, MCP adapter)"
        )
        self.spock_status_btn.clicked.connect(self._run_spock_status)
        ctrl.addWidget(self.spock_status_btn)

        ctrl.addWidget(QLabel("Interval:"))
        self.monitor_interval = QSpinBox()
        self.monitor_interval.setRange(500, 5000)
        self.monitor_interval.setSingleStep(500)
        self.monitor_interval.setValue(1000)
        self.monitor_interval.setSuffix(" ms")
        ctrl.addWidget(self.monitor_interval)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.monitor_host = QWidget()
        self.monitor_grid = QGridLayout(self.monitor_host)
        self.monitor_grid.setSpacing(10)
        layout.addWidget(self.monitor_host)

        inst_title = QLabel("Running services")
        inst_title.setFont(f)
        inst_title.setStyleSheet("color: #FF9800;")
        layout.addWidget(inst_title)

        self.state_lbl = QLabel("STANDBY")
        self.state_lbl.setStyleSheet("color: #C9A227; font-weight:700; font-size:14px;")
        layout.addWidget(self.state_lbl)

        hint = QLabel(
            "Embedding :8080 / chat :8081 (GPU shown on PID). Also lists WebUI :8082, "
            "RAG :8090, MCP :8765 when those are launched. Embedding ports are for "
            "/embeddings only — use Ask AI / chat :8081 for instruct chat."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8aa0ad;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        refresh = _btn("Refresh", "#1976D2")
        refresh.clicked.connect(lambda: self._refresh_instances(False))
        row.addWidget(refresh)
        row.addStretch()
        layout.addLayout(row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Role", "Model", "Port", "PID"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(140)
        layout.addWidget(self.table)

        layout.addWidget(QLabel("Live output:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(160)
        layout.addWidget(self.log, 1)

        self.setStyleSheet(
            "QMainWindow, QWidget { background:#1a1f24; color:#E6EEF2; }"
            "QTableWidget { background:#12171c; gridline-color:#2c3e4a; }"
            "QHeaderView::section { background:#24303a; color:#E6EEF2; padding:4px; }"
            "QTextEdit { background:#0f1419; color:#E6EEF2; border:1px solid #2c3e4a; }"
            "QSpinBox { background:#24303a; color:#E6EEF2; }"
        )

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_monitor)
        self._timer.start(1000)
        self._update_monitor()
        self._refresh_instances(False)

    def _toggle_monitor(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.monitor_btn.setText("Start Monitor")
            self.monitor_btn.setStyleSheet(
                "QPushButton { background:#5C6BC0; color:#fff; padding:8px 12px; "
                "border:none; border-radius:4px; font-weight:600; }"
            )
        else:
            self._timer.start(self.monitor_interval.value())
            self.monitor_btn.setText("Stop Monitor")
            self.monitor_btn.setStyleSheet(
                "QPushButton { background:#6D9E5A; color:#fff; padding:8px 12px; "
                "border:none; border-radius:4px; font-weight:600; }"
            )
            self._update_monitor()

    def _rebuild_boxes(self, snap: Dict[str, Dict[str, str]]) -> None:
        while self.monitor_grid.count():
            item = self.monitor_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._monitor_labels.clear()
        for col, (section, items) in enumerate(snap.items()):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame.setStyleSheet(
                "QFrame { background:#24303a; border:1px solid #2c3e4a; border-radius:8px; }"
            )
            v = QVBoxLayout(frame)
            head = QLabel(section)
            head.setStyleSheet("font-weight:700; color:#FF9800;")
            v.addWidget(head)
            labels: Dict[str, QLabel] = {}
            for key, val in items.items():
                lab = QLabel(f"{key}: {val}")
                lab.setWordWrap(True)
                v.addWidget(lab)
                labels[key] = lab
            self._monitor_labels[section] = labels
            self.monitor_grid.addWidget(frame, 0, col)

    def _update_monitor(self) -> None:
        if self._closing:
            return
        snap = get_live_monitor_snapshot()
        if set(snap.keys()) != set(self._monitor_labels.keys()):
            self._rebuild_boxes(snap)
        else:
            for section, items in snap.items():
                labels = self._monitor_labels.get(section, {})
                for key, value in items.items():
                    if key in labels:
                        labels[key].setText(f"{key}: {value}")
        if self._timer.isActive():
            wanted = self.monitor_interval.value()
            if self._timer.interval() != wanted:
                self._timer.setInterval(wanted)
        self._refresh_instances(True)

    def _refresh_instances(self, quiet: bool = False) -> None:
        rows = discover_llama_servers()
        probes = probe_embed_chat()
        by_port = {}
        for role_key, info in (
            ("embedding", probes.get("embed")),
            ("chat", probes.get("chat")),
        ):
            if isinstance(info, dict) and info.get("port") is not None:
                try:
                    by_port[int(info["port"])] = (role_key, info)
                except (TypeError, ValueError):
                    pass

        self.table.setRowCount(0)
        for info in rows:
            port = int(info.get("port") or 0)
            role = str(info.get("role") or "unknown")
            model = Path(str(info.get("model_path") or "")).name or "-"
            if port in by_port:
                role, probe = by_port[port]
                model = probe.get("model_name") or model
            gpu = str(info.get("gpu_label") or "")
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(role))
            self.table.setItem(r, 1, QTableWidgetItem(model))
            self.table.setItem(r, 2, QTableWidgetItem(str(port)))
            self.table.setItem(
                r, 3, QTableWidgetItem(format_pid_gpu(info.get("pid"), gpu))
            )

        for svc in discover_suite_service_rows():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(svc.get("role") or "")))
            self.table.setItem(r, 1, QTableWidgetItem(str(svc.get("model") or "—")))
            self.table.setItem(r, 2, QTableWidgetItem(str(svc.get("port") or "")))
            self.table.setItem(
                r,
                3,
                QTableWidgetItem(
                    format_pid_gpu(svc.get("pid"), str(svc.get("gpu_label") or ""))
                ),
            )

        n = self.table.rowCount()
        if n:
            roles = [self.table.item(r, 0).text() for r in range(n)]
            self.state_lbl.setText(f"RUNNING - {n} service(s) ({', '.join(roles)})")
            self.state_lbl.setStyleSheet(
                "color: #6D9E5A; font-weight:700; font-size:14px;"
            )
        else:
            self.state_lbl.setText("STANDBY - no suite services")
            self.state_lbl.setStyleSheet(
                "color: #C9A227; font-weight:700; font-size:14px;"
            )
        if not quiet:
            self.log.append("Refreshed instance list.")

    def _run_spock_status(self) -> None:
        from spock_shell.busy_ui import clear_override_cursors

        clear_override_cursors()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            report = run_spock_status_text(root=self.root)
            clear_override_cursors()
            self._show_report("Spock Status (spock-status)", report)
            self.log.append("Ran Spock Status.")
        except Exception as e:
            clear_override_cursors()
            QMessageBox.warning(self, "Spock Status", str(e))
        finally:
            clear_override_cursors()

    def _show_report(self, title: str, text: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(760, 520)
        lay = QVBoxLayout(dlg)
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text)
        edit.setFont(QFont("Consolas", 10))
        lay.addWidget(edit)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._closing = True
        if self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path.cwd()
    if "--root" in args:
        i = args.index("--root")
        if i + 1 < len(args):
            root = Path(args[i + 1])
    app = QApplication(sys.argv)
    win = LiveMonitorWindow(root=root)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
