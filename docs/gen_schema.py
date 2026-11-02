"""Auto-generate accurate SQLite schema pages from the live databases.

For each configured DB file this introspects (read-only):
  - table/view list from sqlite_master
  - column metadata via PRAGMA table_info
  - foreign keys via PRAGMA foreign_key_list
  - indexes via PRAGMA index_list / index_info
  - row counts

Outputs `structure/database-schema.md` with a Mermaid ER diagram plus a
per-table breakdown. Registered in mkdocs.yml under `plugins.gen-files.scripts`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent

DATABASES = [
    "ship_computer.db",
    "uieg_capture.db",
]

# sqlite_* / *_fts_* internals that add noise.
INTERNAL_PREFIXES = ("sqlite_", "docs_fts_")


def _connect_readonly(db: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)


def introspect(db: str) -> dict | None:
    rel = str(Path(db))
    path = ROOT / rel
    if not path.is_file():
        return None
    try:
        con = _connect_readonly(rel)
    except (sqlite3.Error, OSError):
        return None
    info: dict = {"db": rel, "size": path.stat().st_size, "tables": []}
    try:
        rows = con.execute(
            "SELECT name, type, sql FROM sqlite_master "
            "WHERE type IN ('table','view') ORDER BY name"
        ).fetchall()
        with con:
            for name, typ, sql in rows:
                if name.startswith(INTERNAL_PREFIXES):
                    continue
                col_rows = []
                try:
                    col_rows = con.execute(f"PRAGMA table_info('{_q(name)}')").fetchall()
                except sqlite3.Error:
                    col_rows = []
                columns = [
                    {
                        "name": c[1],
                        "type": c[2] or "?",
                        "notnull": bool(c[3]),
                        "default": c[4],
                        "pk": c[5],
                    }
                    for c in col_rows
                ]
                fks = []
                for fk in con.execute(f"PRAGMA foreign_key_list('{_q(name)}')").fetchall():
                    fks.append(
                        {
                            "column": fk[3],
                            "ref_table": fk[2],
                            "ref_column": fk[4],
                        }
                    )
                indexes = []
                for idx in con.execute(f"PRAGMA index_list('{_q(name)}')").fetchall():
                    idx_name = idx[1]
                    cols = []
                    for ic in con.execute(f"PRAGMA index_info('{_q(idx_name)}')").fetchall():
                        cols.append(ic[2])
                    indexes.append(
                        {
                            "name": idx_name,
                            "unique": bool(idx[2]),
                            "columns": cols,
                        }
                    )
                count = None
                if typ == "table":
                    try:
                        count = con.execute(
                            f"SELECT COUNT(*) FROM '{_q(name)}'"
                        ).fetchone()[0]
                    except sqlite3.Error:
                        count = None
                info["tables"].append(
                    {
                        "name": name,
                        "kind": typ,
                        "sql": sql,
                        "columns": columns,
                        "fks": fks,
                        "indexes": indexes,
                        "count": count,
                    }
                )
    except sqlite3.Error:
        con.close()
        return None
    con.close()
    return info


def _q(name: str) -> str:
    """Sqlite-safe single identifier (hash-table style)."""
    hashmap_ = {39: 2 * 39}
    return name.translate(hashmap_)


def _er_diagram(tables: list[dict]) -> str:
    lines = ["```mermaid", "erDiagram"]
    for t in tables:
        lines.append(f"    {_ent_name(t['name'])} {{")
        for c in t["columns"]:
            pk = c["pk"] != 0
            mm = "PK" if pk else ""
            fk = next(
                (f for f in t["fks"] if f["column"] == c["name"]), None
            )
            if fk:
                mm = "FK" if not pk else "PK, FK"
            key = f"{mm} " if mm else ""
            lines.append(f"        {c['type']} {c['name']} {key}".strip())
        lines.append("    }")
    for t in tables:
        for fk in t["fks"]:
            lines.append(
                f"    {_ent_name(t['name'])} ||--o{{ {_ent_name(fk['ref_table'])} : \"{fk['column']}\""
            )
    lines.append("```")
    return "\n".join(lines)


def _ent_name(name: str) -> str:
    keep = "".join(ch for ch in name if ch.isalnum() or ch == "_")
    if not keep or keep[0].isdigit():
        keep = "_" + keep
    return keep.title().replace("_", "")


def render_page() -> str:
    dbs = [introspect(d) for d in DATABASES if introspect(d)]
    out = [
        "# Database Schema (generated)",
        "",
        "Factual schema extracted live from the SQLite files via `sqlite_master`, "
        "`PRAGMA table_info`, `PRAGMA foreign_key_list` and `PRAGMA index_list`. "
        "Kept separate from the hand-written `architecture/database-schema.md` so "
        "this page always reflects the **actual** tables.",
        "",
        f"Monitored databases: {', '.join(f'`{d['db']}`' for d in dbs)}",
        "",
    ]
    for d in dbs:
        out.append(f"## {d['db']}")
        out.append("")
        out.append(
            f"{d['size'] / 1024 / 1024:.1f} MB · {len(d['tables'])} tables/views"
        )
        out.append("")
        out.append(_er_diagram(d["tables"]))
        out.append("")
        out.append("### Table details")
        out.append("")
        for t in d["tables"]:
            out.append(f"#### `{t['name']}` ({t['kind']})")
            out.append("")
            if t["count"] is not None:
                out.append(f"Rows: `{t['count']:,}`")
                out.append("")
            out.append("| Column | Type | PK | Not Null | Default | FK → |")
            out.append("|--------|------|----|----------|---------|------|")
            for c in t["columns"]:
                fks = [f"{f['ref_table']}.{f['ref_column']}" for f in t["fks"] if f["column"] == c["name"]]
                out.append(
                    f"| {c['name']} | {c['type']} | {'✓' if c['pk'] else ''} | "
                    f"{'✓' if c['notnull'] else ''} | {c['default'] or ''} | {', '.join(fks)} |"
                )
            if t["indexes"]:
                out.append("")
                out.append("Indexes:")
                out.append("")
                for ix in t["indexes"]:
                    uniq = " UNIQUE" if ix["unique"] else ""
                    out.append(
                        f"- `{ix['name']}`{uniq}: {', '.join(ix['columns'])}"
                    )
            if t["sql"]:
                out.append("")
                out.append("<details><summary>DDL</summary>")
                out.append("")
                out.append("```sql")
                out.append((t["sql"] or "").strip())
                out.append("```")
                out.append("")
                out.append("</details>")
            out.append("")
    return "\n".join(out)


def main() -> None:
    with mkdocs_gen_files.open("structure/database-schema.md", "w") as fd:
        fd.write(render_page())


if __name__ in ("__main__", "<run_path>"):  # direct run, or mkdocs-gen-files runpy
    main()