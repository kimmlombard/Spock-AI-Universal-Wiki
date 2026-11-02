"""Demo entry: empty suite shell (Module 0 smoke)."""

from __future__ import annotations

import sys

from spock_shell.paths import ensure_root_on_path


def main() -> int:
    ensure_root_on_path()
    from spock_shell.qt_app import create_app
    from spock_shell.window import SuiteShellWindow

    app = create_app(sys.argv)
    win = SuiteShellWindow()
    win.setWindowTitle("Spock Suite Shell (demo)")
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
