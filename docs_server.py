"""Pre-built mkdocs site server — serves ./site (port from config / SPOCK_DOCS_PORT).

Uses Python stdlib http.server (ThreadingHTTPServer).
"""

from __future__ import annotations

import http.server
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
SITE_DIR = _HERE / "site"

try:
    from WarpCore.service_endpoints import DEFAULT_DOCS_PORT, resolve_ports
except ImportError:  # pragma: no cover
    DEFAULT_DOCS_PORT = 8000

    def resolve_ports(cfg=None):
        return {"docs": DEFAULT_DOCS_PORT}


class _DocsHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files from the pre-built mkdocs site directory."""

    def __init__(self, *args, directory: str = "", **kwargs):
        super().__init__(*args, directory=directory or str(SITE_DIR), **kwargs)

    def log_message(self, format: str, *args) -> None:
        pass

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = self.path.split("?", 1)[0]
        target = SITE_DIR / parsed.lstrip("/")

        if target.is_dir():
            index = target / "index.html"
            if index.exists():
                self.path = parsed.rstrip("/") + "/index.html"

        if not target.exists() and not (SITE_DIR / parsed.lstrip("/")).exists():
            fallback = SITE_DIR / "index.html"
            if fallback.exists():
                self.path = "/index.html"

        super().do_GET()


class DocsServer:
    """Lightweight docs server for the pre-built site."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        site_dir: Optional[Path] = None,
        config: Optional[dict] = None,
    ):
        self.host = host
        if port is None:
            port = int(resolve_ports(config).get("docs", DEFAULT_DOCS_PORT))
        self.port = int(port)
        self.site_dir = Path(site_dir) if site_dir else SITE_DIR
        self._server: Optional[http.server.ThreadingHTTPServer] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _make_handler(self, *args, **kwargs):
        return _DocsHandler(*args, directory=str(self.site_dir), **kwargs)

    def start_background(self) -> None:
        """Start server in a daemon thread."""
        import threading

        self._server = http.server.ThreadingHTTPServer(
            (self.host, self.port), self._make_handler
        )
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()

    def serve_forever(self) -> None:
        """Block and serve (non-background)."""
        self._server = http.server.ThreadingHTTPServer(
            (self.host, self.port), self._make_handler
        )
        print(f"Spock AI Helper docs: {self.url}")
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down docs server.")
            self._server.shutdown()

    def shutdown(self) -> None:
        if self._server:
            self._server.shutdown()


def main() -> int:
    port = None
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    server = DocsServer(port=port)
    if not SITE_DIR.exists() or not (SITE_DIR / "index.html").exists():
        print(f"Warning: site/ directory not found or empty at {SITE_DIR}")
        print("Build with: mkdocs build (from the Spock-Onboarding root)")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
