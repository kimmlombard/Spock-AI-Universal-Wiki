"""Parse a Llama GUI Quick Launch "View Command" line.

Llama GUI joins tokens with double quotes only when a token contains a space
or a quote, and escapes inner quotes as backslash-quote. Backslashes in
Windows paths stay literal, so POSIX shlex is the wrong splitter.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

EMBED_KEY = "app.launch.llama_gui_embed_command"
CHAT_KEY = "app.launch.llama_gui_chat_command"

_SERVER_NAMES = {"llama-server", "llama-server.exe"}


def role_key(role: str) -> str:
    if (role or "").lower() in ("embedding", "embed"):
        return EMBED_KEY
    return CHAT_KEY


def normalize_role(role: str) -> str:
    if (role or "").lower() in ("embedding", "embed"):
        return "embedding"
    return "chat"


def split_llama_gui_command(text: str) -> List[str]:
    """Split a View Command line the way Llama GUI quoteArg would rejoin it."""
    tokens: List[str] = []
    buf: List[str] = []
    in_quote = False
    i = 0
    source = text or ""
    while i < len(source):
        ch = source[i]
        if in_quote:
            if ch == "\\" and i + 1 < len(source) and source[i + 1] == '"':
                buf.append('"')
                i += 2
                continue
            if ch == '"':
                in_quote = False
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_quote = True
            i += 1
            continue
        if ch in " \t\r\n":
            if buf:
                tokens.append("".join(buf))
                buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if in_quote:
        raise ValueError("The Llama GUI command has an unclosed quote.")
    if buf:
        tokens.append("".join(buf))
    return tokens


def _is_server_token(token: str) -> bool:
    return os.path.basename(token or "").lower() in _SERVER_NAMES


def flag_value(argv: List[str], names: tuple) -> str:
    """Value of the first matching flag. ``--flag=value`` and ``--flag value``."""
    wanted = {name.lower() for name in names}
    i = 0
    while i < len(argv):
        token = argv[i]
        low = token.lower()
        for name in wanted:
            if low == name:
                if i + 1 < len(argv):
                    return argv[i + 1]
                return ""
            prefix = name + "="
            if low.startswith(prefix):
                return token.split("=", 1)[1]
        i += 1
    return ""


def has_flag(argv: List[str], names: tuple) -> bool:
    wanted = {name.lower() for name in names}
    for token in argv:
        low = token.lower()
        if low in wanted or any(low.startswith(name + "=") for name in wanted):
            return True
    return False


def parse_port(argv: List[str], default: int) -> int:
    raw = flag_value(argv, ("--port", "-p"))
    if not raw:
        return int(default)
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return int(default)
    if not 1 <= port <= 65535:
        return int(default)
    return port


def parse_llama_gui_command(text: str) -> List[str]:
    """Return argv. Raises ValueError when the line is not a llama-server command."""
    argv = split_llama_gui_command(text)
    if not argv or not _is_server_token(argv[0]):
        raise ValueError(
            "The command must start with llama-server or llama-server.exe."
        )
    model = flag_value(argv, ("-m", "--model"))
    if not model:
        raise ValueError("The command needs -m or --model and a GGUF path.")
    return argv


def with_resolved_binary(argv: List[str], binary: str) -> List[str]:
    """Replace the preview's bare llama-server.exe with Spock's binary."""
    if not argv:
        return []
    out = list(argv)
    if binary:
        out[0] = binary
    return out


def command_warnings(argv: List[str], role: str, expected_port: int) -> List[str]:
    notes: List[str] = []
    if normalize_role(role) == "embedding" and not has_flag(
        argv, ("--embeddings", "--embedding")
    ):
        notes.append("This embed command has no --embeddings flag.")
    port = parse_port(argv, expected_port)
    raw_port = flag_value(argv, ("--port", "-p"))
    if raw_port and port != int(expected_port):
        notes.append(
            f"Command port is {port}. This tab expects {int(expected_port)}."
        )
    if normalize_role(role) == "embedding":
        ctx_raw = flag_value(argv, ("-c", "--ctx-size"))
        try:
            ctx = int(ctx_raw) if ctx_raw else 0
        except ValueError:
            ctx = 0
        if ctx > 8192:
            notes.append(
                f"Context {ctx} is a chat-sized context. An embedding server "
                "only needs 8192 or below."
            )
        if not has_flag(argv, ("--pooling",)):
            notes.append(
                "No --pooling flag. Qwen3-VL-Embedding needs --pooling last."
            )
        ngl = flag_value(argv, ("-ngl", "--gpu-layers", "--n-gpu-layers")).lower()
        fit = flag_value(argv, ("-fit", "--fit")).lower()
        if ngl in ("auto",) or fit in ("on", "1", "true"):
            notes.append(
                "-ngl auto or -fit on made short prompts return null embeddings "
                "for Qwen3-VL-Embedding on this GPU. Use -ngl 99 and leave -fit off."
            )
    return notes


def load_saved_text(db_path: str, role: str) -> str:
    from WarpCore import settings_store

    return str(settings_store.get(db_path, role_key(role), "") or "").strip()


def save_saved_text(db_path: str, role: str, text: str, by: str = "llama-gui-tab") -> None:
    from WarpCore import settings_store

    settings_store.set(db_path, role_key(role), str(text or ""), by=by)


def saved_argv(db_path: str, role: str, binary: str) -> Optional[List[str]]:
    """Parsed argv for a saved command, or None when the box is empty.

    A non-empty line that does not parse raises ValueError.
    """
    text = load_saved_text(db_path, role)
    if not text:
        return None
    return with_resolved_binary(parse_llama_gui_command(text), binary)


def action_for_listener(listener: Optional[Dict[str, Any]]) -> str:
    """``free``, ``kill``, or ``refuse`` for a port listener."""
    if not listener:
        return "free"
    if listener.get("is_llama_server"):
        return "kill"
    return "refuse"


def _cmdline_port(argv: List[str], port: int) -> bool:
    raw = flag_value(argv, ("--port", "-p"))
    return str(raw) == str(int(port))


def find_port_listener(port: int) -> Optional[Dict[str, Any]]:
    """The process listening on ``port``, if one can be seen.

    A llama-server whose command line names the port counts even when the
    socket table is hidden. Any other listener is returned as foreign so the
    Launch button will not kill it.
    """
    try:
        import psutil
    except ImportError:
        return None
    port_i = int(port)
    llama_pid: Optional[int] = None
    try:
        processes = list(psutil.process_iter(["pid", "name", "cmdline"]))
    except Exception:
        processes = []
    for proc in processes:
        info = proc.info if hasattr(proc, "info") else {}
        name = str(info.get("name") or "")
        if "llama-server" not in name.lower():
            continue
        cmd = list(info.get("cmdline") or [])
        if _cmdline_port(cmd, port_i):
            try:
                llama_pid = int(info.get("pid") or proc.pid)
            except (TypeError, ValueError):
                continue
            break
    listen_pid: Optional[int] = None
    listen_name = ""
    try:
        connections = psutil.net_connections(kind="inet")
    except Exception:
        connections = []
    for conn in connections:
        status = str(getattr(conn, "status", "") or "")
        if status != getattr(psutil, "CONN_LISTEN", "LISTEN") and status != "LISTEN":
            continue
        laddr = getattr(conn, "laddr", None)
        if laddr is None or int(getattr(laddr, "port", -1) or -1) != port_i:
            continue
        pid = getattr(conn, "pid", None)
        name = ""
        if pid:
            try:
                name = str(psutil.Process(int(pid)).name() or "")
            except Exception:
                name = ""
        listen_pid = int(pid) if pid else None
        listen_name = name
        if "llama-server" in name.lower():
            return {
                "pid": listen_pid,
                "name": name or "llama-server",
                "is_llama_server": True,
            }
        return {
            "pid": listen_pid,
            "name": name,
            "is_llama_server": False,
        }
    if llama_pid is not None:
        return {"pid": llama_pid, "name": "llama-server", "is_llama_server": True}
    return None


def assess_port(port: int) -> Dict[str, Any]:
    listener = find_port_listener(port)
    action = action_for_listener(listener)
    pid = None if not listener else listener.get("pid")
    name = "" if not listener else str(listener.get("name") or "")
    if action == "free":
        message = f"Port {int(port)} is free."
    elif action == "kill":
        message = f"Stopping llama-server PID {pid} on port {int(port)}."
    else:
        who = name or (f"PID {pid}" if pid else "another program")
        message = (
            f"Port {int(port)} is in use by {who}. "
            "That is not llama-server, so it was left running."
        )
    return {"action": action, "pid": pid, "name": name, "message": message}


def _terminate_pid_tree(pid: int, timeout: float = 8.0) -> None:
    import psutil

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


def restart_llama_server(port: int, wait_s: float = 60.0) -> str:
    """Stop llama-server on this port and start the same command again.

    A NaN embedding poisons that GPU process. Later requests stay null until
    the process is replaced. A server on any other port is left running.
    """
    import subprocess
    import time
    import urllib.request

    listener = find_port_listener(port)
    if not listener or not listener.get("is_llama_server") or not listener.get("pid"):
        return f"Could not restart: port {int(port)} has no llama-server."
    pid = int(listener["pid"])
    try:
        import psutil

        proc = psutil.Process(pid)
        argv = [str(part) for part in (proc.cmdline() or [])]
        try:
            env = proc.environ()
        except Exception:
            env = os.environ.copy()
        try:
            cwd = proc.cwd()
        except Exception:
            cwd = None
    except Exception as exc:
        return f"Could not restart llama-server on port {int(port)}: {exc}"
    if not argv:
        return f"Could not restart: llama-server on port {int(port)} has no command line."
    _terminate_pid_tree(pid)
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(log_dir, f"llama-server-port{int(port)}-{stamp}.log")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as log_fp:
            subprocess.Popen(
                argv,
                cwd=cwd or None,
                env=env,
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
    except Exception as exc:
        return f"Could not restart llama-server on port {int(port)}: {exc}"
    health = f"http://127.0.0.1:{int(port)}/health"
    deadline = time.time() + float(wait_s)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=2) as resp:
                if resp.status == 200:
                    return (
                        f"Restarted llama-server on port {int(port)} "
                        f"after a null embedding. Log: {log_path}"
                    )
        except Exception:
            time.sleep(0.5)
    return (
        f"Could not restart: llama-server on port {int(port)} did not become healthy. "
        f"Log: {log_path}"
    )
