"""Qt-friendly llama-server process manager (max one embedding + one chat)."""

from __future__ import annotations

import os
import subprocess
import threading
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, TextIO

import psutil
from PyQt6.QtCore import QObject, pyqtSignal

from model_selector_core import (
    DEFAULT_LLAMA_SERVER,
    SCRIPT_DIR,
    cuda_ordinal_for_launch,
    is_embedding_gguf_path,
)

try:
    from WarpCore.service_endpoints import DEFAULT_CTX
except ImportError:  # pragma: no cover
    DEFAULT_CTX = {"embed_n_ctx": 8192, "chat_n_ctx": 32768}

LOG_DIR = os.path.join(SCRIPT_DIR, "logs")


def loopback_blocks_llama(port: int, timeout: float = 0.8) -> str:
    """Message when 127.0.0.1:port is not llama-server /health.

    Windows lets LM Studio bind 127.0.0.1 and llama-server bind 0.0.0.0 on
    the same port. localhost then always hits LM Studio.
    """
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        return ""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port_i}/health")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    low = raw.lower()
    if '"status"' in low and "ok" in low and "unexpected endpoint" not in low:
        return ""
    if (
        "unexpected endpoint" in low
        or "lms load" in low
        or "no models loaded" in low
    ):
        return (
            f"127.0.0.1:{port_i} is already LM Studio.\n"
            "llama-server can still bind 0.0.0.0, but Ask AI and Deep Dive "
            "use localhost and will keep hitting LM Studio (often with no "
            "model loaded).\n"
            "Quit LM Studio's local server or pick a different chat port."
        )
    if raw.strip():
        return (
            f"127.0.0.1:{port_i} is already in use by another program.\n"
            "Pick a different port so llama-server is what localhost reaches."
        )
    return ""


def attention_launch_args(
    role: Optional[str],
    flash_attn: Optional[bool] = None,
    cache_type_k: Optional[str] = None,
    cache_type_v: Optional[str] = None,
) -> List[str]:
    """Chat-only Flash Attention and quantized KV flags.

    Embedding servers omit them. ``None`` uses the chat defaults
    (``--flash-attn on``, ``-ctk/-ctv q8_0``). ``False`` or ``""`` turns a
    flag off.
    """
    if (role or "").lower() in ("embedding", "embed"):
        return []
    args: List[str] = []
    if flash_attn is None:
        flash_attn = True
    if flash_attn:
        args.extend(["--flash-attn", "on"])
    k = "q8_0" if cache_type_k is None else str(cache_type_k).strip().lower()
    v = "q8_0" if cache_type_v is None else str(cache_type_v).strip().lower()
    if k:
        args.extend(["-ctk", k])
    if v:
        args.extend(["-ctv", v])
    return args

# Every manager in this process — quit reaps owned llama-server even if the
# window closeEvent did not run (console X / last-window quit).
_MANAGERS: Set["LlamaServerManager"] = set()

# Hard cap: Deep Dive / Ask AI expect a single embed endpoint + one instruct chat.
MAX_INSTANCES_PER_ROLE = {
    "embedding": 1,
    "chat": 1,
}


@dataclass
class ServerInstance:
    """One tracked llama-server (owned by us or discovered)."""

    pid: int
    port: int
    model_path: str = ""
    gpu_label: str = ""
    log_path: str = ""
    role: str = "unknown"  # embedding | chat | unknown
    owned: bool = False
    ngl: str = "-1"
    n_ctx: int = 8192
    llama_batch: int = 512
    llama_ubatch: int = 512
    split_mode: str = ""
    tensor_split: str = ""
    n_parallel: Optional[int] = None
    n_cpu_moe: int = 0
    reasoning: str = ""
    flash_attn: Optional[bool] = None
    cache_type_k: Optional[str] = None
    cache_type_v: Optional[str] = None
    raw_argv: Optional[List[str]] = None
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    log_fp: Optional[TextIO] = field(default=None, repr=False)

    @property
    def model_name(self) -> str:
        return os.path.basename(self.model_path) if self.model_path else "—"

    @property
    def is_alive(self) -> bool:
        if self.process is not None:
            return self.process.poll() is None
        try:
            return psutil.pid_exists(self.pid) and psutil.Process(self.pid).is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False


def _parse_cmdline(cmdline: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {
        "model_path": "",
        "port": "",
        "embeddings": "0",
        "n_ctx": "",
        "ui_mcp_proxy": "0",
        "main_gpu": "",
        "tensor_split": "",
    }
    i = 0
    while i < len(cmdline):
        arg = cmdline[i]
        if arg in ("-m", "--model") and i + 1 < len(cmdline):
            out["model_path"] = cmdline[i + 1]
            i += 2
            continue
        if arg in ("--port", "-p") and i + 1 < len(cmdline):
            out["port"] = cmdline[i + 1]
            i += 2
            continue
        if arg in ("-c", "--ctx-size", "--context-size") and i + 1 < len(cmdline):
            out["n_ctx"] = cmdline[i + 1]
            i += 2
            continue
        if arg in ("-mg", "--main-gpu") and i + 1 < len(cmdline):
            out["main_gpu"] = cmdline[i + 1]
            i += 2
            continue
        if arg in ("-ts", "--tensor-split") and i + 1 < len(cmdline):
            out["tensor_split"] = cmdline[i + 1]
            i += 2
            continue
        if arg == "--embeddings":
            out["embeddings"] = "1"
        if arg == "--ui-mcp-proxy":
            out["ui_mcp_proxy"] = "1"
        i += 1
    return out


def discover_llama_servers() -> List[Dict[str, object]]:
    """Find running llama-server processes (owned or external).

    Skips --ui-mcp-proxy WebUI processes (no GGUF; restored via MCP settings).
    """
    from spock_onboarding.llama_process import format_pid_gpu, gpu_label_for_pid

    found: List[Dict[str, object]] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = (proc.info.get("exe") or "").lower()
            if "llama-server" not in name and "llama-server" not in exe:
                continue
            cmdline = proc.info.get("cmdline") or []
            parsed = _parse_cmdline([str(c) for c in cmdline])
            # WebUI proxy is not an embed/chat GGUF instance
            if parsed.get("ui_mcp_proxy") == "1":
                continue
            port = int(parsed["port"]) if str(parsed["port"]).isdigit() else 0
            model = str(parsed["model_path"] or "")
            if not model:
                continue
            role = "embedding" if (
                parsed["embeddings"] == "1" or is_embedding_gguf_path(model)
            ) else "chat"
            n_ctx = int(parsed["n_ctx"]) if str(parsed["n_ctx"]).isdigit() else 8192
            pid = int(proc.info["pid"])
            gpu_label = gpu_label_for_pid(pid, [str(c) for c in cmdline])
            found.append(
                {
                    "pid": pid,
                    "port": port,
                    "model_path": model,
                    "role": role,
                    "n_ctx": n_ctx,
                    "gpu_label": gpu_label,
                    "pid_display": format_pid_gpu(pid, gpu_label),
                    "cmdline": cmdline,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            continue
    return found


class LlamaServerManager(QObject):
    """Tracks llama-server instances; at most one embedding and one chat."""

    started = pyqtSignal(str, int, int, str)  # model_path, port, pid, gpu (latest)
    log_line = pyqtSignal(str)  # from latest owned launch (Launch panel)
    stopped = pyqtSignal(int)  # exit code of an owned process
    failed = pyqtSignal(str)
    status_message = pyqtSignal(str)
    instances_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        _MANAGERS.add(self)
        self.llama_server_path = DEFAULT_LLAMA_SERVER
        self._instances: Dict[int, ServerInstance] = {}
        self._log_threads: Dict[int, threading.Thread] = {}
        # Compatibility fields = most recently started owned instance
        self.server_process: Optional[subprocess.Popen] = None
        self.model_path: str = ""
        self.port: int = 8080
        self.gpu_label: str = ""
        self.pid: Optional[int] = None
        self.log_path: str = ""
        self._stopping = False

    @property
    def is_running(self) -> bool:
        return any(inst.owned and inst.is_alive for inst in self._instances.values())

    def list_instances(self, refresh_discovered: bool = True) -> List[ServerInstance]:
        """Owned instances plus optionally discovered external llama-servers."""
        # Drop dead owned
        dead = [pid for pid, inst in self._instances.items() if not inst.is_alive]
        for pid in dead:
            self._instances.pop(pid, None)

        if refresh_discovered:
            owned_pids = set(self._instances.keys())
            live = discover_llama_servers()
            for info in live:
                pid = int(info["pid"])
                gpu = str(info.get("gpu_label") or "")
                if pid in owned_pids:
                    # Refresh GPU tag for owned processes when empty
                    owned = self._instances.get(pid)
                    if owned is not None and not (owned.gpu_label or "").strip() and gpu:
                        owned.gpu_label = gpu
                    continue
                self._instances[pid] = ServerInstance(
                    pid=pid,
                    port=int(info["port"] or 0),
                    model_path=str(info["model_path"] or ""),
                    role=str(info["role"] or "unknown"),
                    n_ctx=int(info.get("n_ctx") or 8192),
                    owned=False,
                    gpu_label=gpu,
                )
            # Remove discovered stubs that disappeared
            live_discovered = {int(i["pid"]) for i in live}
            stale = [
                pid
                for pid, inst in self._instances.items()
                if not inst.owned and pid not in live_discovered
            ]
            for pid in stale:
                self._instances.pop(pid, None)

        return sorted(self._instances.values(), key=lambda i: (i.port or 99999, i.pid))

    def alive_for_role(self, role: str) -> List[ServerInstance]:
        role = (role or "").strip().lower()
        return [
            inst
            for inst in self.list_instances(refresh_discovered=True)
            if inst.is_alive and (inst.role or "").lower() == role
        ]

    def chat_n_ctx(self, preferred_port: Optional[int] = None) -> Optional[int]:
        """Return n_ctx for a live chat llama-server (prefer matching port)."""
        chats = self.alive_for_role("chat")
        if not chats:
            return None
        if preferred_port:
            for inst in chats:
                if inst.port == preferred_port:
                    return int(inst.n_ctx or 8192)
        return int(chats[0].n_ctx or 8192)

    def _stop_extra_role_instances(self, role: str, keep_port: Optional[int] = None) -> int:
        """Stop live instances of ``role`` beyond the configured max (usually all before launch)."""
        max_n = MAX_INSTANCES_PER_ROLE.get(role)
        if max_n is None:
            return 0
        live = self.alive_for_role(role)
        # Prefer keeping an instance already on the target port (restart case)
        if keep_port:
            live = sorted(
                live,
                key=lambda i: (0 if i.port == keep_port else 1, i.pid),
            )
        stopped = 0
        # Leave room for the new launch: stop down to max_n - 1
        while len(live) >= max_n:
            victim = live.pop(0)
            self.log_line.emit(
                f"Stopping existing {role} llama-server "
                f"(PID {victim.pid} port {victim.port}) — "
                f"limit is {max_n} per role.\n"
            )
            self.stop_pid(victim.pid)
            stopped += 1
            live = [i for i in self.alive_for_role(role) if i.pid != victim.pid]
        return stopped

    def port_in_use(self, port: int) -> bool:
        for inst in self.list_instances(refresh_discovered=True):
            if inst.port == port and inst.is_alive:
                return True
        return False

    def _saved_llama_gui_argv(self, role: str) -> Optional[List[str]]:
        """Saved View Command for this role, or None when the box is empty.

        A non-empty line that does not parse fails the launch.
        """
        try:
            from spock_shell.llama_gui_command import saved_argv
            from spock_shell.paths import SHIP_COMPUTER_DB
        except Exception:
            return None
        try:
            return saved_argv(SHIP_COMPUTER_DB, role, self.llama_server_path)
        except ValueError as exc:
            self.failed.emit(str(exc))
            return []
        except Exception as exc:
            self.failed.emit(f"Could not read the saved Llama GUI command: {exc}")
            return []

    def launch_saved_llama_gui(self, role: str) -> bool:
        """Launch the command saved on Configure tab 8 or 9."""
        saved = self._saved_llama_gui_argv(role)
        if saved is None:
            which = "Embed" if (role or "").lower() in ("embedding", "embed") else "Chat"
            self.failed.emit(
                f"No Llama GUI {which} command is saved. "
                "Paste one on Configure Spock AI and click Save."
            )
            return False
        if not saved:
            return False
        return self._launch_prepared_argv(saved, role)

    def _launch_prepared_argv(self, argv: List[str], role: str) -> bool:
        """Start a llama-server from an already parsed command line."""
        from spock_shell.llama_gui_command import flag_value, parse_port

        if not os.path.isfile(self.llama_server_path):
            self.failed.emit(
                f"Cannot find llama-server at:\n{self.llama_server_path}\n\n"
                "Set LLAMA_SERVER_PATH or install llama-server."
            )
            return False
        role_l = "embedding" if (role or "").lower() in ("embedding", "embed") else "chat"
        model_path = flag_value(argv, ("-m", "--model"))
        if not model_path or not os.path.isfile(model_path):
            self.failed.emit(f"Model file not found:\n{model_path}")
            return False
        default_port = 8080 if role_l == "embedding" else 8081
        port = parse_port(argv, default_port)
        if role_l in MAX_INSTANCES_PER_ROLE:
            self._stop_extra_role_instances(role_l, keep_port=port)
        if self.port_in_use(port):
            self.failed.emit(
                f"Port {port} is already in use by another llama-server.\n"
                "Stop that instance in Status, or pick a different port."
            )
            return False
        blocked = loopback_blocks_llama(port)
        if blocked:
            self.failed.emit(blocked)
            return False

        cmd = list(argv)
        cmd[0] = self.llama_server_path
        env = os.environ.copy()
        env.pop("CUDA_VISIBLE_DEVICES", None)
        n_ctx_raw = flag_value(cmd, ("-c", "--ctx-size"))
        try:
            n_ctx_i = int(n_ctx_raw) if n_ctx_raw else 8192
        except (TypeError, ValueError):
            n_ctx_i = 8192
        env_info = "CUDA_VISIBLE_DEVICES unset (Llama GUI command)"
        start_banner = f"{env_info}\nRole={role_l}\nStarting: {' '.join(cmd)}\n\n"
        self.log_line.emit(start_banner)
        self.status_message.emit("STATUS: STARTING...")
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = os.path.join(LOG_DIR, f"llama-server-port{port}-{stamp}.log")
        log_fp: Optional[TextIO] = None
        try:
            log_fp = open(log_path, "w", encoding="utf-8", errors="replace")
            log_fp.write(start_banner)
            log_fp.flush()
        except Exception as exc:
            log_fp = None
            log_path = f"(log file unavailable: {exc})"
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except Exception as exc:
            if log_fp:
                try:
                    log_fp.close()
                except Exception:
                    pass
            self.failed.emit(f"Failed to start: {exc}")
            return False
        pid = proc.pid
        inst = ServerInstance(
            pid=pid,
            port=port,
            model_path=model_path,
            log_path=log_path,
            role=role_l,
            owned=True,
            n_ctx=n_ctx_i,
            raw_argv=list(cmd),
            process=proc,
            log_fp=log_fp,
        )
        self._instances[pid] = inst
        self._set_compat_fields(inst)
        thread = threading.Thread(target=self._read_output, args=(pid,), daemon=True)
        self._log_threads[pid] = thread
        thread.start()
        self.status_message.emit(
            f"STATUS: RUNNING on port {port} (PID {pid}) [{role_l}] "
            "Llama GUI command"
        )
        self.started.emit(model_path, port, pid, "")
        self.instances_changed.emit()
        return True

    def launch(
        self,
        model_path: str,
        port: int,
        ngl: str = "-1",
        gpu_list: Optional[List[dict]] = None,
        gpu_name: str = "",
        llama_batch: int = 512,
        llama_ubatch: Optional[int] = None,
        role: Optional[str] = None,
        n_ctx: Optional[int] = None,
        *,
        split_mode: str = "",
        tensor_split: str = "",
        n_parallel: Optional[int] = None,
        pin_cuda: Optional[bool] = None,
        cuda_device: str = "",
        ngl_source: str = "",
        flash_attn: Optional[bool] = None,
        cache_type_k: Optional[str] = None,
        cache_type_v: Optional[str] = None,
        n_cpu_moe: int = 0,
        reasoning: str = "",
    ) -> bool:
        if n_ctx is None:
            n_ctx = int(
                DEFAULT_CTX["embed_n_ctx"]
                if (role or "").lower() in ("embedding", "embed")
                else DEFAULT_CTX["chat_n_ctx"]
            )
        if not os.path.isfile(self.llama_server_path):
            self.failed.emit(
                f"Cannot find llama-server at:\n{self.llama_server_path}\n\n"
                "Set LLAMA_SERVER_PATH or install llama-server."
            )
            return False

        if not os.path.isfile(model_path):
            self.failed.emit(f"Model file not found:\n{model_path}")
            return False

        if not (1 <= port <= 65535):
            self.failed.emit("Enter a valid port number (1-65535).")
            return False

        ngl = str(ngl or "-1").strip()
        if ngl.lower() == "auto":
            ngl = "-1"
        if not ngl.lstrip("-").isdigit() or int(ngl) < -1 or int(ngl) > 999:
            self.failed.emit("Enter -1 (auto) or 0-999 for GPU layers.")
            return False

        try:
            n_ctx_i = int(n_ctx)
        except (TypeError, ValueError):
            n_ctx_i = 8192
        if n_ctx_i < 512 or n_ctx_i > 1_048_576:
            self.failed.emit("Context (-c / n_ctx) must be between 512 and 1048576.")
            return False

        # When caller leaves -1 (auto), ask llmfit for a safer layer count if present.
        ngl_reason = ngl_source or "explicit -ngl"
        if ngl == "-1":
            try:
                from spock_shell.llmfit_bridge import resolve_ngl

                ngl, ngl_reason = resolve_ngl(
                    model_path, n_ctx=n_ctx_i, current_ngl="-1"
                )
            except Exception:
                ngl, ngl_reason = "-1", "llmfit bridge unavailable"
            if not ngl.lstrip("-").isdigit() or int(ngl) < -1 or int(ngl) > 999:
                ngl, ngl_reason = "-1", "llmfit returned invalid -ngl"

        if role is None:
            role = "embedding" if is_embedding_gguf_path(model_path) else "chat"

        saved = self._saved_llama_gui_argv(role)
        if saved is not None:
            if not saved:
                return False
            return self._launch_prepared_argv(saved, role)

        # Enforce one embedding + one chat: stop prior same-role servers first.
        if role in MAX_INSTANCES_PER_ROLE:
            self._stop_extra_role_instances(role, keep_port=port)

        if self.port_in_use(port):
            # Same port still occupied (e.g. other role) — fail clearly
            self.failed.emit(
                f"Port {port} is already in use by another llama-server.\n"
                "Stop that instance in Status, or pick a different port."
            )
            return False
        blocked = loopback_blocks_llama(port)
        if blocked:
            self.failed.emit(blocked)
            return False

        ts = str(tensor_split or "").strip()
        sm = str(split_mode or "").strip() or ("layer" if ts else "")
        use_tensor_split = bool(ts) and role == "chat"
        # tensor-split chat must see all GPUs — do not pin CUDA_VISIBLE_DEVICES.
        if pin_cuda is None:
            pin_cuda = not use_tensor_split

        gpu_idx = None
        idx_source = "CUDA_VISIBLE_DEVICES not set"
        if pin_cuda:
            gpu_idx, idx_source = cuda_ordinal_for_launch(
                cuda_device=str(cuda_device or ""),
                gpu_list=gpu_list or [],
                gpu_name=gpu_name or "",
            )

        batch = max(1, int(llama_batch or 512))
        ubatch = max(1, int(llama_ubatch if llama_ubatch is not None else batch))

        cmd = [
            self.llama_server_path,
            "-m",
            model_path,
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "-c",
            str(n_ctx_i),
            "-ngl",
            ngl,
            "-b",
            str(batch),
            "-ub",
            str(ubatch),
        ]
        np_val: Optional[int] = None
        if n_parallel is not None:
            try:
                np_val = max(1, int(n_parallel))
            except (TypeError, ValueError):
                np_val = None
        if np_val is not None:
            cmd.extend(["-np", str(np_val)])
        if use_tensor_split:
            cmd.extend(["--split-mode", sm or "layer"])
            cmd.extend(["--tensor-split", ts])

        # Embedding models produce garbage in the web chat UI — disable it
        if role == "embedding":
            cmd.append("--embeddings")
            cmd.append("--no-webui")
            # Family-specific pooling for usable RAG vectors.
            low_model = model_path.lower().replace("\\", "/")
            if (
                "qwen3-embedding" in low_model
                or "qwen3_embedding" in low_model
                or "qwen3-vl-embedding" in low_model
                or "qwen3_vl_embedding" in low_model
            ):
                cmd.extend(["--pooling", "last"])
            elif "embeddinggemma" in low_model:
                # EmbeddingGemma / EmbeddingGemma 2 use mean pooling.
                cmd.extend(["--pooling", "mean"])
        else:
            cmd.extend(
                attention_launch_args(role, flash_attn, cache_type_k, cache_type_v)
            )
            from WarpCore.config_defaults import chat_moe_reasoning_argv

            cmd.extend(chat_moe_reasoning_argv(role, n_cpu_moe, reasoning))

        env = os.environ.copy()
        if pin_cuda and gpu_idx is not None and gpu_idx != "":
            env["CUDA_VISIBLE_DEVICES"] = gpu_idx
        elif "CUDA_VISIBLE_DEVICES" in env and use_tensor_split:
            # Inherit multi-GPU visibility for tensor-split.
            env.pop("CUDA_VISIBLE_DEVICES", None)

        env_info = (
            f"CUDA_VISIBLE_DEVICES={gpu_idx}  ({idx_source})"
            if pin_cuda and gpu_idx is not None and gpu_idx != ""
            else (
                f"CUDA_VISIBLE_DEVICES unset (tensor-split {ts})"
                if use_tensor_split
                else "CUDA_VISIBLE_DEVICES not set"
            )
        )
        gpu_info = f" on GPU {gpu_name}" if pin_cuda and gpu_name else ""
        start_banner = (
            f"{env_info}\nRole={role}\nStarting{gpu_info}: {' '.join(cmd)}\n\n"
        )
        self.log_line.emit(start_banner)
        self.status_message.emit("STATUS: STARTING...")

        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = os.path.join(LOG_DIR, f"llama-server-port{port}-{stamp}.log")
        log_fp: Optional[TextIO] = None
        try:
            log_fp = open(log_path, "w", encoding="utf-8", errors="replace")
            log_fp.write(start_banner)
            log_fp.flush()
        except Exception as e:
            log_fp = None
            log_path = f"(log file unavailable: {e})"

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except Exception as e:
            if log_fp:
                try:
                    log_fp.close()
                except Exception:
                    pass
            self.failed.emit(f"Failed to start: {e}")
            return False

        pid = proc.pid
        inst = ServerInstance(
            pid=pid,
            port=port,
            model_path=model_path,
            gpu_label=gpu_name,
            log_path=log_path,
            role=role,
            owned=True,
            ngl=ngl,
            n_ctx=n_ctx_i,
            llama_batch=batch,
            llama_ubatch=ubatch,
            split_mode=sm if use_tensor_split else "",
            tensor_split=ts if use_tensor_split else "",
            n_parallel=np_val,
            n_cpu_moe=int(n_cpu_moe or 0) if role == "chat" else 0,
            reasoning=str(reasoning or "") if role == "chat" else "",
            flash_attn=flash_attn,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
            process=proc,
            log_fp=log_fp,
        )
        self._instances[pid] = inst
        self._set_compat_fields(inst)

        thread = threading.Thread(
            target=self._read_output, args=(pid,), daemon=True
        )
        self._log_threads[pid] = thread
        thread.start()

        self.status_message.emit(
            f"STATUS: RUNNING on port {port} (PID {pid}) [{role}] "
            f"-ngl {ngl} ({ngl_reason})"
        )
        self.started.emit(model_path, port, pid, gpu_name)
        self.instances_changed.emit()
        return True

    def _set_compat_fields(self, inst: ServerInstance):
        self.server_process = inst.process
        self.model_path = inst.model_path
        self.port = inst.port
        self.gpu_label = inst.gpu_label
        self.pid = inst.pid
        self.log_path = inst.log_path

    def _close_log_fp(self, inst: ServerInstance):
        if inst.log_fp is not None:
            try:
                inst.log_fp.close()
            except Exception:
                pass
            inst.log_fp = None

    def _read_output(self, pid: int):
        inst = self._instances.get(pid)
        if not inst or not inst.process or not inst.process.stdout:
            return
        proc = inst.process
        try:
            for line in proc.stdout:
                if inst.log_fp is not None:
                    try:
                        inst.log_fp.write(line)
                        inst.log_fp.flush()
                    except Exception:
                        pass
                # Stream to Launch/Status live pane for this process
                if self.pid == pid:
                    self.log_line.emit(line)
        except Exception:
            pass
        finally:
            return_code = proc.poll()
            if return_code is None:
                return_code = -1
            self._close_log_fp(inst)
            inst.process = None
            if pid in self._instances:
                # Keep record briefly as stopped? Remove owned dead entry
                self._instances.pop(pid, None)
            if self.pid == pid:
                self.server_process = None
                self.pid = None
                self.status_message.emit(f"STATUS: STOPPED (exit code {return_code})")
                self.stopped.emit(return_code)
            self.instances_changed.emit()

    def stop(self):
        """Stop the most recently owned / compat instance."""
        if self.pid and self.pid in self._instances:
            self.stop_pid(self.pid)
            return
        # Fallback: stop any owned
        for inst in list(self._instances.values()):
            if inst.owned and inst.is_alive:
                self.stop_pid(inst.pid)
                return

    def stop_owned(self) -> int:
        """Stop llama-server processes this manager launched (not foreign PIDs)."""
        stopped = 0
        for inst in list(self._instances.values()):
            if not inst.owned:
                continue
            if self.stop_pid(inst.pid):
                stopped += 1
        return stopped

    def _terminate_pid_tree(self, pid: int, timeout: float = 8.0) -> None:
        """Terminate pid and descendants so llama-server workers do not orphan."""
        try:
            parent = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        kids = parent.children(recursive=True)
        for child in kids:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        try:
            parent.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        _, alive = psutil.wait_procs(kids + [parent], timeout=timeout)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def stop_pid(self, pid: int) -> bool:
        inst = self._instances.get(pid)
        if not inst:
            # Try kill external by pid
            try:
                p = psutil.Process(pid)
                p.terminate()
                p.wait(timeout=8)
            except Exception:
                try:
                    psutil.Process(pid).kill()
                except Exception:
                    return False
            self.instances_changed.emit()
            return True

        self._stopping = True
        try:
            self.status_message.emit(f"STATUS: STOPPING PID {pid}...")
        except RuntimeError:
            pass
        self._terminate_pid_tree(pid)
        self._close_log_fp(inst)
        self._instances.pop(pid, None)
        if self.pid == pid:
            self.server_process = None
            self.pid = None
            self.stopped.emit(-1)
        self.instances_changed.emit()
        return True

    def restart_pid(self, pid: int, gpu_list: Optional[List[dict]] = None) -> bool:
        inst = self._instances.get(pid)
        if not inst or not inst.owned:
            self.failed.emit("Can only restart instances launched from Spock-to-bridge.")
            return False
        if not inst.model_path or not os.path.isfile(inst.model_path):
            self.failed.emit("Cannot restart: model path missing.")
            return False
        port = inst.port
        model = inst.model_path
        gpu = inst.gpu_label
        ngl = inst.ngl
        n_ctx = getattr(inst, "n_ctx", 8192)
        batch = inst.llama_batch
        ubatch = inst.llama_ubatch
        role = inst.role
        raw = list(getattr(inst, "raw_argv", None) or [])
        self.stop_pid(pid)
        if raw:
            return self._launch_prepared_argv(raw, role)
        return self.launch(
            model_path=model,
            port=port,
            ngl=ngl,
            gpu_list=gpu_list,
            gpu_name=gpu,
            llama_batch=batch,
            llama_ubatch=ubatch,
            role=role,
            n_ctx=n_ctx,
            split_mode=getattr(inst, "split_mode", "") or "",
            tensor_split=getattr(inst, "tensor_split", "") or "",
            n_parallel=getattr(inst, "n_parallel", None),
            pin_cuda=not bool(getattr(inst, "tensor_split", "") or ""),
            flash_attn=getattr(inst, "flash_attn", None),
            cache_type_k=getattr(inst, "cache_type_k", None),
            cache_type_v=getattr(inst, "cache_type_v", None),
            n_cpu_moe=int(getattr(inst, "n_cpu_moe", 0) or 0),
            reasoning=str(getattr(inst, "reasoning", "") or ""),
        )

    def kill_all(self) -> int:
        killed = 0
        # Prefer graceful stop of owned first
        for pid in list(self._instances.keys()):
            if self.stop_pid(pid):
                killed += 1
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                exe = proc.info.get("exe") or ""
                name = proc.info.get("name") or ""
                if "llama-server" in name.lower() or "llama-server" in exe.lower():
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        self.server_process = None
        self.pid = None
        self._instances.clear()
        msg = (
            f"Killed {killed} llama-server process(es)."
            if killed
            else "No llama-server processes found."
        )
        self.log_line.emit(f"\n{msg}\n")
        self.status_message.emit(msg)
        self.instances_changed.emit()
        return killed


def stop_all_owned_in_process() -> int:
    """Stop llama-server this process launched (every LlamaServerManager)."""
    stopped = 0
    for mgr in list(_MANAGERS):
        try:
            stopped += int(mgr.stop_owned() or 0)
        except Exception:
            pass
    return stopped
