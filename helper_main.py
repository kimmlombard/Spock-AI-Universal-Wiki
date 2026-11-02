"""Spock AI Helper — suite entry point.

Launches:
  1. Docs server (background) from pre-built site/ — port from docs_port / SPOCK_DOCS_PORT
  2. Browser to the docs URL
  3. Shared Chat AI Helper GUI (chat_ai_helper.py) over AIHelperDocuments/

Prerequisites:
  - Chat LLM reachable (configured provider / llama-server)
  - Pre-built site/ directory (build with: mkdocs build)
"""

from __future__ import annotations

import sys
import threading
import time
from docs_server import DocsServer, SITE_DIR


def _open_browser(url: str) -> None:
    time.sleep(0.6)
    from spock_shell.open_url import open_url

    open_url(url)


def main() -> int:
    from spock_shell.paths import ensure_root_on_path

    ensure_root_on_path()

    from WarpCore.service_endpoints import docs_base_url, resolve_ports
    from WarpCore.theme import THEMES
    from spock_shell.ai_helper import open_ai_helper
    from spock_shell.config import load_config

    try:
        config = load_config()
    except Exception as exc:
        print(f"Warning: could not load ship_computer settings ({exc}); using defaults.")
        config = {"ask_ai_provider": "llama-server"}

    ports = resolve_ports(config)
    docs_port = int(ports["docs"])
    docs_url = docs_base_url(config)

    if SITE_DIR.exists() and (SITE_DIR / "index.html").exists():
        server = DocsServer(port=docs_port, config=config)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        print(f"Docs site running at {docs_url}")
        bt = threading.Thread(target=_open_browser, args=(docs_url,), daemon=True)
        bt.start()
    else:
        print(f"Warning: site/ not found at {SITE_DIR}")
        print("Build with: mkdocs build")

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    theme = THEMES.get("dark") or next(iter(THEMES.values()))
    win = open_ai_helper(parent=None, theme=theme, config=config)  # type: ignore[arg-type]
    if win is None:
        print("Failed to open Chat AI Helper.")
        return 1
    setattr(win, "_force_close", True)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
