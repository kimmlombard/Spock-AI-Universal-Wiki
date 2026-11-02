"""Spock-UIE-Wiki-KB v2 orchestrator.

QApplication -> OrchestratorWindow -> station packages.

Kept deliberately thin: it sets up import paths (WarpCore + stations), then
delegates to Spock-UIE-Wiki-KB.py (the station-suite entry point) which owns
app creation via spock_shell.qt_app and the UIE wiki KB orchestrator window.
"""

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _warpcore_path  # noqa: E402

_warpcore_path.ensure()

_ENTRY = os.path.join(_HERE, "Spock-UIE-Wiki-KB.py")
_spec = importlib.util.spec_from_file_location("spock_uie_wiki_kb", _ENTRY)
assert _spec is not None and _spec.loader is not None
_spock = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_spock)


def main() -> int:
    return _spock.main()


if __name__ == "__main__":
    sys.exit(main())
