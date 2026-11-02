"""Persist first-models summary for bringup / future UI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class FirstModelsState:
    root: Path
    runtime: str = "llamacpp"
    llama_server_path: str = ""
    llama_install_dir: str = ""
    embed_model_id: str = ""
    chat_model_id: str = ""
    embed_gguf_path: str = ""
    chat_gguf_path: str = ""
    embed_n_ctx: int = 8192
    chat_n_ctx: int = 8192
    embed_quant: str = ""
    chat_quant: str = ""
    pick_note: str = ""
    embed_dim: Optional[int] = None
    embed_probe_ok: bool = False
    chat_probe_ok: bool = False
    vram_gb: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary_path(self) -> Path:
        return self.root / "first_models_last.json"

    def summary_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "runtime": self.runtime,
            "llama_server_path": self.llama_server_path,
            "llama_install_dir": self.llama_install_dir,
            "embed_model_id": self.embed_model_id,
            "chat_model_id": self.chat_model_id,
            "embed_gguf_path": self.embed_gguf_path,
            "chat_gguf_path": self.chat_gguf_path,
            "embed_n_ctx": self.embed_n_ctx,
            "chat_n_ctx": self.chat_n_ctx,
            "embed_quant": self.embed_quant,
            "chat_quant": self.chat_quant,
            "pick_note": self.pick_note,
            "embed_dim": self.embed_dim,
            "embed_probe_ok": self.embed_probe_ok,
            "chat_probe_ok": self.chat_probe_ok,
            "vram_gb": self.vram_gb,
        }
        d.update(self.extra)
        return d

    def write_summary_json(self) -> Path:
        path = self.summary_path
        path.write_text(json.dumps(self.summary_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, root: Path) -> Optional["FirstModelsState"]:
        path = root / "first_models_last.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return cls(
            root=root,
            runtime=str(data.get("runtime") or "llamacpp"),
            llama_server_path=str(data.get("llama_server_path") or ""),
            llama_install_dir=str(data.get("llama_install_dir") or ""),
            embed_model_id=str(data.get("embed_model_id") or ""),
            chat_model_id=str(data.get("chat_model_id") or ""),
            embed_gguf_path=str(data.get("embed_gguf_path") or ""),
            chat_gguf_path=str(data.get("chat_gguf_path") or ""),
            embed_n_ctx=int(data.get("embed_n_ctx") or 8192),
            chat_n_ctx=int(data.get("chat_n_ctx") or 8192),
            embed_quant=str(data.get("embed_quant") or ""),
            chat_quant=str(data.get("chat_quant") or ""),
            pick_note=str(data.get("pick_note") or ""),
            embed_dim=data.get("embed_dim"),
            embed_probe_ok=bool(data.get("embed_probe_ok")),
            chat_probe_ok=bool(data.get("chat_probe_ok")),
            vram_gb=data.get("vram_gb"),
        )
