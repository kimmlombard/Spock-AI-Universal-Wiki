"""Minimal HTTP crawler → captured_files only (disk-first).

Adapted from D:\\Spock-To-Bridge-UIEG-Scanner\\crawler.py.
Does not write the DB — Import step loads files into uieg_capture.db.
"""

from __future__ import annotations

import os
import re
from collections import deque
from typing import Callable, Deque, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests

from WarpCore.deps import missing_crawler_deps, missing_deps_message

LogFn = Callable[[str], None]

USER_AGENT = (
    "Spock-to-bridge-UIEG-Capture/1.0 (+local research; not a browser extension)"
)


def to_raw_github_url(url: str) -> str:
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/(.*)", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return url


def _safe_filename_from_url(url: str, default_ext: str = ".html") -> str:
    stripped = url.replace("https://", "").replace("http://", "")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in stripped)[:200]
    if not safe:
        safe = "page"
    if not os.path.splitext(safe)[1]:
        safe += default_ext
    return safe


def _same_host(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()
    except Exception:
        return False


def _normalize_url(u: str) -> str:
    u = (u or "").split("#")[0].strip()
    if u.endswith("/") and u.count("/") > 2:
        u = u.rstrip("/")
    return u


def _soup(html: str):
    """Parse HTML. Imported lazily — bs4 arrives with the Phase B full tier."""
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def _extract_same_host_links(base_url: str, html: str) -> List[str]:
    soup = _soup(html)
    out: List[str] = []
    for a in soup.find_all("a", href=True):
        full = _normalize_url(urljoin(base_url, a["href"]))
        if not full.startswith(("http://", "https://")):
            continue
        if not _same_host(base_url, full):
            continue
        if "login" in full.lower() and "return_to" in full.lower():
            continue
        out.append(full)
    return list(dict.fromkeys(out))


def snapshot_url_to_html(
    url: str,
    dest_path: str,
    *,
    timeout_sec: int = 15,
    log: Optional[LogFn] = None,
) -> str:
    """Fetch one URL and write an offline .html snapshot (SingleFile-spirit, no browser).

    Returns the written dest_path. Raises OSError / RuntimeError on failure.
    """
    _log = log or (lambda _m: None)
    target = to_raw_github_url((url or "").strip())
    if not target:
        raise RuntimeError("No URL to snapshot.")

    dest = dest_path
    if not dest.lower().endswith((".html", ".htm")):
        dest = dest + ".html"
    parent = os.path.dirname(os.path.abspath(dest))
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Local file:// or plain path — copy/read without HTTP
    local_path = ""
    if target.lower().startswith("file:"):
        try:
            from urllib.parse import unquote, urlparse

            local_path = unquote(urlparse(target).path)
            if os.name == "nt" and local_path.startswith("/") and len(local_path) > 2 and local_path[2] == ":":
                local_path = local_path[1:]
        except Exception:
            local_path = ""
    elif os.path.isfile(target):
        local_path = target

    if local_path and os.path.isfile(local_path):
        _log(f"Copying local HTML {local_path} -> {dest}")
        with open(local_path, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
        with open(dest, "w", encoding="utf-8", errors="replace") as f:
            f.write(html)
        return dest

    if not target.startswith(("http://", "https://")):
        raise RuntimeError(f"Unsupported URL for HTML snapshot:\n{target}")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    _log(f"Snapshot {target} -> {dest}")
    try:
        r = session.get(target, timeout=timeout_sec)
        r.raise_for_status()
        r.encoding = r.encoding or "utf-8"
        html = r.text
    except Exception as e:
        raise RuntimeError(f"Fetch failed for {target}: {e}") from e

    # Light SingleFile-spirit touch: ensure charset meta so offline open is readable
    if html and "<meta" in html.lower() and "charset" not in html.lower()[:800]:
        insert = '<meta charset="utf-8">'
        lower = html.lower()
        idx = lower.find("<head>")
        if idx >= 0:
            html = html[: idx + 6] + insert + html[idx + 6 :]
        else:
            html = insert + html

    with open(dest, "w", encoding="utf-8", errors="replace") as f:
        f.write(html)
    _log(f"Saved {os.path.basename(dest)}")
    return dest


def crawl_url_to_disk(
    url: str,
    capture_folder: str,
    *,
    link_limit: int = 10,
    crawl_levels: int = 2,
    timeout_sec: int = 15,
    fetch_code_links: bool = True,
    code_exts: Optional[Set[str]] = None,
    log: Optional[LogFn] = None,
) -> List[str]:
    """BFS crawl: start URL + same-host pages up to crawl_levels deep.

    link_limit caps total HTML pages saved (including the start URL).
    crawl_levels=1 fetches only the start URL; 2 = start + one link hop; etc.
    Returns list of written file paths.
    """
    missing = missing_crawler_deps()
    if missing:
        raise RuntimeError(missing_deps_message(missing, "Crawl to disk"))
    _log = log or (lambda _m: None)
    os.makedirs(capture_folder, exist_ok=True)
    code_exts = code_exts or {".py", ".md", ".txt", ".rst"}
    written: List[str] = []
    written_urls: Set[str] = set()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    max_pages = max(1, int(link_limit))
    max_depth = max(0, int(crawl_levels) - 1)

    def fetch_text(u: str) -> Optional[str]:
        try:
            r = session.get(u, timeout=timeout_sec)
            r.raise_for_status()
            r.encoding = r.encoding or "utf-8"
            return r.text
        except Exception as e:
            _log(f"Fetch failed for {u}: {e}")
            return None

    def fetch_bytes(u: str) -> Optional[bytes]:
        try:
            r = session.get(u, timeout=timeout_sec)
            r.raise_for_status()
            return r.content
        except Exception as e:
            _log(f"Fetch failed for {u}: {e}")
            return None

    def save_html(page_url: str, html: str) -> Optional[str]:
        if page_url in written_urls:
            return None
        fname = _safe_filename_from_url(page_url, ".html")
        if not fname.endswith(".html"):
            fname = os.path.splitext(fname)[0] + ".html"
        stem, ext = os.path.splitext(fname)
        fpath = os.path.join(capture_folder, fname)
        n = 2
        while os.path.exists(fpath):
            fname = f"{stem}_{n}{ext}"
            fpath = os.path.join(capture_folder, fname)
            n += 1
        with open(fpath, "w", encoding="utf-8", errors="replace") as f:
            f.write(html)
        written_urls.add(page_url)
        written.append(fpath)
        _log(f"Saved {fname}")
        return fpath

    start = _normalize_url(url)
    if not start.startswith(("http://", "https://")):
        start = "https://" + start.lstrip("/")

    _log(
        f"Crawling {start} -> {capture_folder} "
        f"(levels={crawl_levels}, page cap={max_pages})"
    )

    queue: Deque[Tuple[str, int]] = deque([(start, 0)])
    seen: Set[str] = {start}
    first_html: Optional[str] = None

    while queue and len(written) < max_pages:
        cur_url, depth = queue.popleft()
        html = fetch_text(cur_url)
        if not html:
            continue
        save_html(cur_url, html)
        if cur_url == start:
            first_html = html
        if depth >= max_depth or len(written) >= max_pages:
            continue
        for link in _extract_same_host_links(cur_url, html):
            if link in seen:
                continue
            if len(written) + len(queue) >= max_pages:
                break
            seen.add(link)
            queue.append((link, depth + 1))

    if fetch_code_links and first_html:
        code_links: List[Tuple[str, str]] = []
        seen_raw: Set[str] = set()
        soup = _soup(first_html)
        for a in soup.find_all("a", href=True):
            full = urljoin(start, a["href"])
            ext = os.path.splitext(urlparse(full).path)[1].lower()
            if ext not in code_exts:
                continue
            raw = to_raw_github_url(full)
            if raw in seen_raw:
                continue
            seen_raw.add(raw)
            code_links.append((os.path.basename(urlparse(full).path) or f"file{ext}", raw))

        for fname, raw_url in code_links[:20]:
            content = fetch_bytes(raw_url)
            if not content:
                continue
            fpath = os.path.join(capture_folder, fname)
            if os.path.exists(fpath):
                base, ext = os.path.splitext(fname)
                fpath = os.path.join(capture_folder, f"{base}_raw{ext}")
                fname = os.path.basename(fpath)
            with open(fpath, "wb") as f:
                f.write(content)
            written.append(fpath)
            _log(f"Saved code {fname}")

    _log(
        f"Crawl complete — {len(written)} file(s) on disk "
        f"({len(written_urls)} HTML page(s)). Import to load DB."
    )
    return written
