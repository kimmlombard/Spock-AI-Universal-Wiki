"""Immediate wait-cursor + progress feedback for long Qt actions.

Qt timers do not fire while the GUI thread is blocked. Call ``heartbeat()``
from long synchronous work so the elapsed label updates and the event loop
can paint. Always clear the full override-cursor stack on exit — a single
``restoreOverrideCursor()`` leaves the spinner stuck on Windows when dialogs
stacked extra overrides.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, List, Optional

from PyQt6.QtCore import QEventLoop, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

_active: List["BusySession"] = []


def clear_override_cursors() -> None:
    """Pop every application override cursor (safe if already clear)."""
    app = QApplication.instance()
    if app is None:
        return
    while app.overrideCursor() is not None:
        app.restoreOverrideCursor()


def make_progress_bar() -> QProgressBar:
    """Inline panel bar (idle). Use ``set_busy`` while background work runs."""
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(False)
    return bar


def set_busy(bar: Optional[QProgressBar], busy: bool) -> None:
    """Toggle indeterminate pulse (busy) vs idle 0%."""
    if bar is None:
        return
    if busy:
        bar.setRange(0, 0)
    else:
        bar.setRange(0, 100)
        bar.setValue(0)


class BusySession:
    """One in-progress busy scope (progress UI + wait cursor)."""

    def __init__(self, parent: Optional[QWidget], message: str, *, show_dialog: bool):
        self.parent = parent
        self.message = message
        self.show_dialog = show_dialog
        self.t0 = time.monotonic()
        self._win: Optional[QWidget] = None
        self._label: Optional[QLabel] = None
        self._bar: Optional[QProgressBar] = None

    def start(self) -> None:
        clear_override_cursors()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        if self.show_dialog and self.parent is not None:
            self._win = QWidget(self.parent, Qt.WindowType.Dialog)
            self._win.setWindowTitle(self.message.split("…")[0].strip() or "Working")
            self._win.setWindowModality(Qt.WindowModality.ApplicationModal)
            self._win.setMinimumWidth(380)
            lay = QVBoxLayout(self._win)
            self._label = QLabel(f"{self.message}\nElapsed: 0s")
            self._label.setWordWrap(True)
            lay.addWidget(self._label)
            self._bar = QProgressBar()
            self._bar.setRange(0, 0)
            self._bar.setTextVisible(False)
            lay.addWidget(self._bar)
            self._win.show()
            # Center over parent
            try:
                geo = self.parent.frameGeometry()
                self._win.move(
                    geo.center().x() - self._win.width() // 2,
                    geo.center().y() - self._win.height() // 2,
                )
            except Exception:
                pass
        self.pulse()

    def pulse(self, status: Optional[str] = None) -> None:
        """Update elapsed text and let Qt paint (call during long work)."""
        if status:
            self.message = status
        secs = max(0, int(time.monotonic() - self.t0))
        if self._label is not None:
            self._label.setText(f"{self.message}\nElapsed: {secs}s")
            self._label.repaint()
        if self._bar is not None:
            self._bar.repaint()
        if self._win is not None:
            self._win.repaint()
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )

    def stop(self) -> None:
        if self._win is not None:
            self._win.hide()
            self._win.close()
            self._win.deleteLater()
            self._win = None
            self._label = None
            self._bar = None
        clear_override_cursors()
        if self.parent is not None:
            try:
                self.parent.unsetCursor()
            except Exception:
                pass
        QApplication.processEvents()


def heartbeat(status: Optional[str] = None) -> None:
    """Keep busy UI alive while the GUI thread runs synchronous work."""
    if _active:
        _active[-1].pulse(status)


@contextmanager
def pause_busy_for_dialog() -> Iterator[None]:
    """Drop wait cursor while a QMessageBox is shown; restore afterward."""
    clear_override_cursors()
    QApplication.processEvents()
    try:
        yield
    finally:
        if _active:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            _active[-1].pulse()


@contextmanager
def busy_scope(
    parent: Optional[QWidget] = None,
    message: str = "Working…",
    *,
    show_dialog: bool = True,
) -> Iterator[BusySession]:
    """Wait cursor + optional progress window with elapsed seconds.

    Call ``heartbeat()`` (or ``session.pulse()``) inside long work so the
    elapsed timer advances; a plain ``QTimer`` will not fire while blocked.
    """
    session = BusySession(parent, message, show_dialog=show_dialog)
    _active.append(session)
    try:
        session.start()
        yield session
    finally:
        if _active and _active[-1] is session:
            _active.pop()
        elif session in _active:
            _active.remove(session)
        session.stop()
