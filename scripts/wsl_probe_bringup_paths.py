#!/usr/bin/env python3
"""Probe what WSL bring-up would use for llama-server / llmfit."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SPOCK_WSL_DST", Path.home() / "src" / "Spock-AI-Universal-Wiki"))
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

print("ROOT", ROOT)
print("os.name", os.name)

fm = ROOT / "first_models_last.json"
if fm.is_file():
    data = json.loads(fm.read_text(encoding="utf-8"))
    print("first_models_last.json:")
    for k in (
        "llama_server_path",
        "embed_gguf_path",
        "chat_gguf_path",
        "llmfit_path",
    ):
        print(f"  {k}={data.get(k)}")
else:
    print("no first_models_last.json")

db = ROOT / "ship_computer.db"
if db.is_file():
    c = sqlite3.connect(str(db))
    rows = c.execute(
        "SELECT Variable_Name, Variable_Value FROM Spock_Console "
        "WHERE Variable_Name LIKE '%llmfit%' OR Variable_Name LIKE '%llama%' "
        "OR Variable_Name LIKE '%gguf%' ORDER BY 1"
    ).fetchall()
    print("Spock_Console llama/llmfit/gguf:")
    for n, v in rows:
        print(f"  {n}={v}")
    c.close()

print("tools/llmfit:", list((ROOT / "tools" / "llmfit").iterdir()) if (ROOT / "tools" / "llmfit").is_dir() else "missing")
print("tools/llama-server:", list((ROOT / "tools" / "llama-server").iterdir()) if (ROOT / "tools" / "llama-server").is_dir() else "missing")

from WarpCore.service_endpoints import (
    llmfit_binary_candidates,
    llama_server_binary_candidates,
    resolve_llama_server_path,
)

print("llmfit candidates:")
for p in llmfit_binary_candidates(ROOT):
    print(f"  exists={p.is_file()} {p}")

print("llama candidates:")
for p in llama_server_binary_candidates(ROOT):
    print(f"  exists={p.is_file()} {p}")

path, src = resolve_llama_server_path()
print("resolve_llama_server_path:", path, "src=", src)

from spock_onboarding import llmfit_bridge
from spock_onboarding.runtime import detect_llama_server

print("llmfit available", llmfit_bridge.available())
print("find_llmfit_exe", llmfit_bridge.find_llmfit_exe())
print("find_uvx", llmfit_bridge.find_uvx())
print("detect_llama_server", detect_llama_server(ROOT))
