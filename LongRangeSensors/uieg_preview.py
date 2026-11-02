"""Preview helpers for UIEG capture BLOBs / files (localhost HTTP for HTML)."""

from __future__ import annotations

import os
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional, Tuple


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isfile(path):
            return super().send_head()
        ext = os.path.splitext(self.path)[1].lower()
        if ext in (".js", ".mjs", ".css", ".json"):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        self.send_error(404)
        return None


def start_preview_server(directory: str) -> Tuple[HTTPServer, int, threading.Thread]:
    port = find_free_port()
    from functools import partial

    httpd = HTTPServer(("127.0.0.1", port), partial(QuietHandler, directory=directory))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port, thread


def write_temp_preview(
    content: bytes,
    capture_id: int,
    ext: str,
    temp_dir: str,
) -> str:
    os.makedirs(temp_dir, exist_ok=True)
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ".bin"
    path = os.path.join(temp_dir, f"__temp_preview_{capture_id}{ext}")
    with open(path, "wb") as f:
        f.write(content)
    return path
