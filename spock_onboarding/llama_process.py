"""Qt-free llama-server process management (embed + chat)."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TextIO

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

try:
    from WarpCore.service_endpoints import (
        DEFAULT_CHAT_PORT,
        DEFAULT_EMBED_PORT,
    )
except ImportError:  # pragma: no cover
    DEFAULT_EMBED_PORT = 8080
    DEFAULT_CHAT_PORT = 8081

MAX_PER_ROLE = {"embedding": 1, "chat": 1}


def is_embedding_gguf_path(path: str) -> bool:
    low = (path or "").lower().replace("\\", "/")
    return any(
        t in low
        for t in (
            "embed",
            "embedding",
            "bge-",
            "e5-",
            "nomic-embed",
            "gte-",
        )
    )


def parse_cmdline(cmdline: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {
        "model_path": "",
        "port": "",
        "embeddings": "0",
        "n_ctx": "",
        "ui_mcp_proxy": "0",
        "ngl": "",
        "main_gpu": "",
        "tensor_split": "",
    }
    i = 0
    while i < len(cmdline):
        arg = str(cmdline[i])
        if arg in ("-m", "--model") and i + 1 < len(cmdline):
            out["model_path"] = str(cmdline[i + 1])
            i += 2
            continue
        if arg in ("--port", "-p") and i + 1 < len(cmdline):
            out["port"] = str(cmdline[i + 1])
            i += 2
            continue
        if arg in ("-c", "--ctx-size", "--context-size") and i + 1 < len(cmdline):
            out["n_ctx"] = str(cmdline[i + 1])
            i += 2
            continue
        if arg in ("-ngl", "--n-gpu-layers", "--gpu-layers") and i + 1 < len(cmdline):
            out["ngl"] = str(cmdline[i + 1])
            i += 2
            continue
        if arg in ("-mg", "--main-gpu") and i + 1 < len(cmdline):
            out["main_gpu"] = str(cmdline[i + 1])
            i += 2
            continue
        if arg in ("-ts", "--tensor-split") and i + 1 < len(cmdline):
            out["tensor_split"] = str(cmdline[i + 1])
            i += 2
            continue
        if arg in ("--embeddings", "--embedding"):
            out["embeddings"] = "1"
        if arg in ("--ui-mcp-proxy",):
            out["ui_mcp_proxy"] = "1"
        i += 1
    return out


def gpu_label_from_cvd_and_cmdline(
    cuda_visible: str = "",
    *,
    main_gpu: str = "",
    tensor_split: str = "",
) -> str:
    """Human GPU tag: ``GPU 0``, ``GPU 0+1``, ``multi-GPU``, or empty."""
    cvd = (cuda_visible or "").strip()
    if cvd:
        parts = [p.strip() for p in cvd.split(",") if p.strip() != ""]
        if len(parts) == 1:
            return f"GPU {parts[0]}"
        if parts:
            return "GPU " + "+".join(parts)
    mg = (main_gpu or "").strip()
    if mg != "" and not (tensor_split or "").strip():
        return f"GPU {mg}"
    if (tensor_split or "").strip():
        return "multi-GPU"
    return ""


def gpu_label_for_pid(pid: int, cmdline: Optional[List[str]] = None) -> str:
    """Best-effort GPU assignment for a running process."""
    cuda_visible = ""
    if psutil is not None:
        try:
            env = psutil.Process(int(pid)).environ()
            cuda_visible = str(env.get("CUDA_VISIBLE_DEVICES") or "")
        except (psutil.Error, TypeError, ValueError):
            cuda_visible = ""
    parsed: Dict[str, str] = {}
    if cmdline:
        parsed = parse_cmdline([str(c) for c in cmdline])
    return gpu_label_from_cvd_and_cmdline(
        cuda_visible,
        main_gpu=str(parsed.get("main_gpu") or ""),
        tensor_split=str(parsed.get("tensor_split") or ""),
    )


def format_pid_gpu(pid: Any, gpu_label: str = "") -> str:
    """``pid 1234`` or ``pid 1234 on GPU 0`` (keeps named GPUs as-is)."""
    label = (gpu_label or "").strip()
    if not label:
        return f"pid {pid}"
    low = label.lower()
    if low.startswith("gpu") or low == "multi-gpu" or any(c.isalpha() for c in label):
        pass  # already tagged, or a device name like "RTX 3060"
    else:
        label = f"GPU {label}"
    return f"pid {pid} on {label}"


def role_from_parsed(parsed: Dict[str, str]) -> str:
    model = parsed.get("model_path") or ""
    if parsed.get("embeddings") == "1" or is_embedding_gguf_path(model):
        return "embedding"
    return "chat"


def build_server_argv(
    llama_server: str,
    model_path: str,
    *,
    port: int,
    n_ctx: int = 8192,
    ngl: str = "-1",
    role: Optional[str] = None,
    batch: int = 512,
    ubatch: Optional[int] = None,
    split_mode: str = "",
    tensor_split: str = "",
    n_parallel: Optional[int] = None,
    n_cpu_moe: int = 0,
    reasoning: str = "",
) -> List[str]:
    if role is None:
        role = "embedding" if is_embedding_gguf_path(model_path) else "chat"
    ub = int(ubatch if ubatch is not None else batch)
    cmd = [
        llama_server,
        "-m",
        model_path,
        "--host",
        "0.0.0.0",
        "--port",
        str(int(port)),
        "-c",
        str(int(n_ctx)),
        "-ngl",
        str(ngl),
        "-b",
        str(int(batch)),
        "-ub",
        str(ub),
    ]
    ts = str(tensor_split or "").strip()
    sm = str(split_mode or "").strip()
    if ts and role == "chat":
        cmd.extend(["--split-mode", sm or "layer", "--tensor-split", ts])
    if role == "chat":
        from WarpCore.config_defaults import chat_moe_reasoning_argv

        cmd.extend(chat_moe_reasoning_argv(role, n_cpu_moe, reasoning))
    if n_parallel is not None and role == "embedding":
        cmd.extend(["-np", str(int(n_parallel))])
    if role == "embedding":
        cmd.append("--embeddings")
        cmd.append("--no-webui")
        low = model_path.lower().replace("\\", "/")
        if (
            "qwen3-embedding" in low
            or "qwen3_embedding" in low
            or "qwen3-vl-embedding" in low
            or "qwen3_vl_embedding" in low
        ):
            cmd.extend(["--pooling", "last"])
        elif "embeddinggemma" in low:
            cmd.extend(["--pooling", "mean"])
    return cmd


@dataclass
class ServerInstance:
    pid: int
    port: int
    model_path: str = ""
    role: str = "unknown"
    n_ctx: int = 8192
    owned: bool = False
    ngl: str = "-1"
    gpu_label: str = ""
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    log_fp: Optional[TextIO] = field(default=None, repr=False)
    log_path: str = ""

    @property
    def alive(self) -> bool:
        if self.process is not None:
            return self.process.poll() is None
        if psutil is None:
            return False
        try:
            return psutil.pid_exists(self.pid) and psutil.Process(self.pid).is_running()
        except Exception:
            return False


def discover_llama_servers() -> List[Dict[str, Any]]:
    if psutil is None:
        return []
    found: List[Dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = (proc.info.get("exe") or "").lower()
            if "llama-server" not in name and "llama-server" not in exe:
                continue
            cmdline = [str(c) for c in (proc.info.get("cmdline") or [])]
            parsed = parse_cmdline(cmdline)
            if parsed.get("ui_mcp_proxy") == "1":
                continue
            model = str(parsed.get("model_path") or "")
            if not model:
                continue
            port_s = str(parsed.get("port") or "")
            port = int(port_s) if port_s.isdigit() else 0
            n_ctx_s = str(parsed.get("n_ctx") or "")
            n_ctx = int(n_ctx_s) if n_ctx_s.isdigit() else 8192
            pid = int(proc.info["pid"])
            found.append(
                {
                    "pid": pid,
                    "port": port,
                    "model_path": model,
                    "role": role_from_parsed(parsed),
                    "n_ctx": n_ctx,
                    "ngl": parsed.get("ngl") or "",
                    "gpu_label": gpu_label_for_pid(pid, cmdline),
                    "cmdline": cmdline,
                }
            )
        except (ValueError, TypeError):
            continue
        except Exception:
            continue
    return found


class LlamaProcessManager:
    """Track owned llama-server processes; attach to discovered peers."""

    def __init__(self, llama_server_path: str = "", log_dir: Optional[Path] = None) -> None:
        self.llama_server_path = llama_server_path or ""
        self.log_dir = Path(log_dir) if log_dir else Path("logs")
        self._owned: Dict[int, ServerInstance] = {}
        self._owned_pids: Set[int] = set()

    def list_instances(self, *, refresh: bool = True) -> List[ServerInstance]:
        dead = [pid for pid, inst in self._owned.items() if not inst.alive]
        for pid in dead:
            self._owned.pop(pid, None)
            self._owned_pids.discard(pid)
        out = list(self._owned.values())
        if refresh:
            owned = set(self._owned.keys())
            for info in discover_llama_servers():
                pid = int(info["pid"])
                if pid in owned:
                    continue
                out.append(
                    ServerInstance(
                        pid=pid,
                        port=int(info.get("port") or 0),
                        model_path=str(info.get("model_path") or ""),
                        role=str(info.get("role") or "unknown"),
                        n_ctx=int(info.get("n_ctx") or 8192),
                        owned=False,
                        ngl=str(info.get("ngl") or ""),
                        gpu_label=str(info.get("gpu_label") or ""),
                    )
                )
        return sorted(out, key=lambda i: (i.port or 99999, i.pid))

    def alive_for_role(self, role: str) -> List[ServerInstance]:
        role = (role or "").strip().lower()
        return [i for i in self.list_instances(refresh=True) if i.alive and i.role == role]

    def port_in_use(self, port: int) -> bool:
        return any(i.port == int(port) and i.alive for i in self.list_instances(refresh=True))

    def stop_role(self, role: str) -> int:
        stopped = 0
        for inst in list(self.alive_for_role(role)):
            if self.stop_pid(inst.pid):
                stopped += 1
        return stopped

    def stop_pid(self, pid: int) -> bool:
        inst = self._owned.get(pid)
        if inst and inst.process is not None:
            try:
                inst.process.terminate()
                try:
                    inst.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    inst.process.kill()
            except Exception:
                pass
            if inst.log_fp:
                try:
                    inst.log_fp.close()
                except Exception:
                    pass
            self._owned.pop(pid, None)
            self._owned_pids.discard(pid)
            return True
        if psutil is None:
            return False
        try:
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=8)
            except psutil.TimeoutExpired:
                p.kill()
            self._owned.pop(pid, None)
            self._owned_pids.discard(pid)
            return True
        except Exception:
            return False

    def stop_owned(self) -> int:
        n = 0
        for pid in list(self._owned_pids):
            if self.stop_pid(pid):
                n += 1
        return n

    def launch(
        self,
        model_path: str,
        port: int,
        *,
        ngl: str = "-1",
        role: Optional[str] = None,
        n_ctx: int = 8192,
        batch: int = 512,
        ubatch: Optional[int] = None,
        split_mode: str = "",
        tensor_split: str = "",
        n_parallel: Optional[int] = None,
        pin_cuda: Optional[bool] = None,
        cuda_device: str = "",
        n_cpu_moe: int = 0,
        reasoning: str = "",
    ) -> ServerInstance:
        exe = self.llama_server_path
        if not exe or not os.path.isfile(exe):
            raise FileNotFoundError(f"llama-server not found: {exe}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"model not found: {model_path}")
        if role is None:
            role = "embedding" if is_embedding_gguf_path(model_path) else "chat"
        saved: Optional[List[str]] = None
        try:
            from spock_shell.llama_gui_command import saved_argv
            from spock_shell.paths import SHIP_COMPUTER_DB

            saved = saved_argv(SHIP_COMPUTER_DB, role, exe)
            if saved:
                from spock_shell.llama_gui_command import parse_port

                port = parse_port(saved, port)
        except ValueError:
            raise
        except Exception:
            saved = None
        # Enforce one per role
        for inst in list(self.alive_for_role(role)):
            self.stop_pid(inst.pid)
        if self.port_in_use(port):
            raise RuntimeError(f"port {port} already in use")

        ts = str(tensor_split or "").strip()
        use_tensor_split = bool(ts) and role == "chat" and not saved
        if pin_cuda is None:
            pin_cuda = not use_tensor_split
        if saved:
            pin_cuda = False
            cmd = saved
        else:
            cmd = build_server_argv(
                exe,
                model_path,
                port=port,
                n_ctx=n_ctx,
                ngl=ngl,
                role=role,
                batch=batch,
                ubatch=ubatch,
                split_mode=split_mode,
                tensor_split=ts if use_tensor_split else "",
                n_parallel=n_parallel,
                n_cpu_moe=n_cpu_moe,
                reasoning=reasoning,
            )
        env = os.environ.copy()
        if saved:
            env.pop("CUDA_VISIBLE_DEVICES", None)
        elif pin_cuda and str(cuda_device).strip() != "":
            from model_selector_core import cuda_ordinal_for_launch

            # Pass live nvidia-smi rows when available so dual identical GPUs
            # (two 3060s) map smi index → CUDA ordinal correctly. With no list,
            # cuda_ordinal_for_launch falls back to get_cuda_devices().
            gpu_list = None
            try:
                from WarpCore.host_recipe import probe_hardware

                gpu_list = list((probe_hardware() or {}).get("gpus") or [])
            except Exception:
                gpu_list = None
            ordinal, _ordinal_source = cuda_ordinal_for_launch(
                cuda_device=str(cuda_device).strip(),
                gpu_list=gpu_list,
            )
            if ordinal:
                env["CUDA_VISIBLE_DEVICES"] = ordinal
            else:
                env.pop("CUDA_VISIBLE_DEVICES", None)
        elif use_tensor_split:
            env.pop("CUDA_VISIBLE_DEVICES", None)

        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = self.log_dir / f"llama-server-port{port}-{stamp}.log"
        log_fp = open(log_path, "w", encoding="utf-8", errors="replace")
        env_line = (
            f"CUDA_VISIBLE_DEVICES={env.get('CUDA_VISIBLE_DEVICES', 'unset')} "
            f"role={role}"
        )
        log_fp.write(env_line + "\n" + " ".join(cmd) + "\n")
        log_fp.flush()
        creation = 0
        if os.name == "nt":
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            cmd,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            creationflags=creation,
        )
        inst = ServerInstance(
            pid=int(proc.pid),
            port=int(port),
            model_path=model_path,
            role=role,
            n_ctx=int(n_ctx),
            owned=True,
            ngl=str(ngl),
            process=proc,
            log_fp=log_fp,
            log_path=str(log_path),
        )
        self._owned[inst.pid] = inst
        self._owned_pids.add(inst.pid)
        return inst


def wait_until_healthy(
    probe_fn,
    host: str,
    port: int,
    *,
    role_hint: str = "",
    timeout_s: float = 120.0,
    interval_s: float = 1.0,
) -> Dict[str, Any]:
    """Poll probe_fn(host, port, role_hint=...) until reachable or timeout."""
    deadline = time.monotonic() + float(timeout_s)
    last: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = probe_fn(host, port, role_hint=role_hint)
        if last.get("reachable"):
            return last
        time.sleep(interval_s)
    last = last or probe_fn(host, port, role_hint=role_hint)
    last["wait_timeout"] = True
    return last
