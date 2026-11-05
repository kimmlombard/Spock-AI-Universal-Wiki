"""WarpCore: Spock_Console settings store in ships_computer.db.

Replaces the root-level app_config.json / scan_config.json / config.json /
wiki_agent_session.json files with a normalized key/value table. Pure sqlite —
safe for the GUI, wizard, CLI, and subprocesses (wiki_agent, extractor, RAG
API, MCP server).

Schema:
    Spock_Console(
        key_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        Variable_Name  TEXT UNIQUE NOT NULL,
        Variable_Value TEXT NOT NULL,          -- JSON-encoded
        Variable_Type  TEXT NOT NULL,          -- str|int|float|bool|json|list|secret
        updated_at     TEXT,
        updated_by     TEXT                    -- 'app'|'wizard'|'maintenance'|'wiki_agent'
    )
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .db import connect, table_exists
from .config_defaults import (
    DEFAULT_APP_CONFIG,
    DEFAULT_CTX_SETTINGS,
    DEFAULT_SCAN_CONFIG,
    flatten_config,
    infer_type,
    merge_ctx_settings,
    merge_embedding_profile,
    merge_launch_settings,
    merge_mcp_settings,
    merge_search_config,
    merge_uieg_config,
)
from . import secrets as _secrets

SCHEMA = """
CREATE TABLE IF NOT EXISTS Spock_Console (
    key_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    Variable_Name  TEXT UNIQUE NOT NULL,
    Variable_Value TEXT NOT NULL,
    Variable_Type  TEXT NOT NULL,
    updated_at     TEXT,
    updated_by     TEXT
);
CREATE TABLE IF NOT EXISTS config (
    key         TEXT PRIMARY KEY,
    value_json  TEXT NOT NULL,
    updated_at  TEXT,
    updated_by  TEXT
);
"""

# JSON files that the migration archives after a successful import.
SOURCE_FILES = (
    "app_config.json",
    "scan_config.json",
    "config.json",
    "wiki_agent_session.json",
)

CONFIG_ARCHIVE_DIR = "config_archive"

# key → name of the config file it migrates from
_FILE_NAMESPACES: Dict[str, str] = {
    "app_config.json": "app",
    "scan_config.json": "scan",
    "config.json": "hf",
    "wiki_agent_session.json": "wiki_agent.session",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_schema(db_path: str) -> None:
    from .db import ensure_schema

    if not table_exists(db_path, "Spock_Console"):
        ensure_schema(db_path, SCHEMA)
    from .ship_schema import ensure_ship_computer_schema

    ensure_ship_computer_schema(db_path)


def _stash_secret(name: str, value: Any) -> Any:
    """Persist secret in the OS keyring; SQLite keeps a placeholder when that works."""
    text = "" if value is None else str(value)
    if _secrets.is_placeholder(text):
        return _secrets.PLACEHOLDER
    if not text:
        _secrets.put(name, "")
        return ""
    if _secrets.put(name, text):
        return _secrets.PLACEHOLDER
    return text


def _read_secret(db_path: str, name: str, value: Any) -> str:
    stored = "" if value is None else (value if isinstance(value, str) else str(value))
    keyed = _secrets.get(name)
    if stored and not _secrets.is_placeholder(stored):
        if stored != keyed and _secrets.put(name, stored):
            _replace_secret_cell(db_path, name, _secrets.PLACEHOLDER)
        return stored
    if keyed:
        return keyed
    return "" if _secrets.is_placeholder(stored) else stored


def _replace_secret_cell(db_path: str, name: str, stored: str) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            UPDATE Spock_Console
            SET Variable_Value = ?, Variable_Type = 'secret', updated_at = ?
            WHERE Variable_Name = ?
            """,
            (json.dumps(stored), _now(), name),
        )
        conn.commit()
    finally:
        conn.close()


def set(db_path: str, name: str, value: Any, by: str = "app") -> None:
    """Store one setting. Converts via infer_type unless a known type wins."""
    _ensure_schema(db_path)
    vtype = infer_type(name, value)
    if vtype == "secret":
        value = _stash_secret(name, value)
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO Spock_Console (Variable_Name, Variable_Value, Variable_Type, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(Variable_Name) DO UPDATE SET
                Variable_Value = excluded.Variable_Value,
                Variable_Type  = excluded.Variable_Type,
                updated_at     = excluded.updated_at,
                updated_by     = excluded.updated_by
            """,
            (name, json.dumps(value), vtype, _now(), by),
        )
        conn.commit()
    finally:
        conn.close()


def set_many(db_path: str, mapping: Dict[str, Any], by: str = "app") -> None:
    _ensure_schema(db_path)
    conn = connect(db_path)
    try:
        now = _now()
        for name, value in mapping.items():
            vtype = infer_type(name, value)
            if vtype == "secret":
                value = _stash_secret(name, value)
            conn.execute(
                """
                INSERT INTO Spock_Console (Variable_Name, Variable_Value, Variable_Type, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(Variable_Name) DO UPDATE SET
                    Variable_Value = excluded.Variable_Value,
                    Variable_Type  = excluded.Variable_Type,
                    updated_at     = excluded.updated_at,
                    updated_by     = excluded.updated_by
                """,
                (name, json.dumps(value), vtype, now, by),
            )
        conn.commit()
    finally:
        conn.close()


def get(db_path: str, name: str, default: Any = None) -> Any:
    _ensure_schema(db_path)
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT Variable_Value, Variable_Type FROM Spock_Console WHERE Variable_Name=?",
            (name,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return default
    decoded = _decode(row[0], row[1])
    if row[1] == "secret":
        return _read_secret(db_path, name, decoded)
    return decoded


def has(db_path: str, name: str) -> bool:
    _ensure_schema(db_path)
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM Spock_Console WHERE Variable_Name=?", (name,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def delete(db_path: str, name: str) -> bool:
    _ensure_schema(db_path)
    vtype = None
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT Variable_Type FROM Spock_Console WHERE Variable_Name=?",
            (name,),
        ).fetchone()
        if row:
            vtype = row[0]
        cur = conn.execute(
            "DELETE FROM Spock_Console WHERE Variable_Name=?", (name,)
        )
        conn.commit()
        removed = cur.rowcount > 0
    finally:
        conn.close()
    if vtype == "secret" or infer_type(name, "") == "secret":
        _secrets.put(name, "")
    return removed


def get_all(db_path: str, prefix: str = "") -> Dict[str, Any]:
    """Return {Variable_Name: value} rows; optional namespace filter."""
    _ensure_schema(db_path)
    conn = connect(db_path)
    try:
        if prefix:
            rows = conn.execute(
                "SELECT Variable_Name, Variable_Value, Variable_Type FROM Spock_Console WHERE Variable_Name LIKE ? ORDER BY Variable_Name",
                (prefix + "%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT Variable_Name, Variable_Value, Variable_Type FROM Spock_Console ORDER BY Variable_Name"
            ).fetchall()
    finally:
        conn.close()
    out: Dict[str, Any] = {}
    for r in rows:
        decoded = _decode(r[1], r[2])
        if r[2] == "secret":
            decoded = _read_secret(db_path, r[0], decoded)
        out[r[0]] = decoded
    return out


def get_meta(db_path: str) -> List[Tuple[str, str, str, str, str]]:
    """Return all rows as (Variable_Name, Variable_Type, value_repr, updated_at, updated_by).

    value_repr is JSON-dumped value; secret rows are masked unless reveal=True.
    """
    _ensure_schema(db_path)
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT Variable_Name, Variable_Value, Variable_Type, updated_at, updated_by FROM Spock_Console ORDER BY Variable_Name"
        ).fetchall()
    finally:
        conn.close()
    return [(r[0], r[2], r[1], r[3], r[4]) for r in rows]


def _decode(value_json: str, vtype: str) -> Any:
    try:
        value = json.loads(value_json)
    except (TypeError, ValueError):
        return value_json
    if vtype == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if vtype == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if vtype == "bool":
        return bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes")
    return value


def _flatten_file(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Namespace a JSON file's contents into dotted keys for the store."""
    flat: Dict[str, Any] = {}
    ns = _FILE_NAMESPACES.get(name)
    if name == "wiki_agent_session.json":
        # Store the whole session blob under a single key.
        flat["wiki_agent.session"] = data if isinstance(data, dict) else {}
        return flat
    if name == "config.json":
        # {"hf_token": ...} → hf.token
        for k, v in data.items():
            suffix = k.removeprefix("hf_") if k.startswith("hf_") else k
            flat[f"hf.{suffix}"] = v
        return flat
    if ns:
        flat.update(flatten_config(data, prefix=ns))
    else:
        flat.update(flatten_config(data))
    return flat


def migrate_from_json(db_path: str, root: Optional[str] = None, archive: bool = True) -> Dict[str, Any]:
    """One-time, idempotent import of root JSON config files into Spock_Console.

    Returns a report dict. If 'migrated' already set (a row exists with any
    'app.'-prefixed key), does nothing. Archives originals to config_archive/.
    """
    root = root or str(Path.cwd())
    root_path = Path(root)
    report: Dict[str, Any] = {"imported": 0, "archived": [], "skipped": []}

    if has(db_path, "app.theme"):
        report["skipped"] = ["already migrated"]
        return report

    _ensure_schema(db_path)
    all_rows: Dict[str, Any] = {}

    for fname in SOURCE_FILES:
        fpath = root_path / fname
        if not fpath.exists():
            report["skipped"].append(f"{fname} (missing)")
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                report["skipped"].append(f"{fname} (not an object)")
                continue
        except (OSError, json.JSONDecodeError):
            report["skipped"].append(f"{fname} (unreadable)")
            continue
        all_rows.update(_flatten_file(fname, data))
        report["imported"] += 1

    # Merge with defaults so every expected key exists even when a file is thin.
    defaults = flatten_config(DEFAULT_APP_CONFIG, prefix="app")
    defaults.update(flatten_config(DEFAULT_SCAN_CONFIG, prefix="scan"))
    for key, value in defaults.items():
        all_rows.setdefault(key, value)

    set_many(db_path, all_rows, by="migration")
    set(db_path, "settings.migrated_at", _now(), by="migration")

    if archive:
        archive_dir = root_path / CONFIG_ARCHIVE_DIR
        archive_dir.mkdir(parents=True, exist_ok=True)
        for fname in SOURCE_FILES:
            fpath = root_path / fname
            if fpath.exists():
                try:
                    dest = archive_dir / fname
                    shutil.move(str(fpath), str(dest))
                    report["archived"].append(str(dest))
                except OSError:
                    report["skipped"].append(f"{fname} (archive failed)")
    return report


def export_to_json(db_path: str, out_dir: str) -> Dict[str, str]:
    """Write current store contents back to app_config.json / scan_config.json /
    config.json / wiki_agent_session.json for backup/rollback. Returns paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    all_rows = get_all(db_path)

    def take(prefix: str) -> Dict[str, Any]:
        nested: Dict[str, Any] = {}
        for key, value in all_rows.items():
            if key.startswith(prefix + "."):
                parts = key[len(prefix) + 1:].split(".")
                node = nested
                for p in parts[:-1]:
                    node = node.setdefault(p, {})
                node[parts[-1]] = value
        return nested

    app = take("app")
    scan = take("scan")
    session = all_rows.get("wiki_agent.session", {})

    # Restore nested defaults so exported app_config looks like the original shape.
    app["embedding_profile"] = merge_embedding_profile(app.get("embedding_profile"))
    app["mcp"] = merge_mcp_settings(app.get("mcp"))
    app["search"] = merge_search_config(app.get("search"))
    app["uieg"] = merge_uieg_config(app.get("uieg"))
    app["ctx"] = merge_ctx_settings(app.get("ctx") if isinstance(app.get("ctx"), dict) else None)
    app["launch"] = merge_launch_settings(
        app.get("launch") if isinstance(app.get("launch"), dict) else None
    )
    if "rag_api" in all_rows:
        app["rag_api"] = all_rows["rag_api"]

    app["openai_compat_api_key"] = ""
    app["lm_studio_key"] = ""
    if isinstance(app.get("rag_api"), dict):
        app["rag_api"]["api_key"] = ""
    if isinstance(app.get("search"), dict):
        app["search"]["github_token"] = ""
        app["search"]["brave_api_key"] = ""

    written: Dict[str, str] = {}
    for fname, payload in (
        ("app_config.json", app),
        ("scan_config.json", scan),
        ("config.json", {"hf_token": ""}),
        ("wiki_agent_session.json", session),
    ):
        dest = out / fname
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        written[fname] = str(dest)
    return written


def ensure_paths_healed(db_path: str, root: Optional[str] = None) -> Dict[str, Any]:
    """Remap Spock_Console paths when the DB was copied across Linux/Windows roots."""
    try:
        from WarpCore.path_relocate import heal_relocated_paths

        return heal_relocated_paths(
            db_path,
            root=Path(root).resolve() if root else Path(db_path).resolve().parent,
            by="path_relocate",
        )
    except Exception as exc:  # pragma: no cover — never block app start
        return {"ok": False, "error": str(exc), "changed": []}


def load_app_config(db_path: str) -> Dict[str, Any]:
    """Return the full app config dict (defaults merged), mirroring old load_config()."""
    ensure_paths_healed(db_path)
    if not has(db_path, "app.theme"):
        return dict(DEFAULT_APP_CONFIG)
    rows = get_all(db_path, prefix="app.")
    config = dict(DEFAULT_APP_CONFIG)

    def nest(prefix: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in rows.items():
            if key.startswith(prefix + "."):
                parts = key[len(prefix) + 1:].split(".")
                node = out
                for p in parts[:-1]:
                    node = node.setdefault(p, {})
                node[parts[-1]] = value
        return out

    for top, sub in (
        ("embedding_profile", None),
        ("rag_api", None),
        ("mcp", None),
        ("search", None),
        ("uieg", None),
        ("ctx", None),
        ("launch", None),
    ):
        sub_dict = nest(f"app.{top}") if top else None
        if top == "embedding_profile":
            config["embedding_profile"] = merge_embedding_profile(sub_dict)
        elif top == "mcp":
            config["mcp"] = merge_mcp_settings(sub_dict)
        elif top == "search":
            config["search"] = merge_search_config(sub_dict)
        elif top == "uieg":
            config["uieg"] = merge_uieg_config(sub_dict)
        elif top == "rag_api":
            if sub_dict:
                config["rag_api"] = sub_dict
        elif top == "ctx":
            config["ctx"] = merge_ctx_settings(sub_dict)
        elif top == "launch":
            config["launch"] = merge_launch_settings(sub_dict)

    nested = {
        "embedding_profile",
        "rag_api",
        "mcp",
        "search",
        "uieg",
        "ctx",
        "launch",
    }
    for key, value in rows.items():
        if not key.startswith("app."):
            continue
        short = key[4:]
        if not short or short in nested or "." in short:
            continue
        config[short] = value
    return config


def save_app_config(db_path: str, config: Dict[str, Any], by: str = "app") -> None:
    """Persist a full app config dict back into the store."""
    flat = flatten_config(config, prefix="app")
    set_many(db_path, flat, by=by)


def load_scan_config(db_path: str) -> Dict[str, Any]:
    ensure_paths_healed(db_path)
    if not has(db_path, "scan.scan_roots"):
        return dict(DEFAULT_SCAN_CONFIG)
    rows = get_all(db_path, prefix="scan.")
    cfg = dict(DEFAULT_SCAN_CONFIG)
    for key, value in rows.items():
        short = key[len("scan."):]
        if short in cfg:
            cfg[short] = value
    return cfg


def ensure_ctx_defaults_in_store(
    db_path: str,
    *,
    by: str = "ctx_defaults",
) -> Dict[str, Any]:
    """Fill missing app.ctx.* keys so Maintenance Ctx filter has rows to edit."""
    _ensure_schema(db_path)
    filled: List[str] = []
    flat = flatten_config({"ctx": dict(DEFAULT_CTX_SETTINGS)}, prefix="app")
    for key, value in flat.items():
        if _fill_if_empty(db_path, key, value, by=by):
            filled.append(key)
    return {"filled": filled, "keys": len(flat)}


def ensure_scan_in_store(
    db_path: str,
    root: Optional[str] = None,
    *,
    by: str = "scan_import",
) -> Dict[str, Any]:
    """Import scan.* into Spock_Console when missing (JSON left behind after app-only migrate).

    Prefer ``scan_config.json`` under ``root`` when present; otherwise seed DEFAULT_SCAN_CONFIG.
    Idempotent when ``scan.scan_roots`` already exists.
    """
    report: Dict[str, Any] = {"imported": False, "source": None, "keys": 0}
    if has(db_path, "scan.scan_roots"):
        report["source"] = "db"
        report["keys"] = len(get_all(db_path, prefix="scan."))
        return report

    cfg = dict(DEFAULT_SCAN_CONFIG)
    root_path = Path(root or Path.cwd())
    json_path = root_path / "scan_config.json"
    if json_path.is_file():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for key in DEFAULT_SCAN_CONFIG:
                    if key in data:
                        cfg[key] = data[key]
                report["source"] = str(json_path)
            else:
                report["source"] = "defaults"
        except (OSError, json.JSONDecodeError):
            report["source"] = "defaults"
    else:
        report["source"] = "defaults"

    save_scan_config(db_path, cfg, by=by)
    report["imported"] = True
    report["keys"] = len(flatten_config(cfg, prefix="scan"))
    return report


def _parse_dotenv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def _setting_is_empty(db_path: str, name: str) -> bool:
    if not has(db_path, name):
        return True
    value = get(db_path, name, None)
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False


def _fill_if_empty(db_path: str, name: str, value: Any, *, by: str) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if not _setting_is_empty(db_path, name):
        return False
    set(db_path, name, value, by=by)
    return True


def ensure_live_overlays_in_store(
    db_path: str,
    root: Optional[str] = None,
    *,
    by: str = "overlay_import",
) -> Dict[str, Any]:
    """Bring leftover onboarding files into Spock_Console (fill-if-empty / missing only).

    Sources:
      - scan_config.json → scan.*
      - wiki_agent_session.json → wiki_agent.session
      - .env / .HF_TOKEN / process env → hf.token + API keys + embedding profile
      - first_models_last.json → model paths / llama-server path when empty

    Skips spock_ready_last.json (ephemeral readiness status, not settings).
    """
    root_path = Path(root or Path.cwd())
    report: Dict[str, Any] = {
        "scan": {},
        "wiki_session": False,
        "hf_token_row": False,
        "filled": [],
        "skipped_status_json": ["spock_ready_last.json"],
    }

    report["scan"] = ensure_scan_in_store(db_path, root=str(root_path), by=by)

    session_path = root_path / "wiki_agent_session.json"
    if not has(db_path, "wiki_agent.session") and session_path.is_file():
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                set(db_path, "wiki_agent.session", data, by=by)
                report["wiki_session"] = True
                report["filled"].append("wiki_agent.session")
        except (OSError, json.JSONDecodeError):
            pass

    env_map = _parse_dotenv(root_path / ".env")
    # Process env wins over file for secrets (same order as pick.resolve_hf_token).
    for env_key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "SPOCK_HF_TOKEN"):
        if os.environ.get(env_key, "").strip():
            env_map[env_key] = os.environ.get(env_key, "").strip()
    hf_file = root_path / ".HF_TOKEN"
    if hf_file.is_file():
        try:
            tok = hf_file.read_text(encoding="utf-8").strip()
            if tok:
                env_map.setdefault("HF_TOKEN", tok)
        except OSError:
            pass

    hf_token = (
        env_map.get("HF_TOKEN")
        or env_map.get("HUGGING_FACE_HUB_TOKEN")
        or env_map.get("SPOCK_HF_TOKEN")
        or ""
    ).strip()
    if not has(db_path, "hf.token"):
        # Prefer env; else re-materialize a visible row from keyring if present.
        existing = (_secrets.get("hf.token") or "").strip()
        set(db_path, "hf.token", hf_token or existing or "", by=by)
        report["hf_token_row"] = True
        report["filled"].append("hf.token")
    elif hf_token and _setting_is_empty(db_path, "hf.token"):
        set(db_path, "hf.token", hf_token, by=by)
        report["filled"].append("hf.token")

    secret_fills = (
        ("GITHUB_TOKEN", "app.search.github_token"),
        ("BRAVE_API_KEY", "app.search.brave_api_key"),
        ("OPENAI_API_KEY", "app.openai_compat_api_key"),
        ("LM_STUDIO_API_KEY", "app.lm_studio_key"),
    )
    for env_key, store_key in secret_fills:
        val = (os.environ.get(env_key) or env_map.get(env_key) or "").strip()
        if _fill_if_empty(db_path, store_key, val, by=by):
            report["filled"].append(store_key)

    emb_fills = (
        ("EMBEDDINGS_URL", "app.embedding_profile.embeddings_url", str),
        ("EMBEDDINGS_DIM", "app.embedding_profile.embeddings_dim", int),
        ("EMBEDDINGS_TRUNCATE", "app.embedding_profile.truncate_chars", int),
        ("EMBEDDINGS_BATCH_CHUNK", "app.embedding_profile.batch_chunk", int),
        ("EMBEDDINGS_BATCH_WORKERS", "app.embedding_profile.batch_workers", int),
    )
    for env_key, store_key, caster in emb_fills:
        raw = (os.environ.get(env_key) or env_map.get(env_key) or "").strip()
        if not raw:
            continue
        try:
            value: Any = caster(raw) if caster is not str else raw
        except (TypeError, ValueError):
            continue
        if _fill_if_empty(db_path, store_key, value, by=by):
            report["filled"].append(store_key)

    llama_path = (
        os.environ.get("LLAMA_SERVER_PATH") or env_map.get("LLAMA_SERVER_PATH") or ""
    ).strip()
    if _fill_if_empty(db_path, "app.mcp.llama_server_path", llama_path, by=by):
        report["filled"].append("app.mcp.llama_server_path")

    models_path = root_path / "first_models_last.json"
    if models_path.is_file():
        try:
            with open(models_path, "r", encoding="utf-8") as f:
                pick = json.load(f)
        except (OSError, json.JSONDecodeError):
            pick = None
        if isinstance(pick, dict):
            model_fills = (
                ("embed_gguf_path", "app.embedding_profile.model_path"),
                ("embed_model_id", "app.embedding_profile.model_id"),
                ("llama_server_path", "app.mcp.llama_server_path"),
            )
            for src, dest in model_fills:
                val = str(pick.get(src) or "").strip()
                if _fill_if_empty(db_path, dest, val, by=by):
                    report["filled"].append(dest)
            # Persist pick snapshot once for audit (not a runtime setting).
            if not has(db_path, "onboarding.first_models"):
                set(db_path, "onboarding.first_models", pick, by=by)
                report["filled"].append("onboarding.first_models")

    return report


def save_scan_config(db_path: str, cfg: Dict[str, Any], by: str = "maintenance") -> None:
    flat = flatten_config(cfg, prefix="scan")
    set_many(db_path, flat, by=by)


def get_hf_token(db_path: str) -> Optional[str]:
    token = str(get(db_path, "hf.token", "") or "").strip()
    if token:
        return token
    keyed = _secrets.get("hf.token").strip()
    return keyed or None
