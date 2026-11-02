# Readiness schema (Phase 1 freeze)

File: `spock_ready_last.json` (repo root after `spock_bringup status` / `spock_probe`)

```json
{
  "ts": "ISO-8601 UTC",
  "install_root": "absolute path",
  "ui_ready": true,
  "servers_ready": true,
  "full_deps_ok": false,
  "venv_python": ".../.venv/Scripts/python.exe",
  "embed": {
    "port": 8080,
    "reachable": true,
    "model_path": "...",
    "model_name": "...",
    "n_ctx": 8192,
    "pid": null,
    "attached": false
  },
  "chat": {
    "port": 8081,
    "reachable": true,
    "model_path": "...",
    "model_name": "...",
    "n_ctx": 8192,
    "pid": null,
    "attached": false
  },
  "reasons": ["SERVERS_NOT_READY", "UI_NOT_READY", "NEED_ACQUIRE", "NEED_HF_TOKEN"],
  "next_ui_prompts": ["hf_token", "api_keys", "ingest_paths"],
  "schema_version": 1
}
```

## Gates

| Flag | Meaning |
|------|---------|
| `ui_ready` | Phase A: `.venv` exists and `import PyQt6` succeeds |
| `servers_ready` | Embed `:8080` and chat `:8081` `/health` OK |
| `full_deps_ok` | `bootstrap_full_deps.ok` present (Phase B) |

## Future PyQt UI

`next_ui_prompts` drives show-and-tell screens (tokens, API keys, ingest paths). Do not invent parallel status files without bumping `schema_version`.
