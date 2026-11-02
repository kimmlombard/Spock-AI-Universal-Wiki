#!/usr/bin/env python3
"""Rewrite first_models_last.json Windows paths for the WSL Spock tree."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SPOCK_WSL_DST", Path.home() / "src" / "Spock-AI-Universal-Wiki"))
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from spock_bringup import _resolve_existing_file  # noqa: E402
from WarpCore.service_endpoints import (  # noqa: E402
    is_runnable_host_binary,
    resolve_llama_server_path,
)

path = ROOT / "first_models_last.json"
if not path.is_file():
    raise SystemExit(f"missing {path}")

data = json.loads(path.read_text(encoding="utf-8"))
print("before llama=", data.get("llama_server_path"))
print("before embed=", data.get("embed_gguf_path"))
print("before chat=", data.get("chat_gguf_path"))

llama_path, note = resolve_llama_server_path()
if is_runnable_host_binary(llama_path):
    data["llama_server_path"] = str(Path(llama_path).resolve())
    data["llama_install_dir"] = str(Path(llama_path).resolve().parent)
    print("llama ->", data["llama_server_path"], f"({note})")
else:
    print("WARN: no native llama-server yet:", llama_path, note)

embed = _resolve_existing_file(str(data.get("embed_gguf_path") or ""), ROOT)
chat = _resolve_existing_file(str(data.get("chat_gguf_path") or ""), ROOT)
if embed:
    data["embed_gguf_path"] = str(embed)
    print("embed ->", embed)
else:
    print("WARN: embed GGUF not found")
if chat:
    data["chat_gguf_path"] = str(chat)
    print("chat ->", chat)
else:
    print("WARN: chat GGUF not found")

path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print("wrote", path)
