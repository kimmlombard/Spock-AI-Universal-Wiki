"""Entry: Spock Engineering Deck (Ask AI / Deep Dive)."""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import _warpcore_path  # noqa: E402

_warpcore_path.ensure()

from EngineeringDeck.app import EngineeringDeckWindow  # noqa: E402
from spock_shell.qt_app import create_app  # noqa: E402


def main() -> int:
    app = create_app(sys.argv)
    win = EngineeringDeckWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
