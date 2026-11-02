"""SQLite store for Search + Save captures (uieg_capture.db).

Adapted from D:\\Spock-To-Bridge-UIEG-Scanner\\database.py with source_url / source_kind.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


from LongRangeSensors.uieg_paths import CHANNEL_CRAWL, CHANNEL_REPO


def _backfill_capture_channels(c: sqlite3.Cursor) -> None:
    """Set channel on legacy rows from path / source_kind heuristics."""
    rows = c.execute(
        "SELECT id, filepath, filename, source_kind, channel FROM captures"
    ).fetchall()
    for cid, filepath, filename, source_kind, channel in rows:
        if channel in (CHANNEL_CRAWL, CHANNEL_REPO):
            continue
        fp = str(filepath or filename or "").replace("\\", "/").lower()
        sk = str(source_kind or "").lower()
        ch = CHANNEL_CRAWL
        if "/repos/" in fp or "\\repos\\" in str(filepath or ""):
            ch = CHANNEL_REPO
        elif sk in ("repo_file", "repo_import", "folder_import") and _repo_key_from_filepath(
            str(filepath or "")
        ):
            ch = CHANNEL_REPO
        elif sk.startswith("repo"):
            ch = CHANNEL_REPO
        c.execute("UPDATE captures SET channel = ? WHERE id = ?", (ch, cid))


def init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS capture_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                label TEXT,
                source_url TEXT,
                disk_root TEXT,
                created_at TEXT,
                file_count INTEGER DEFAULT 0,
                notes TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                filepath TEXT,
                filetype TEXT,
                captured_at TEXT,
                content BLOB,
                source_url TEXT,
                source_kind TEXT
            )
            """
        )
        # Migrate older UIEG schemas missing optional columns
        cols = {row[1] for row in c.execute("PRAGMA table_info(captures)").fetchall()}
        if "source_url" not in cols:
            c.execute("ALTER TABLE captures ADD COLUMN source_url TEXT")
        if "source_kind" not in cols:
            c.execute("ALTER TABLE captures ADD COLUMN source_kind TEXT")
        if "promoted_at" not in cols:
            c.execute("ALTER TABLE captures ADD COLUMN promoted_at TEXT")
        if "promoted_path" not in cols:
            c.execute("ALTER TABLE captures ADD COLUMN promoted_path TEXT")
        if "file_size" not in cols:
            c.execute("ALTER TABLE captures ADD COLUMN file_size INTEGER")
        if "batch_id" not in cols:
            c.execute("ALTER TABLE captures ADD COLUMN batch_id INTEGER")
        if "channel" not in cols:
            c.execute("ALTER TABLE captures ADD COLUMN channel TEXT")
        # Backfill size from BLOB length when missing
        c.execute(
            """
            UPDATE captures
            SET file_size = length(content)
            WHERE file_size IS NULL AND content IS NOT NULL
            """
        )
        _backfill_capture_channels(c)
        # NOTE: spock_profile table is owned by WarpCore.profile_store in
        # ships_computer.db (V2 consolidation) — no longer created here.
        conn.commit()
    finally:
        conn.close()


def create_batch(
    db_path: str,
    channel: str,
    label: str,
    *,
    source_url: Optional[str] = None,
    disk_root: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO capture_batches
                (channel, label, source_url, disk_root, created_at, file_count, notes)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (
                channel,
                label,
                source_url,
                disk_root,
                datetime.now().isoformat(timespec="seconds"),
                notes,
            ),
        )
        conn.commit()
        return int(c.lastrowid)
    finally:
        conn.close()


def update_batch_file_count(db_path: str, batch_id: int, file_count: int) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE capture_batches SET file_count = ? WHERE id = ?",
            (int(file_count), int(batch_id)),
        )
        conn.commit()
    finally:
        conn.close()


def list_batches(
    db_path: str,
    channel: Optional[str] = None,
    *,
    limit: int = 20,
) -> List[Tuple]:
    conn = sqlite3.connect(db_path)
    try:
        if channel:
            return conn.execute(
                """
                SELECT id, channel, label, source_url, disk_root, created_at, file_count, notes
                FROM capture_batches
                WHERE channel = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (channel, limit),
            ).fetchall()
        return conn.execute(
            """
            SELECT id, channel, label, source_url, disk_root, created_at, file_count, notes
            FROM capture_batches
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def format_file_size(n: Optional[int]) -> str:
    """Human-readable size for Browse grid."""
    if n is None:
        return "—"
    try:
        size = int(n)
    except (TypeError, ValueError):
        return "—"
    if size < 0:
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def insert_capture(
    db_path: str,
    filename: str,
    filepath: str,
    filetype: str,
    content: bytes,
    source_url: Optional[str] = None,
    source_kind: Optional[str] = None,
    file_size: Optional[int] = None,
    batch_id: Optional[int] = None,
    channel: Optional[str] = None,
) -> int:
    blob = content if isinstance(content, (bytes, bytearray)) else bytes(content or b"")
    size = int(file_size) if file_size is not None else len(blob)
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO captures
                (filename, filepath, filetype, captured_at, content,
                 source_url, source_kind, file_size, batch_id, channel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                filepath,
                filetype,
                datetime.now().isoformat(timespec="seconds"),
                blob,
                source_url,
                source_kind,
                size,
                batch_id,
                channel,
            ),
        )
        conn.commit()
        return int(c.lastrowid)
    finally:
        conn.close()


def _capture_select_sql(channel: Optional[str] = None) -> Tuple[str, Tuple]:
    base = """
            SELECT id, filename, filepath, filetype, captured_at, source_url, source_kind,
                   promoted_at, promoted_path, file_size, channel, batch_id
            FROM captures
            """
    if channel:
        return base + " WHERE channel = ? ORDER BY id DESC", (channel,)
    return base + " ORDER BY id DESC", ()


def list_captures(db_path: str, channel: Optional[str] = None) -> List[Tuple]:
    conn = sqlite3.connect(db_path)
    try:
        sql, params = _capture_select_sql(channel)
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def get_capture_content(db_path: str, capture_id: int) -> Optional[bytes]:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("SELECT content FROM captures WHERE id = ?", (capture_id,))
        row = c.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_capture_row(db_path: str, capture_id: int) -> Optional[Tuple]:
    """Row: id, filename, filepath, filetype, captured_at, source_url, source_kind,
    promoted_at, promoted_path, file_size, channel, batch_id.
    """
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, filename, filepath, filetype, captured_at, source_url, source_kind,
                   promoted_at, promoted_path, file_size, channel, batch_id
            FROM captures WHERE id = ?
            """,
            (capture_id,),
        )
        return c.fetchone()
    finally:
        conn.close()


def mark_capture_promoted(
    db_path: str,
    capture_id: int,
    promoted_path: str,
    promoted_at: Optional[str] = None,
) -> None:
    when = promoted_at or datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            """
            UPDATE captures
            SET promoted_at = ?, promoted_path = ?
            WHERE id = ?
            """,
            (when, promoted_path, capture_id),
        )
        conn.commit()
    finally:
        conn.close()


def clear_database(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("DELETE FROM captures")
        c.execute("DELETE FROM capture_batches")
        for name in ("captures", "capture_batches"):
            try:
                c.execute("DELETE FROM sqlite_sequence WHERE name = ?", (name,))
            except sqlite3.Error:
                pass
        conn.commit()
    finally:
        conn.close()


def file_exists_in_db(db_path: str, filename: str) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM captures WHERE filename = ? LIMIT 1", (filename,))
        return c.fetchone() is not None
    finally:
        conn.close()


def count_captures(db_path: str, channel: Optional[str] = None) -> int:
    conn = sqlite3.connect(db_path)
    try:
        if channel:
            row = conn.execute(
                "SELECT COUNT(*) FROM captures WHERE channel = ?", (channel,)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM captures").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _github_slug_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    u = url.strip().rstrip("/")
    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "github.com/",
    ):
        if u.lower().startswith(prefix):
            rest = u[len(prefix) :]
            parts = [p for p in rest.split("/") if p]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    if "/" in u and "://" not in u and u.count("/") == 1:
        return u
    return None


_SKIP_REPO_FOLDER_NAMES = {
    "captured_files",
    "promoted_research",
    "_repos",
    "crawl",
    "repos",
    "node_modules",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
}


def _repo_key_from_filepath(filepath: str) -> Optional[str]:
    """Best-effort owner/repo from .../repos/owner_repo/file.md or legacy owner_repo/."""
    if not filepath:
        return None
    norm = filepath.replace("\\", "/").strip()
    if len(norm) >= 2 and norm[1] == ":":
        norm = norm[2:].lstrip("/")
    parts = [p for p in norm.split("/") if p and p not in (".", "..")]
    if not parts:
        return None

    def _slug_from_leaf(leaf: str) -> Optional[str]:
        if not leaf or leaf in _SKIP_REPO_FOLDER_NAMES or leaf.startswith("."):
            return None
        if "_" not in leaf:
            return None
        if "." in leaf and leaf.rsplit(".", 1)[-1].lower() in {
            "md", "py", "txt", "rst", "json", "toml", "yml", "yaml",
            "html", "htm", "js", "css", "png", "jpg", "pdf",
        }:
            return None
        owner, _, repo = leaf.partition("_")
        if not owner or not repo or owner in _SKIP_REPO_FOLDER_NAMES:
            return None
        return f"{owner}/{repo}"

    for i, part in enumerate(parts):
        if part in ("captured_files", "repos") and i + 1 < len(parts):
            slug = _slug_from_leaf(parts[i + 1])
            if slug:
                return slug
    return _slug_from_leaf(parts[0])


def summarize_uieg_db(db_path: str) -> Dict[str, Any]:
    """Return overview + repo list for UIEG Status panel."""
    from collections import Counter, defaultdict

    out: Dict[str, Any] = {
        "exists": False,
        "db_path": db_path,
        "size_mb": 0.0,
        "total": 0,
        "promoted": 0,
        "by_kind": {},
        "by_channel": {},
        "batches": [],
        "repos": [],
        "error": None,
    }
    if not os.path.isfile(db_path):
        out["error"] = f"Database not found:\n{db_path}"
        return out
    out["exists"] = True
    try:
        out["size_mb"] = os.path.getsize(db_path) / (1024 * 1024)
    except OSError:
        pass
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            total = conn.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
            promoted = conn.execute(
                "SELECT COUNT(*) FROM captures WHERE promoted_at IS NOT NULL AND promoted_at != ''"
            ).fetchone()[0]
            kinds = conn.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(source_kind), ''), '(none)'), COUNT(*)
                FROM captures GROUP BY 1 ORDER BY 2 DESC
                """
            ).fetchall()
            channels = conn.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(channel), ''), '(none)'), COUNT(*)
                FROM captures GROUP BY 1 ORDER BY 2 DESC
                """
            ).fetchall()
            batch_rows = conn.execute(
                """
                SELECT id, channel, label, source_url, disk_root, created_at, file_count
                FROM capture_batches
                ORDER BY id DESC
                LIMIT 15
                """
            ).fetchall()
            rows = conn.execute(
                """
                SELECT source_url, source_kind, filepath, filename, promoted_at, channel
                FROM captures
                """
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        out["error"] = str(e)
        return out

    out["total"] = int(total or 0)
    out["promoted"] = int(promoted or 0)
    out["by_kind"] = {str(k): int(n) for k, n in kinds}
    out["by_channel"] = {str(k): int(n) for k, n in channels}
    out["batches"] = [
        {
            "id": int(b[0]),
            "channel": str(b[1] or ""),
            "label": str(b[2] or ""),
            "source_url": str(b[3] or ""),
            "disk_root": str(b[4] or ""),
            "created_at": str(b[5] or ""),
            "file_count": int(b[6] or 0),
        }
        for b in batch_rows
    ]

    repo_files: Dict[str, int] = defaultdict(int)
    repo_promoted: Dict[str, int] = defaultdict(int)
    repo_meta: Dict[str, Dict[str, Any]] = {}
    for source_url, source_kind, filepath, filename, promoted_at, channel in rows:
        if str(channel or "") == CHANNEL_CRAWL:
            continue
        slug = _github_slug_from_url(str(source_url or ""))
        if not slug:
            slug = _repo_key_from_filepath(str(filepath or "")) or _repo_key_from_filepath(
                str(filename or "")
            )
        if not slug:
            continue
        repo_files[slug] += 1
        is_promoted = bool(str(promoted_at or "").strip())
        if is_promoted:
            repo_promoted[slug] += 1
        meta = repo_meta.setdefault(
            slug,
            {
                "slug": slug,
                "files": 0,
                "promoted_files": 0,
                "source_url": "",
                "kinds": Counter(),
            },
        )
        meta["files"] = repo_files[slug]
        meta["promoted_files"] = repo_promoted[slug]
        if source_url and not meta["source_url"]:
            meta["source_url"] = str(source_url)
        if source_kind:
            meta["kinds"][str(source_kind)] += 1

    repos = sorted(repo_meta.values(), key=lambda r: (-int(r["files"]), str(r["slug"])))
    for r in repos:
        kinds_c = r.pop("kinds")
        r["kind_summary"] = ", ".join(f"{k}:{n}" for k, n in kinds_c.most_common(4)) or "-"
        files = int(r.get("files") or 0)
        promoted_n = int(r.get("promoted_files") or 0)
        if files <= 0:
            r["promoted_status"] = "-"
        elif promoted_n <= 0:
            r["promoted_status"] = "no"
        elif promoted_n >= files:
            r["promoted_status"] = "yes"
        else:
            r["promoted_status"] = f"partial ({promoted_n}/{files})"
    out["repos"] = repos
    return out


def format_uieg_status_report(db_path: str) -> str:
    """Plain-text recap of uieg_capture.db for the UIEG Status center pane."""
    info = summarize_uieg_db(db_path)
    if info.get("error") and not info.get("exists"):
        return info["error"]
    if info.get("error"):
        return f"Error reading database:\n{info['error']}"

    lines = [
        "UIEG CAPTURE - STATUS",
        "",
        f"  Database:  {os.path.basename(info['db_path'])}",
        f"  Path:      {info['db_path']}",
        f"  Size:      {info['size_mb']:.2f} MB",
        f"  Captures:  {info['total']}",
        f"  Promoted:  {info['promoted']}  (via Promote to Ship's Computer)",
        "",
        "  By source_kind:",
    ]
    by_kind = info.get("by_kind") or {}
    if not by_kind:
        lines.append("    (none)")
    else:
        for k, n in by_kind.items():
            lines.append(f"    {k:<24} {n:>6d}")

    lines.extend(["", "  By channel (workflow):"])
    by_channel = info.get("by_channel") or {}
    if not by_channel:
        lines.append("    (none)")
    else:
        for k, n in by_channel.items():
            lines.append(f"    {k:<24} {n:>6d}")

    batches = info.get("batches") or []
    lines.extend(["", "  Recent batches:", ""])
    if not batches:
        lines.append("    (none — import after crawl or repo fetch)")
    else:
        lines.append(f"  {'ID':>4}  {'Ch':<6}  {'Files':>5}  {'Label':<28}  Created")
        lines.append(f"  {'-' * 4}  {'-' * 6}  {'-' * 5}  {'-' * 28}  {'-' * 19}")
        for b in batches:
            lines.append(
                f"  {int(b.get('id') or 0):>4}  "
                f"{str(b.get('channel') or ''):<6}  "
                f"{int(b.get('file_count') or 0):>5}  "
                f"{str(b.get('label') or ''):<28}  "
                f"{str(b.get('created_at') or '')}"
            )

    lines.extend(["", "  Repos in DB:", ""])
    repos = info.get("repos") or []
    if not repos:
        lines.append("    (no repo-like captures found - fetch a repo then Import)")
    else:
        lines.append(
            f"  {'Repo':<36} {'Files':>6}  {'Promoted':<16}  Kind / URL"
        )
        lines.append(
            f"  {'-' * 36} {'-' * 6}  {'-' * 16}  {'-' * 36}"
        )
        for r in repos:
            slug = str(r.get("slug") or "")
            url = str(r.get("source_url") or "")
            kind = str(r.get("kind_summary") or "-")
            promo = str(r.get("promoted_status") or "-")
            extra = url or kind
            lines.append(
                f"  {slug:<36} {int(r.get('files') or 0):>6d}  {promo:<16}  {extra}"
            )

    return "\n".join(lines)
