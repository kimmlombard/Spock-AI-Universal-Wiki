# Logic Deep Dive: WarpCore/db.py

> **Note:** The local LLM (LM Studio / llama-server on port 8081) was not reachable or the time budget expired, so this page shows the machine-extracted structure instead of a written walkthrough. Rebuild with the model loaded to generate prose.

## AST structure

```text
module: WarpCore/db.py
  module docstring: WarpCore: shared pure-sqlite helpers for Spock V2.
  imports: __future__, os, pathlib, sqlite3, typing
  def resolve_db_path(path, name) [L18-22]
  def connect(db_path, timeout) [L25-31]
  def ensure_schema(db_path, schema_sql) [L34-41]
  def table_exists(db_path, table) [L44-53]
  def row_count(db_path, table) [L56-62]
  def table_names(db_path) [L65-75]
```
