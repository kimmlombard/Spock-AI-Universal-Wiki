"""Entry: Spock Bringup Menu (lite onboarding GUI)."""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _warpcore_path  # noqa: E402

_warpcore_path.ensure()


def main() -> int:
    from PyQt6.QtCore import QTimer

    from spock_bringup_menu.app import BringupMenuWindow
    from spock_shell.qt_app import create_app

    app = create_app(sys.argv)
    app.setApplicationName("Spock Bringup Menu")
    win = BringupMenuWindow()
    win.show()
    win.raise_()
    win.activateWindow()
    # Backup schedule: profile-load path also offers; this catches cases where
    # that chain was skipped. ``_offer_host_recipe`` is idempotent per session.
    QTimer.singleShot(800, lambda: win.schedule_host_recipe_offer(0))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
