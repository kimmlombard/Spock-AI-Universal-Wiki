"""Spock-UIE-Wiki-KB — main orchestrator for suite mini-apps."""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _warpcore_path

_warpcore_path.ensure()


def main() -> int:
    from Orchestrator.app import UieWikiKbOrchestratorWindow
    from spock_shell.qt_app import create_app

    app = create_app(sys.argv)
    app.setApplicationName("Spock-UIE-Wiki-KB")
    win = UieWikiKbOrchestratorWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
