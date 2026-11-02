"""Entry: spock_live_monitor mini-app."""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _warpcore_path  # noqa: E402

_warpcore_path.ensure()

from spock_live_monitor.__main__ import LiveMonitorWindow  # noqa: E402
from spock_shell.qt_app import create_app  # noqa: E402


def main() -> int:
    app = create_app(sys.argv)
    win = LiveMonitorWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
