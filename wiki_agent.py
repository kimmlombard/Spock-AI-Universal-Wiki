#!/usr/bin/env python3
"""
Wiki Agent - Starfleet Ship's Computer
Implements the Agent-Skill loop from AGENTS.md
Duty Officer: Computer - coordinates Spock, Scotty, Bones, Kirk

Run as: python wiki_agent.py
Or systemd: ExecStart=/usr/bin/python /home/kim/starfleet_wiki/wiki_agent.py
"""

import os
import sys
import json
import time
import sqlite3
import hashlib
import subprocess
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

# Force UTF-8 console output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# For file watching - pure Python, cross-platform
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Starfleet Configuration ---
WIKI_ROOT = Path(__file__).parent.resolve()
DB_PATH = WIKI_ROOT / "ship_computer.db"
EXTRACTOR_SCRIPT = WIKI_ROOT / "starfleet_universal_extractor.py"
AGENTS_MD = WIKI_ROOT / "AGENTS.md"
INDEX_MD = WIKI_ROOT / "index.md"
CAPTAINS_LOG_MD = WIKI_ROOT / "captains_log.md"
AGENT_LOCK_PATH = WIKI_ROOT / "wiki_agent.pid"


def _load_dotenv_embeddings():
    """Load EMBEDDINGS_* from .env into os.environ if not already set."""
    env_path = WIKI_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k.startswith("EMBEDDINGS_") and k not in os.environ:
                os.environ[k] = v.strip().strip('"').strip("'")
    except Exception:
        pass


_load_dotenv_embeddings()

# Directories to watch and ingest (from Spock_Console / scan_config.json fallback)
def _settings_store():
    import _warpcore_path

    _warpcore_path.ensure()
    from WarpCore import settings_store

    return settings_store


def _connect(timeout: float = 30.0):
    """WAL + busy_timeout via WarpCore so writers wait instead of failing locked."""
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore.db import connect as _wc_connect

        return _wc_connect(str(DB_PATH), timeout=timeout)
    except Exception:
        conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=%d" % int(timeout * 1000))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA optimize")
        return conn


def load_scan_roots() -> list:
    from db_maintenance import normalize_scan_root_path

    def _paths(roots) -> list:
        out = []
        for r in roots or []:
            if not r:
                continue
            out.append(Path(normalize_scan_root_path(str(r))))
        return out

    try:
        st = _settings_store()
        roots = st.get(str(DB_PATH), "scan.scan_roots")
        if roots:
            return _paths(roots)
    except Exception:
        pass
    cfg_path = WIKI_ROOT / "scan_config.json"
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
        roots = cfg.get("scan_roots", [])
        return _paths(roots)
    return [Path(WIKI_ROOT)]  # fallback — scan own project

SCAN_ROOTS = load_scan_roots()


# Load Prime Directive from DB
def load_config() -> Dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value_json FROM config").fetchall()
        return {k: json.loads(v) for k, v in rows}


CONFIG = load_config()
ALLOWED_ROOTS = [Path(p) for p in CONFIG.get("allowed_roots", [])]
ROLE_PATHS = CONFIG.get("role_paths", {})

# Load scan filters from Spock_Console (JSON fallback)
def load_scan_config() -> Dict[str, Any]:
    try:
        st = _settings_store()
        cfg = st.load_scan_config(str(DB_PATH))
        if cfg.get("allowed_extensions") or cfg.get("scan_roots"):
            return cfg
    except Exception:
        pass
    cfg_path = WIKI_ROOT / "scan_config.json"
    if cfg_path.exists():
        with open(cfg_path) as f:
            return json.load(f)
    return {"allowed_extensions": [], "skip_dirs": [], "skip_filenames": []}

SCAN_CONFIG = load_scan_config()
_CONFIG_EXTENSIONS = set(SCAN_CONFIG.get("allowed_extensions", []))
SKIP_DIRS = set(SCAN_CONFIG.get("skip_dirs", []))
SKIP_FILENAMES = set(SCAN_CONFIG.get("skip_filenames", []))


def _parse_extension_filter(raw: str) -> set:
    """Env WIKI_AGENT_EXTENSIONS: '.md' | '.py,.ts,.rs' | 'all' (empty → scan_config)."""
    text = (raw or "").strip()
    if not text or text.lower() in ("all", "*", "default"):
        return set(_CONFIG_EXTENSIONS)
    out = set()
    for part in text.split(","):
        p = part.strip().lower()
        if not p:
            continue
        if not p.startswith("."):
            p = f".{p}"
        out.add(p)
    return out or set(_CONFIG_EXTENSIONS)


ALLOWED_EXTENSIONS = _parse_extension_filter(os.environ.get("WIKI_AGENT_EXTENSIONS", ""))
SESSION_PATH = WIKI_ROOT / "wiki_agent_session.json"


def write_agent_session(extra: Optional[Dict] = None):
    payload = {
        "pid": os.getpid(),
        "started_at": int(time.time()),
        "started_stardate": stardate() if "stardate" in globals() else "",
        "extensions": sorted(ALLOWED_EXTENSIONS) if ALLOWED_EXTENSIONS else [],
        "filter": os.environ.get("WIKI_AGENT_EXTENSIONS", "all") or "all",
        "scan_roots": [str(r) for r in SCAN_ROOTS],
    }
    if extra:
        payload.update(extra)
    try:
        SESSION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass
    try:
        st = _settings_store()
        st.set(str(DB_PATH), "wiki_agent.session", payload, by="wiki_agent")
    except Exception:
        pass


def clear_agent_session():
    try:
        if SESSION_PATH.exists():
            data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
            if int(data.get("pid") or 0) == os.getpid():
                SESSION_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        st = _settings_store()
        st.delete(str(DB_PATH), "wiki_agent.session")
    except Exception:
        pass


# --- Starfleet Utilities ---
COLORS = {
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "RED": "\033[91m",
    "CYAN": "\033[96m",
    "DIM": "\033[90m",
    "BOLD": "\033[1m",
    "RESET": "\033[0m",
}

def console(alert: str, officer: str, action: str, message: str):
    """Echo progress to terminal with color (plain text when NO_COLOR / non-TTY)."""
    use_color = (
        sys.stdout.isatty()
        and not os.environ.get("NO_COLOR")
        and os.environ.get("TERM", "") != "dumb"
    )
    if not use_color:
        print(f"{stardate()} {officer.upper():>10} {action} {message}")
        return
    c = COLORS
    color = c.get(alert, c["DIM"])
    print(
        f"{c['DIM']}{stardate()}{c['RESET']} {color}{c['BOLD']}"
        f"{officer.upper():>10}{c['RESET']} {color}{action}{c['RESET']} "
        f"{c['DIM']}{message}{c['RESET']}"
    )


def stardate() -> str:
    return datetime.now().strftime("%Y.%m.%d.%H.%M.%S")


def log(
    officer: str,
    skill: str,
    action: str,
    target: str,
    message: str,
    alert: str = "GREEN",
):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO captains_log (stardate, alert_level, officer, skill_name, action, target_path, message)
            VALUES (?,?,?,?,?,?,?)
        """,
            (stardate(), alert, officer, skill, action, str(target), message),
        )
    # Also append to markdown for human reading
    with open(CAPTAINS_LOG_MD, "a", encoding="utf-8") as f:
        f.write(f"\n## [{stardate()}] {alert} | {officer.upper()} | {action}\n")
        f.write(f"**Target**: `{target}`\n\n{message}\n")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # OpenProcess returns None/0 if the pid does not exist
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_is_wiki_agent(pid: int) -> bool:
    """True only if pid is a live process running this install's wiki_agent.py.

    Windows reuses PIDs; a bare existence check falsely blocks after a crash
    when the old number is recycled by Cursor or another app.
    """
    if not _pid_is_running(pid) or pid == os.getpid():
        return False
    try:
        import psutil

        cmdline = " ".join(psutil.Process(pid).cmdline() or [])
    except Exception:
        return False
    folded = os.path.normcase(cmdline).replace("\\", "/")
    marker = os.path.normcase(str(WIKI_ROOT / "wiki_agent.py")).replace("\\", "/")
    return "wiki_agent.py" in folded and marker in folded


def acquire_agent_lock() -> bool:
    """Ensure only one wiki_agent owns the shared queue/DB. Stale locks are cleared."""
    if AGENT_LOCK_PATH.exists():
        try:
            old_pid = int(AGENT_LOCK_PATH.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            old_pid = 0
        if old_pid and _pid_is_wiki_agent(old_pid):
            console(
                "RED",
                "computer",
                "LOCK",
                f"Another wiki_agent is already running (PID {old_pid}). Exiting.",
            )
            return False
        try:
            AGENT_LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        AGENT_LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except OSError as e:
        console("RED", "computer", "LOCK", f"Could not write lock file: {e}")
        return False
    write_agent_session()
    return True


def release_agent_lock():
    clear_agent_session()
    try:
        if AGENT_LOCK_PATH.exists():
            cur = AGENT_LOCK_PATH.read_text(encoding="utf-8").strip()
            if cur == str(os.getpid()):
                AGENT_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _norm_path(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def enqueue_skill(skill_name: str, officer: str, payload: Dict, priority: int = 5):
    with _connect() as conn:
        # Dedup onboarding: watcher often re-fires while bootstrap/ingest is
        # still running and the document row does not exist yet.
        if skill_name == "onboarding":
            path = payload.get("path")
            if path:
                want = _norm_path(path)
                for (payload_json,) in conn.execute(
                    """
                    SELECT payload_json FROM agent_queue
                    WHERE skill_name = 'onboarding'
                      AND status IN ('pending', 'running')
                    """
                ):
                    data = json.loads(payload_json or "{}")
                    existing = data.get("path") or ""
                    batch = data.get("paths") or []
                    if existing and _norm_path(existing) == want:
                        return
                    if any(_norm_path(str(p)) == want for p in batch):
                        return
        if skill_name == "update_index":
            row = conn.execute(
                """
                SELECT 1 FROM agent_queue
                WHERE skill_name = 'update_index'
                  AND status IN ('pending', 'running')
                LIMIT 1
                """
            ).fetchone()
            if row:
                return
        conn.execute(
            """
            INSERT INTO agent_queue (skill_name, officer, payload_json, priority, status)
            VALUES (?,?,?,?, 'pending')
        """,
            (skill_name, officer, json.dumps(payload), priority),
        )


def schedule_index_update() -> None:
    """Rebuild index.md once, after outstanding onboarding jobs finish."""
    with _connect() as conn:
        pending = conn.execute(
            """
            SELECT COUNT(*) FROM agent_queue
            WHERE skill_name = 'onboarding'
              AND status IN ('pending', 'running')
            """
        ).fetchone()[0]
    if pending:
        return
    enqueue_skill("update_index", "kirk", {}, priority=8)


def infer_officer(path: Path) -> str:
    p = str(path).lower()
    for officer, patterns in ROLE_PATHS.items():
        if any(pattern in p for pattern in patterns):
            return officer
    return "kirk"  # default


# --- Skills: Each is a duty station ---
class Skills:
    """Each method is a skill. Called by the Agent based on queue.
    Every method returns a WarpCore.skills.SkillResult with structured
    evidence (counts, affected paths, error summaries) instead of raw errors.
    """

    @staticmethod
    def _result(ok: bool, evidence: str = "", log_lines=None):
        from WarpCore.skills import SkillResult

        return SkillResult(ok=ok, evidence=evidence, log_lines=list(log_lines or []))

    @staticmethod
    def onboarding(payload: Dict):
        """Trigger: new file(s). Officer: Scotty. General Order 12 applies."""
        from WarpCore.skills import validate_payload

        payload = validate_payload("onboarding", payload)
        raw_paths: List[str] = []
        if payload.get("path"):
            raw_paths.append(str(payload["path"]))
        for p in payload.get("paths") or []:
            raw_paths.append(str(p))
        seen = set()
        paths: List[Path] = []
        for raw in raw_paths:
            key = _norm_path(raw)
            if key in seen:
                continue
            seen.add(key)
            path = Path(raw)
            if not path.exists():
                log(
                    "scotty",
                    "onboarding",
                    "SKIP",
                    path,
                    "File vanished before ingest",
                    "YELLOW",
                )
                continue
            paths.append(path)
        if not paths:
            return Skills._result(False, "No files left to ingest", ["skip:empty"])

        log(
            "scotty",
            "onboarding",
            "START",
            paths[0] if len(paths) == 1 else f"{len(paths)} files",
            f"Dispatching {len(paths)} file(s) to universal extractor",
        )
        env = os.environ.copy()
        env["SCAN_ROOT"] = str(SCAN_ROOTS[0]) if SCAN_ROOTS else ""
        # Prefer Spock_Console embedding profile (embeddinggemma = 768), not a
        # stale 4096 default that drifts from the live :8080 GGUF.
        profile: Dict[str, Any] = {}
        try:
            st = _settings_store()
            for key, dest in (
                ("app.embedding_profile.embeddings_url", "embeddings_url"),
                ("app.embedding_profile.embeddings_dim", "embeddings_dim"),
                ("app.embedding_profile.truncate_chars", "truncate_chars"),
                ("app.embedding_profile.batch_chunk", "batch_chunk"),
                ("app.embedding_profile.batch_workers", "batch_workers"),
                ("app.embedding_profile.model_path", "model_path"),
                ("app.embedding_profile.model_id", "model_id"),
            ):
                val = st.get(str(DB_PATH), key)
                if val is not None and val != "":
                    profile[dest] = val
            # Nested blob form
            nested = st.get(str(DB_PATH), "app.embedding_profile")
            if isinstance(nested, dict):
                for k, v in nested.items():
                    profile.setdefault(k, v)
        except Exception:
            pass
        env["EMBEDDINGS_URL"] = str(
            os.environ.get("EMBEDDINGS_URL")
            or profile.get("embeddings_url")
            or "http://localhost:8080/embeddings"
        )
        env["EMBEDDINGS_DIM"] = str(
            os.environ.get("EMBEDDINGS_DIM")
            or profile.get("embeddings_dim")
            or 768
        )
        env["EMBEDDINGS_TRUNCATE"] = str(
            os.environ.get("EMBEDDINGS_TRUNCATE")
            or profile.get("truncate_chars")
            or 1500
        )
        env["EMBEDDINGS_BATCH_CHUNK"] = str(
            os.environ.get("EMBEDDINGS_BATCH_CHUNK")
            or profile.get("batch_chunk")
            or 32
        )
        env["EMBEDDINGS_BATCH_WORKERS"] = str(
            os.environ.get("EMBEDDINGS_BATCH_WORKERS")
            or profile.get("batch_workers")
            or 8
        )
        model_path = os.environ.get("SPOCK_EMBED_MODEL_PATH") or profile.get("model_path") or ""
        model_id = os.environ.get("SPOCK_EMBED_MODEL_ID") or profile.get("model_id") or ""
        if model_path:
            env["SPOCK_EMBED_MODEL_PATH"] = str(model_path)
        if model_id:
            env["SPOCK_EMBED_MODEL_ID"] = str(model_id)
        env["TESSERACT_CMD"] = os.environ.get(
            "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        cmd = [sys.executable, str(EXTRACTOR_SCRIPT)]
        man_path = None
        if len(paths) == 1:
            cmd.append(str(paths[0]))
        else:
            fd, man_path = tempfile.mkstemp(prefix="spock-ingest-", suffix=".txt")
            os.close(fd)
            Path(man_path).write_text(
                "\n".join(str(p) for p in paths) + "\n", encoding="utf-8"
            )
            cmd.extend(["--manifest", man_path])
        if payload.get("reprocess"):
            cmd.append("--reprocess")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
            )
        finally:
            if man_path:
                try:
                    os.unlink(man_path)
                except OSError:
                    pass
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "extractor failed").strip()
            log("scotty", "onboarding", "FAILED", paths[0], err, "RED")
            # Surface a short cause in the live Wiki Scan console (not only captains_log).
            short = err.splitlines()[-1] if err else "extractor failed"
            if len(short) > 180:
                short = short[:177] + "..."
            console("RED", "scotty", "  onboarding", f"cause: {short}")
            return Skills._result(
                False, f"Extractor failed: {err}", [f"failed:{paths[0]}"]
            )
        skip_note = ""
        for line in (result.stderr or "").splitlines():
            if line.startswith("EMBED_SKIPPED"):
                skip_note = line.strip()
        if skip_note:
            shown = skip_note if len(skip_note) <= 180 else skip_note[:177] + "..."
            console("YELLOW", "scotty", "  onboarding", shown)
            log("scotty", "onboarding", "EMBED_SKIPPED", paths[0], skip_note, "YELLOW")
        log(
            "scotty",
            "onboarding",
            "COMPLETE",
            paths[0] if len(paths) == 1 else f"{len(paths)} files",
            f"Ingest successful ({len(paths)} file(s))",
        )
        summary = f"Ingested {len(paths)} file(s)"
        if skip_note:
            summary = f"{summary}. {skip_note}"
        return Skills._result(
            True,
            summary,
            [f"ingested:{p}" for p in paths[:20]],
        )

    @staticmethod
    def maintenance(payload: Dict):
        """Trigger: cron 6h. Officer: Spock. Lint + health check."""
        from WarpCore.skills import validate_payload

        payload = validate_payload("maintenance", payload)
        log("spock", "maintenance", "LINT_START", "wiki", "Beginning logic scan")
        log_lines = []

        # Quick purge of documents whose files vanished under scan roots
        try:
            from db_maintenance import purge_missing_content

            purge_result = purge_missing_content(
                DB_PATH, roots=[str(r) for r in SCAN_ROOTS]
            )
            purged_n = int(purge_result.get("purged") or 0)
            if purged_n:
                log(
                    "spock",
                    "maintenance",
                    "PURGE_MISSING",
                    "system",
                    f"Purged {purged_n} missing document(s)",
                    "YELLOW",
                )
                console(
                    "YELLOW",
                    "spock",
                    "PURGE",
                    f"Removed {purged_n} missing document(s)",
                )
                log_lines.append(f"purged:{purged_n}")
        except Exception as e:
            log("spock", "maintenance", "PURGE_MISSING", "system", str(e), "RED")

        with _connect() as conn:
            # 1. Find orphan pages - no inbound links
            orphans = conn.execute("""
                SELECT d.id, d.path, d.title FROM documents d
                LEFT JOIN links l ON l.dst_doc_id = d.id
                WHERE l.id IS NULL AND d.role!= 'kirk'
            """).fetchall()

            # 2. Find broken links
            broken = conn.execute("""
                SELECT l.id, d.path, l.dst_path FROM links l
                JOIN documents d ON d.id = l.src_doc_id
                WHERE l.is_broken = 1 OR l.dst_doc_id IS NULL AND l.is_external = 0
            """).fetchall()

            # 3. Find stale memory_entities - not mentioned in 90 days
            stale = conn.execute("""
                SELECT id, name FROM memory_entities
                WHERE updated_at < strftime('%s','now','-90 days')
            """).fetchall()

        report = f"# Lint Report {stardate()}\n\n"
        report += (
            f"## Orphan Pages: {len(orphans)}\n"
            + "\n".join(f"- [{t}]({p})" for _, p, t in orphans)
            + "\n\n"
        )
        report += (
            f"## Broken Links: {len(broken)}\n"
            + "\n".join(f"- {p} → {dst}" for _, p, dst in broken)
            + "\n\n"
        )
        report += (
            f"## Stale Entities: {len(stale)}\n"
            + "\n".join(f"- {n}" for _, n in stale)
            + "\n"
        )

        (WIKI_ROOT / "lint_report.md").write_text(report, encoding="utf-8")
        alert = "YELLOW" if orphans or broken else "GREEN"
        log(
            "spock",
            "maintenance",
            "LINT_COMPLETE",
            "wiki",
            f"{len(orphans)} orphans, {len(broken)} broken",
            alert,
        )
        enqueue_skill("update_index", "kirk", {}, priority=9)
        evidence = (
            f"{len(orphans)} orphans, {len(broken)} broken, "
            f"{len(stale)} stale; lint_report.md updated"
        )
        log_lines += [
            f"orphans:{len(orphans)}",
            f"broken:{len(broken)}",
            f"stale:{len(stale)}",
            "lint_report.md",
        ]
        return Skills._result(True, evidence, log_lines)

    @staticmethod
    def backup(payload: Dict):
        """Trigger: cron 2am. Officer: Kirk."""
        from WarpCore.skills import validate_payload

        payload = validate_payload("backup", payload)
        log("kirk", "backup", "START", "repo", "Initiating backup sequence")
        try:
            subprocess.run(["git", "add", "."], cwd=WIKI_ROOT, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"Stardate {stardate()}: Automated backup"],
                cwd=WIKI_ROOT,
                check=True,
            )
            subprocess.run(["git", "push"], cwd=WIKI_ROOT, check=True)
            log("kirk", "backup", "COMPLETE", "repo", "Backup pushed to origin")
            return Skills._result(
                True, "Backup committed and pushed to origin", ["git:commit", "git:push"]
            )
        except subprocess.CalledProcessError as e:
            log("kirk", "backup", "FAILED", "repo", str(e), "RED")
            return Skills._result(False, f"Backup failed: {e}", [f"error:{e}"])

    @staticmethod
    def update_index(payload: Dict):
        """Trigger: after ingest/lint. Officer: Kirk. Regenerates index.md for Obsidian."""
        from WarpCore.skills import validate_payload

        payload = validate_payload("update_index", payload)
        log("kirk", "update_index", "START", "index.md", "Rebuilding content catalog")
        with _connect() as conn:
            rows = conn.execute("""
                SELECT role, title, path, updated_at FROM documents
                ORDER BY role, title COLLATE NOCASE
            """).fetchall()

        content = f"# Index - Stardate {stardate()}\n\n"
        current_role = None
        for role, title, path, updated in rows:
            if role != current_role:
                content += f"\n## {role.title()}\n\n"
                current_role = role
            date = datetime.fromtimestamp(updated).strftime("%Y-%m-%d")
            content += f"- [{title}]({path}) `{date}`\n"

        INDEX_MD.write_text(content, encoding="utf-8")
        log(
            "kirk",
            "update_index",
            "COMPLETE",
            "index.md",
            f"Indexed {len(rows)} documents",
        )
        return Skills._result(
            True, f"index.md updated with {len(rows)} documents", [f"indexed:{len(rows)}"]
        )

    @staticmethod
    def reference_review(payload: Dict):
        """Trigger: user 'research X'. Officer: Away Team. Runs starfleet_away.py"""
        from WarpCore.skills import validate_payload

        payload = validate_payload("reference_review", payload)
        url = payload["url"]
        role = payload.get("role", "kirk")
        log(
            "away_team",
            "reference_review",
            "START",
            url,
            f"Beaming down to acquire source",
        )
        # Calls your SingleFile-lite tool
        result = subprocess.run(
            [sys.executable, str(WIKI_ROOT / "starfleet_away.py"), url, "--role", role],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            saved_path = result.stdout.strip().splitlines()[
                -1
            ]  # script prints path last
            log(
                "away_team",
                "reference_review",
                "COMPLETE",
                url,
                f"Artifact secured: {saved_path}",
            )
            enqueue_skill("onboarding", "scotty", {"path": saved_path}, priority=2)
            return Skills._result(
                True, f"Artifact secured: {saved_path}", [f"saved:{saved_path}"]
            )
        else:
            log("away_team", "reference_review", "FAILED", url, result.stderr, "RED")
            return Skills._result(
                False, f"reference_review failed: {result.stderr}", [f"error:{result.stderr}"]
            )

    @staticmethod
    def acquire_codebase_knowledge(payload: Dict):
        """Map/document a codebase into docs/codebase (awesome-copilot contract).

        Deterministic scan + seven markdown templates. Optionally queues
        onboarding so Wiki Scan / the agent embeds the new docs.
        """
        from WarpCore.skills import validate_payload

        payload = validate_payload("acquire_codebase_knowledge", payload)
        root_path = str(payload.get("root_path") or "").strip()
        focus = str(payload.get("focus") or "").strip()
        output_rel = str(payload.get("output_rel") or "docs/codebase").strip()
        ingest = bool(payload.get("ingest", True))
        if not root_path:
            return Skills._result(False, "root_path is required", ["error:missing_root"])

        log(
            "spock",
            "acquire_codebase_knowledge",
            "START",
            root_path,
            f"Scanning codebase → {output_rel}"
            + (f" (focus: {focus})" if focus else ""),
        )
        try:
            from spock_codebase_knowledge import acquire_codebase_knowledge as run_acquire

            result = run_acquire(
                root_path, focus=focus, output_rel=output_rel or "docs/codebase"
            )
        except Exception as e:
            log(
                "spock",
                "acquire_codebase_knowledge",
                "FAILED",
                root_path,
                str(e),
                "RED",
            )
            return Skills._result(False, f"Acquire failed: {e}", [f"error:{e}"])

        docs = list(result.get("docs") or [])
        evidence = (
            f"Wrote {len(docs)} doc(s) under {result.get('output_dir')} "
            f"(scan={result.get('scan_path')})"
        )
        log_lines = [f"root:{result.get('root')}", f"docs:{len(docs)}"] + [
            f"wrote:{p}" for p in docs
        ]
        if ingest and docs:
            enqueue_skill(
                "onboarding",
                "scotty",
                {"paths": docs, "reprocess": True},
                priority=3,
            )
            log_lines.append(f"queued_onboarding:{len(docs)}")
            evidence += f"; queued onboarding for {len(docs)} file(s)"
        log(
            "spock",
            "acquire_codebase_knowledge",
            "COMPLETE",
            root_path,
            evidence,
        )
        return Skills._result(True, evidence, log_lines)


# --- Agent: The Computer ---
class WikiEventHandler(FileSystemEventHandler):
    """Watchdog handler: new files queued for onboarding, changed files re-queued."""

    def __init__(self, agent):
        self.agent = agent

    def on_created(self, event):
        if event.is_directory:
            return
        self._queue(Path(event.src_path), is_new=True)

    def on_modified(self, event):
        if event.is_directory:
            return
        self._queue(Path(event.src_path), is_new=False)

    def on_deleted(self, event):
        """File/folder removed on disk → purge matching documents from DB."""
        path = Path(event.src_path)
        try:
            from db_maintenance import docs_under_root, purge_documents_by_ids

            with _connect() as conn:
                if event.is_directory:
                    rows = docs_under_root(conn, str(path))
                    ids = [r[0] for r in rows]
                else:
                    rows = conn.execute(
                        "SELECT id FROM documents WHERE path = ?", (str(path),)
                    ).fetchall()
                    if not rows:
                        # try normalized slash variants
                        alt = str(path).replace("/", "\\")
                        rows = conn.execute(
                            "SELECT id FROM documents WHERE path = ? OR path = ?",
                            (str(path), alt),
                        ).fetchall()
                    ids = [r[0] for r in rows]
                if not ids:
                    return
                n = purge_documents_by_ids(conn, ids)
            console(
                "YELLOW",
                "computer",
                "PURGE",
                f"Removed {n} doc(s) for deleted {'dir' if event.is_directory else 'file'}: {path.name}",
            )
            log(
                "spock",
                "maintenance",
                "PURGE_MISSING",
                str(path),
                f"Purged {n} document(s) after delete event",
                "YELLOW",
            )
        except Exception as e:
            console("RED", "computer", "PURGE", f"Failed for {path}: {e}")

    def _queue(self, path: Path, is_new: bool = True):
        # Skip hidden files
        parts = path.parts
        if any(p.startswith('.') for p in parts):
            return
        # Skip non-allowed extensions
        if ALLOWED_EXTENSIONS and path.suffix.lower() not in ALLOWED_EXTENSIONS:
            return
        # Skip configured directories
        if any(d in parts for d in SKIP_DIRS):
            return
        # Skip configured filenames
        if path.name in SKIP_FILENAMES:
            return

        if is_new:
            officer = infer_officer(path)
            enqueue_skill("onboarding", officer, {"path": str(path)}, priority=2)
            return

        # Modified file — check if actually changed
        try:
            with _connect() as conn:
                row = conn.execute(
                    "SELECT file_mtime, file_size, hash_sha256 FROM documents WHERE path = ?",
                    (str(path),)
                ).fetchone()
            if row is None:
                # Not yet indexed — queue as new
                officer = infer_officer(path)
                enqueue_skill("onboarding", officer, {"path": str(path)}, priority=2)
                return
            db_mtime, db_size, db_hash = row
            disk_mtime = int(path.stat().st_mtime)
            disk_size = path.stat().st_size
            if disk_mtime == db_mtime and disk_size == db_size:
                return  # unchanged
            disk_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if disk_hash == db_hash:
                return  # content unchanged
            console("YELLOW", "computer", "WATCHER", f"Changed: {path.name}")
            officer = infer_officer(path)
            enqueue_skill("onboarding", officer, {"path": str(path)}, priority=2)
        except Exception:
            pass


class WikiAgent:
    def __init__(self):
        self.skills = Skills()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="Officer")
        self.running = True
        self.observer = Observer()

        # Wire up file watcher on all SCAN_ROOTS
        handler = WikiEventHandler(self)
        for root in SCAN_ROOTS:
            if root.exists():
                self.observer.schedule(handler, str(root), recursive=True)

    def ship_status(self) -> str:
        """Check for RED_ALERT in last hour"""
        with _connect() as conn:
            row = conn.execute("""
                SELECT 1 FROM captains_log
                WHERE alert_level='RED' AND created_at > strftime('%s','now','-1 hour')
                LIMIT 1
            """).fetchone()
            return "RED_ALERT" if row else "GREEN"

    def get_next_task(self) -> Optional[Tuple]:
        with _connect() as conn:
            row = conn.execute("""
                SELECT id, skill_name, officer, payload_json FROM agent_queue
                WHERE status='pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            """).fetchone()
            if row:
                conn.execute(
                    "UPDATE agent_queue SET status='running', started_at=strftime('%s','now') WHERE id=?",
                    (row[0],),
                )
                return row
        return None

    def execute_task(
        self, task_id: int, skill_name: str, officer: str, payload_json: str
    ):
        from WarpCore.skills import parse_payload_json, validate_payload

        payload = parse_payload_json(payload_json)
        try:
            payload = validate_payload(skill_name, payload)
        except ValueError as ve:
            console("RED", officer, f"  {skill_name}", f"REJECTED — {ve}")
            with _connect() as conn:
                conn.execute(
                    "UPDATE agent_queue SET status='failed', finished_at=strftime('%s','now'), error_msg=? WHERE id=?",
                    (str(ve), task_id),
                )
            log(officer, skill_name, "REJECT", payload, str(ve), "RED")
            return
        target = payload.get("path", payload.get("url", ""))
        if not target and payload.get("paths"):
            target = f"{len(payload['paths'])} files"
        short_target = Path(target).name if target and not str(target).endswith(" files") else str(target or "")
        console("DIM", officer, f"  {skill_name}", short_target)
        try:
            skill_func = getattr(self.skills, skill_name)
            result = skill_func(payload)
            result_json = json.dumps(
                result.to_dict() if hasattr(result, "to_dict") else {"ok": True},
                default=str,
            )
            ok = bool(getattr(result, "ok", True))
            if not ok:
                console("RED", officer, f"  {skill_name}", f"FAILED: {short_target}")
                with _connect() as conn:
                    conn.execute(
                        "UPDATE agent_queue SET status='failed', finished_at=strftime('%s','now'), evidence=?, error_msg=? WHERE id=?",
                        (result_json, str(getattr(result, "evidence", "") or "skill returned ok=false")[:2000], task_id),
                    )
                return
            console("GREEN", officer, f"  {skill_name}", f"done: {short_target}")
            with _connect() as conn:
                try:
                    conn.execute(
                        "UPDATE agent_queue SET status='done', finished_at=strftime('%s','now'), evidence=? WHERE id=?",
                        (result_json, task_id),
                    )
                except sqlite3.OperationalError:
                    conn.execute(
                        "UPDATE agent_queue SET status='done', finished_at=strftime('%s','now') WHERE id=?",
                        (task_id,),
                    )
            if skill_name == "onboarding":
                schedule_index_update()
        except Exception as e:
            console("RED", officer, f"  {skill_name}", f"FAILED: {short_target} — {e}")
            with _connect() as conn:
                conn.execute(
                    "UPDATE agent_queue SET status='failed', finished_at=strftime('%s','now'), error_msg=? WHERE id=?",
                    (str(e), task_id),
                )
            log(officer, skill_name, "CRASH", payload, str(e), "RED")

    def schedule_cron_skills(self):
        """Kirk's duty roster. Run maintenance and backup on schedule."""
        while self.running:
            now = datetime.now()
            # Maintenance every 6h at :00
            if now.minute == 0 and now.hour % 6 == 0:
                enqueue_skill("maintenance", "spock", {}, priority=3)
                console("CYAN", "kirk", "CRON", "Maintenance queued (Spock)")
            # Backup at 02:00
            if now.minute == 0 and now.hour == 2:
                enqueue_skill("backup", "kirk", {}, priority=4)
                console("CYAN", "kirk", "CRON", "Backup queued")
            time.sleep(60)

    def bootstrap_scan(self):
        """Scan: queue un-indexed files, re-queue changed files."""
        log("computer", "agent", "BOOTSTRAP", "system", f"Scanning {len(SCAN_ROOTS)} roots")
        console("CYAN", "computer", "BOOTSTRAP", f"Scanning {len(SCAN_ROOTS)} directories...")

        with _connect() as conn:
            # Clear stale pending entries from previous runs
            stale = conn.execute("DELETE FROM agent_queue WHERE status='pending'").rowcount
            if stale:
                console("DIM", "computer", "PRUNE", f"Cleared {stale} stale queue entries")
            # Stop Scan leaves jobs in 'running'; bootstrap would skip those paths.
            stale_run = conn.execute(
                """
                UPDATE agent_queue
                SET status='failed',
                    finished_at=strftime('%s','now'),
                    error_msg='stale running job at bootstrap'
                WHERE status='running'
                """
            ).rowcount
            if stale_run:
                console(
                    "YELLOW",
                    "computer",
                    "PRUNE",
                    f"Reaped {stale_run} leftover running job(s)",
                )

            # Load existing docs: path -> (mtime, size, hash, needs_embed)
            existing = {}
            for row in conn.execute(
                """
                SELECT path, file_mtime, file_size, hash_sha256,
                       CASE WHEN embedding IS NULL OR length(embedding) = 0
                            THEN 1 ELSE 0 END AS needs_embed
                FROM documents
                """
            ):
                existing[row[0]] = (row[1], row[2], row[3], int(row[4] or 0))

            queued_paths = {json.loads(r[0]).get("path") for r in
                           conn.execute("SELECT payload_json FROM agent_queue WHERE status IN ('pending','running')").fetchall()}

        queued = 0
        updated = 0
        reembed = 0
        skipped = 0
        work: List[str] = []
        for scan_root in SCAN_ROOTS:
            if not scan_root.exists():
                console("YELLOW", "computer", "SKIP", f"Root not found: {scan_root}")
                continue
            for f in scan_root.rglob("*"):
                if not f.is_file():
                    continue
                # Skip hidden dirs
                if any(p.startswith('.') for p in f.parts):
                    continue
                # Skip configured directories
                if any(d in f.parts for d in SKIP_DIRS):
                    continue
                # Skip non-allowed extensions
                if ALLOWED_EXTENSIONS and f.suffix.lower() not in ALLOWED_EXTENSIONS:
                    continue
                # Skip configured filenames
                if f.name in SKIP_FILENAMES:
                    continue

                fpath = str(f)
                if fpath in queued_paths:
                    skipped += 1
                    continue

                if fpath in existing:
                    db_mtime, db_size, db_hash, needs_embed = existing[fpath]
                    disk_mtime = int(f.stat().st_mtime)
                    disk_size = f.stat().st_size
                    content_same = False
                    if disk_mtime == db_mtime and disk_size == db_size:
                        content_same = True
                    else:
                        disk_hash = hashlib.sha256(f.read_bytes()).hexdigest()
                        content_same = disk_hash == db_hash
                    if content_same and not needs_embed:
                        skipped += 1
                        continue
                    if content_same and needs_embed:
                        # Clear Embeddings / model switch left the row without a
                        # vector — re-queue even though the file hash is unchanged.
                        console("CYAN", "computer", "REEMBED", f"Missing vector: {f.name}")
                        work.append(fpath)
                        reembed += 1
                    else:
                        console("YELLOW", "computer", "UPDATE", f"Changed: {f.name}")
                        work.append(fpath)
                        updated += 1
                else:
                    work.append(fpath)
                    queued += 1
                queued_paths.add(fpath)

        if work:
            # reprocess=True when any row needs a vector despite unchanged bytes;
            # extractor also refuses to skip NULL embeddings, but the flag keeps
            # CLI/batch path explicit if prepare_document logic diverges.
            payload: Dict = {"paths": work}
            if reembed:
                payload["reprocess"] = True
            enqueue_skill(
                "onboarding",
                "scotty",
                payload,
                priority=3,
            )

        log("computer", "agent", "BOOTSTRAP_COMPLETE", "system",
            f"Queued {queued} new, {updated} changed, {reembed} missing-embed, "
            f"{skipped} unchanged ({len(work)} file ingest job)")
        console("GREEN", "computer", "BOOTSTRAP",
                f"Queued {queued} new, {updated} changed, {reembed} missing-embed, "
                f"{skipped} unchanged as {1 if work else 0} ingest job")

        # Quick purge: DB rows under scan roots whose files are gone
        try:
            from db_maintenance import purge_missing_content

            result = purge_missing_content(DB_PATH, roots=[str(r) for r in SCAN_ROOTS])
            purged = int(result.get("purged") or 0)
            if purged:
                console(
                    "YELLOW",
                    "computer",
                    "PURGE",
                    f"Removed {purged} missing document(s) (checked {result.get('checked')})",
                )
                log(
                    "spock",
                    "maintenance",
                    "PURGE_MISSING",
                    "system",
                    f"Bootstrap purged {purged} missing docs",
                    "YELLOW",
                )
            else:
                console("DIM", "computer", "PURGE", "No missing documents under scan roots")
        except Exception as e:
            console("RED", "computer", "PURGE", f"Missing-content purge failed: {e}")

    def _queue_busy(self) -> bool:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM agent_queue
                WHERE status IN ('pending', 'running')
                """
            ).fetchone()
        return bool(row and int(row[0] or 0) > 0)

    def _drain_queue_until_idle(self, *, idle_confirm: int = 2) -> None:
        """Run pending/running skills until the queue stays empty."""
        empty_streak = 0
        while self.running:
            task = self.get_next_task()
            if task:
                empty_streak = 0
                self.execute_task(*task)
                continue
            empty_streak += 1
            if empty_streak >= idle_confirm and not self._queue_busy():
                return
            time.sleep(1)

    def run(self, *, once: bool = False):
        if not acquire_agent_lock():
            return

        mode = "once (exit when idle)" if once else "continuous (watch until stop)"
        console(
            "CYAN",
            "computer",
            "BOOT",
            f"USS Wikiprise online — {len(SCAN_ROOTS)} roots · mode={mode}",
        )
        ext_label = (
            ",".join(sorted(ALLOWED_EXTENSIONS))
            if ALLOWED_EXTENSIONS
            else "(all types)"
        )
        console("CYAN", "computer", "FILTER", f"Extensions: {ext_label}")
        log(
            "computer",
            "agent",
            "BOOT",
            "system",
            f"Ship computer online. Filter={ext_label} mode={'once' if once else 'continuous'}",
        )

        observer_started = False
        try:
            # Initial scan first — then start watcher (continuous only) so bootstrap
            # I/O does not race with on_created/on_modified and double-queue paths.
            self.bootstrap_scan()

            if once:
                console(
                    "CYAN",
                    "computer",
                    "MODE",
                    "Scan-once: draining ingest queue (no file watcher)",
                )
                self._drain_queue_until_idle()
                with _connect() as conn:
                    docs = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
                    done = conn.execute(
                        "SELECT count(*) FROM agent_queue WHERE status='done'"
                    ).fetchone()[0]
                    failed = conn.execute(
                        "SELECT count(*) FROM agent_queue WHERE status='failed'"
                    ).fetchone()[0]
                if failed:
                    console(
                        "YELLOW",
                        "computer",
                        "SCAN_COMPLETE",
                        f"Finished with failures · Docs: {docs} · done: {done} · failed: {failed}",
                    )
                else:
                    console(
                        "GREEN",
                        "computer",
                        "SCAN_COMPLETE",
                        f"Bootstrap + index finished · Docs: {docs} · Queue done: {done}",
                    )
                log(
                    "computer",
                    "agent",
                    "SCAN_COMPLETE",
                    "system",
                    f"once-mode complete docs={docs} done={done} failed={failed}",
                    "YELLOW" if failed else "GREEN",
                )
                self.running = False
                return

            self.observer.start()
            observer_started = True
            console(
                "GREEN",
                "computer",
                "WATCHER",
                f"File observer active on {len(SCAN_ROOTS)} roots "
                "(continuous — use Stop Scan to exit)",
            )

            # Start cron scheduler
            threading.Thread(target=self.schedule_cron_skills, daemon=True).start()

            # Main loop
            loop_count = 0
            announced_idle = False
            while self.running:
                try:
                    task = self.get_next_task()
                    if task:
                        announced_idle = False
                        self.execute_task(*task)
                    else:
                        loop_count += 1
                        if loop_count % 12 == 0:  # Every ~60s
                            with _connect() as conn:
                                pending = conn.execute(
                                    "SELECT count(*) FROM agent_queue WHERE status='pending'"
                                ).fetchone()[0]
                                done = conn.execute(
                                    "SELECT count(*) FROM agent_queue WHERE status='done'"
                                ).fetchone()[0]
                                docs = conn.execute(
                                    "SELECT count(*) FROM documents"
                                ).fetchone()[0]
                            if pending == 0 and not announced_idle:
                                console(
                                    "GREEN",
                                    "computer",
                                    "IDLE",
                                    "Queue empty — watching for file changes "
                                    "(Stop Scan to exit)",
                                )
                                announced_idle = True
                            console(
                                "DIM",
                                "computer",
                                "STATUS",
                                f"Queue: {pending} pending, {done} done | Docs: {docs}",
                            )
                            loop_count = 0
                    time.sleep(5)
                except KeyboardInterrupt:
                    self.running = False
                    console("YELLOW", "computer", "SHUTDOWN", "Ship computer powering down")
                    log(
                        "computer",
                        "agent",
                        "SHUTDOWN",
                        "system",
                        "Ship computer powering down",
                    )
        finally:
            if observer_started:
                self.observer.stop()
                self.observer.join()
            release_agent_lock()


def _parse_once_flag(argv: List[str]) -> bool:
    """True = scan once and exit; False = continuous watch."""
    args = [a.lower() for a in argv[1:]]
    if "--continuous" in args or "-c" in args:
        return False
    if "--once" in args or "-1" in args:
        return True
    env = (os.environ.get("SPOCK_WIKI_MODE") or "").strip().lower()
    if env in ("once", "oneshot", "one-shot", "1"):
        return True
    if env in ("continuous", "watch", "daemon", "0"):
        return False
    # Default for bare CLI remains continuous (daemon); GUI passes --once/--continuous.
    return False


if __name__ == "__main__":
    agent = WikiAgent()
    agent.run(once=_parse_once_flag(sys.argv))
