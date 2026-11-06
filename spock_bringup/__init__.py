"""Headless acquire / up / down / status orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from spock_onboarding import llmfit_bridge
from spock_onboarding.health import format_llama_line, probe_embed_chat, probe_llama_server
from spock_onboarding.llama_process import (
    DEFAULT_CHAT_PORT,
    DEFAULT_EMBED_PORT,
    LlamaProcessManager,
    wait_until_healthy,
)
from spock_onboarding.pick import (
    download_pair,
    pick_from_recipe,
    pick_from_selection,
    pick_model_pair,
    resolve_hf_token,
)
from spock_onboarding.readiness import (
    check_ui_ready,
    collect_next_ui_prompts,
    format_status_text,
    full_deps_marker,
    write_readiness,
)
from spock_onboarding.runtime import ensure_llama_server
from spock_onboarding.state import FirstModelsState

ProgressCb = Optional[Callable[[str], None]]
_MANAGER: Optional[LlamaProcessManager] = None


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)
    else:
        print(msg, flush=True)


def _root(root: Optional[Path] = None) -> Path:
    return Path(root) if root else Path.cwd()


def _mgr(root: Path, llama_server: str = "") -> LlamaProcessManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = LlamaProcessManager(
            llama_server_path=llama_server,
            log_dir=root / "logs",
        )
    elif llama_server:
        _MANAGER.llama_server_path = llama_server
    return _MANAGER


def _pinned_ngl() -> Tuple[Optional[str], str]:
    """The user's ``app.launch.ngl``, or ``(None, "")`` when it is left on auto."""
    try:
        from spock_shell.paths import SHIP_COMPUTER_DB
        from WarpCore.host_recipe import pinned_launch_settings

        ngl = str(pinned_launch_settings(SHIP_COMPUTER_DB).get("ngl") or "-1")
    except Exception:
        return None, ""
    if ngl == "-1":
        return None, ""
    return ngl, "pinned in app.launch.ngl"


def load_summary(root: Path) -> Optional[FirstModelsState]:
    return FirstModelsState.load(root)


def cmd_acquire(
    root: Optional[Path] = None,
    *,
    hf_token: Optional[str] = None,
    download_llama: bool = True,
    download_models: bool = True,
    embed_repo: str = "",
    chat_repo: str = "",
    embed_quant: str = "",
    chat_quant: str = "",
    embed_n_ctx: int = 0,
    chat_n_ctx: int = 0,
    cb: ProgressCb = None,
) -> Dict[str, Any]:
    """Ensure llama-server + GGUFs; write first_models_last.json.

    Model choice, in order: an explicit ``embed_repo``/``chat_repo`` pair (what
    the step 3 shortlist passes), else the best fit for the host recipe, else
    the static VRAM catalog.
    """
    root = _root(root)
    reasons: List[str] = []
    token = resolve_hf_token(hf_token)

    _log(cb, "Resolving llmfit (optional)...")
    if llmfit_bridge.available():
        exe = llmfit_bridge.find_llmfit_exe()
        via = str(exe) if exe else f"uvx ({llmfit_bridge.find_uvx()})"
        _log(cb, f"llmfit available via {via}")
    else:
        _log(cb, "llmfit not found (local exe or uvx); using catalog pick")

    _log(cb, "Ensuring llama-server...")
    try:
        llama_exe = ensure_llama_server(
            root, download_if_missing=download_llama, cb=cb
        )
    except Exception as e:
        reasons.append("NEED_LLAMA_SERVER")
        return {"ok": False, "reasons": reasons, "error": str(e)}

    if embed_repo and chat_repo:
        pick = pick_from_selection(
            embed_repo=embed_repo,
            chat_repo=chat_repo,
            embed_quant=embed_quant or "Q8_0",
            chat_quant=chat_quant or "Q4_K_M",
            embed_n_ctx=embed_n_ctx or 4096,
            chat_n_ctx=chat_n_ctx or 8192,
            note="selected from step 3 fit shortlist",
        )
    else:
        _log(cb, "Matching models to the host recipe...")
        pick = pick_from_recipe(root)
        if pick is None:
            _log(cb, "Host recipe unavailable; falling back to the VRAM catalog")
            pick = pick_model_pair()
    _log(cb, f"Model pick: {pick.note}")
    _log(cb, f"  embed {pick.embed_repo} {pick.embed_quant} -c {pick.embed_n_ctx}")
    _log(cb, f"  chat  {pick.chat_repo} {pick.chat_quant} -c {pick.chat_n_ctx}")

    embed_path = ""
    chat_path = ""
    if download_models:
        if not token:
            _log(
                cb,
                "No HF token — anonymous download (public GGUFs only; "
                "gated google/* repos remap to bartowski/* mirrors)",
            )
        try:
            from spock_onboarding.pick import prefer_public_pick

            pick = prefer_public_pick(pick, token=token)
            _log(cb, f"  embed {pick.embed_repo} {pick.embed_quant} -c {pick.embed_n_ctx}")
            _log(cb, f"  chat  {pick.chat_repo} {pick.chat_quant} -c {pick.chat_n_ctx}")
            embed_p, chat_p = download_pair(root, pick, token=token, cb=cb)
            embed_path = str(embed_p)
            chat_path = str(chat_p)
        except Exception as e:
            err = str(e)
            low = err.lower()
            if any(
                s in low
                for s in ("gated", "401", "403", "authenticated", "restricted")
            ):
                reasons.append("NEED_HF_TOKEN")
            else:
                reasons.append("NEED_MODELS")
            return {
                "ok": False,
                "reasons": reasons,
                "error": err,
                "llama_server_path": llama_exe,
                "pick_note": pick.note,
            }
    else:
        reasons.append("NEED_MODELS")

    state = FirstModelsState(
        root=root,
        runtime="llamacpp",
        llama_server_path=llama_exe,
        llama_install_dir=str(Path(llama_exe).parent),
        embed_model_id=pick.embed_repo,
        chat_model_id=pick.chat_repo,
        embed_gguf_path=embed_path,
        chat_gguf_path=chat_path,
        embed_n_ctx=pick.embed_n_ctx,
        chat_n_ctx=pick.chat_n_ctx,
        embed_quant=pick.embed_quant,
        chat_quant=pick.chat_quant,
        pick_note=pick.note,
    )
    path = state.write_summary_json()
    _log(cb, f"Wrote {path}")
    return {
        "ok": bool(embed_path and chat_path and llama_exe),
        "reasons": reasons,
        "summary_path": str(path),
        "state": state.summary_dict(),
    }


def _win_path_to_wsl(path: str) -> str:
    """Map ``D:\\foo`` → ``/mnt/d/foo`` when running under WSL/Linux."""
    import os
    import re

    raw = (path or "").strip().strip('"')
    if not raw or os.name == "nt":
        return raw
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if not m:
        return raw
    drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def _resolve_existing_file(path: str, root: Path) -> Optional[Path]:
    """Return an existing file path, healing Windows drive letters under WSL."""
    if not path:
        return None
    candidates = [Path(path)]
    healed = _win_path_to_wsl(path)
    if healed != path:
        candidates.append(Path(healed))
    # Same relative path under this Spock root (models synced or shared)
    try:
        p = Path(healed if healed != path else path)
        parts = list(p.parts)
        if "models" in parts:
            idx = parts.index("models")
            rel = Path(*parts[idx:])
            candidates.append(root / rel)
        if "tools" in parts and "llama-server" in parts:
            idx = parts.index("tools")
            rel = Path(*parts[idx:])
            candidates.append(root / rel)
    except Exception:
        pass
    for c in candidates:
        try:
            if c.is_file():
                return c.resolve()
        except OSError:
            continue
    return None


def _resolve_for_up(root: Path) -> FirstModelsState:
    state = load_summary(root)
    if state is None:
        raise FileNotFoundError(
            "first_models_last.json missing — run: python -m spock_bringup acquire"
        )
    from WarpCore.service_endpoints import is_runnable_host_binary

    llama = _resolve_existing_file(state.llama_server_path, root)
    if llama is None or not is_runnable_host_binary(llama):
        exe = ensure_llama_server(
            root, hint=state.llama_server_path, download_if_missing=False
        )
        state.llama_server_path = exe
    else:
        state.llama_server_path = str(llama)

    embed = _resolve_existing_file(state.embed_gguf_path, root)
    if embed is None:
        raise FileNotFoundError(
            f"embed GGUF missing: {state.embed_gguf_path} "
            "(under WSL use /mnt/d/... or copy models into this tree)"
        )
    state.embed_gguf_path = str(embed)

    chat = _resolve_existing_file(state.chat_gguf_path, root)
    if chat is None:
        raise FileNotFoundError(
            f"chat GGUF missing: {state.chat_gguf_path} "
            "(under WSL use /mnt/d/... or copy models into this tree)"
        )
    state.chat_gguf_path = str(chat)
    return state


def cmd_up(
    root: Optional[Path] = None,
    *,
    embed_port: int = DEFAULT_EMBED_PORT,
    chat_port: int = DEFAULT_CHAT_PORT,
    wait_s: float = 180.0,
    cb: ProgressCb = None,
) -> Dict[str, Any]:
    root = _root(root)
    state = _resolve_for_up(root)
    mgr = _mgr(root, state.llama_server_path)

    def maybe_attach_or_launch(
        *,
        role: str,
        port: int,
        model: str,
        n_ctx: int,
    ) -> Dict[str, Any]:
        probe = probe_llama_server("127.0.0.1", port, role_hint=role)
        if probe.get("reachable"):
            _log(cb, f"Attach {role} :{port} (already healthy)")
            return {"attached": True, "launched": False, "port": port, "probe": probe}

        # Host recipe owns GPU policy / tensor-split / -c; pinned app.launch.*
        # overrides -ngl and embed -np. Without this, dual-GPU hosts pin both
        # roles to CUDA 0 and Deep Dive starves for VRAM / context.
        plan_ov: Dict[str, Any] = {}
        try:
            from spock_shell.paths import SHIP_COMPUTER_DB
            from WarpCore.host_recipe import effective_recipe, launch_plan_for_role

            host = effective_recipe(SHIP_COMPUTER_DB, created_by="bringup-up")
            plan_ov = launch_plan_for_role(
                SHIP_COMPUTER_DB, host.get("recipe"), role
            )
            if plan_ov.get("n_ctx"):
                n_ctx = int(plan_ov["n_ctx"])
        except Exception as e:
            _log(cb, f"Host recipe unavailable for {role} ({e}); launching without it")

        ngl, ngl_why = _pinned_ngl()
        if ngl is None:
            if plan_ov.get("ngl") and str(plan_ov.get("ngl")) != "-1":
                ngl = str(plan_ov["ngl"])
                ngl_why = str(plan_ov.get("ngl_source") or "host recipe")
            else:
                ngl, ngl_why = llmfit_bridge.resolve_ngl(model, n_ctx=n_ctx)

        ts = str(plan_ov.get("tensor_split") or "")
        sm = str(plan_ov.get("split_mode") or "")
        _log(
            cb,
            f"Launch {role} :{port} ngl={ngl} ({ngl_why}) -c {n_ctx}"
            + (f" tensor-split {ts}" if ts and role == "chat" else "")
            + (
                f" -ncmoe {int(plan_ov.get('n_cpu_moe') or 0)}"
                if role == "chat" and int(plan_ov.get("n_cpu_moe") or 0) > 0
                else ""
            )
            + (
                f" --reasoning {plan_ov.get('reasoning')}"
                if role == "chat" and plan_ov.get("reasoning")
                else ""
            )
            + (
                f" CUDA_VISIBLE_DEVICES={plan_ov.get('cuda_device')}"
                if plan_ov.get("pin_cuda") and plan_ov.get("cuda_device") not in (None, "")
                else (" (multi-GPU)" if ts and role == "chat" else "")
            )
        )
        inst = mgr.launch(
            model,
            port,
            ngl=ngl,
            role=role,
            n_ctx=n_ctx,
            split_mode=sm,
            tensor_split=ts,
            n_parallel=plan_ov.get("n_parallel"),
            pin_cuda=plan_ov.get("pin_cuda"),
            cuda_device=str(plan_ov.get("cuda_device") or ""),
            n_cpu_moe=int(plan_ov.get("n_cpu_moe") or 0),
            reasoning=str(plan_ov.get("reasoning") or ""),
        )
        probe = wait_until_healthy(
            probe_llama_server,
            "127.0.0.1",
            port,
            role_hint=role,
            timeout_s=wait_s,
        )
        return {
            "attached": False,
            "launched": True,
            "port": port,
            "pid": inst.pid,
            "probe": probe,
            "ngl": ngl,
        }

    embed_info = maybe_attach_or_launch(
        role="embedding",
        port=embed_port,
        model=state.embed_gguf_path,
        n_ctx=state.embed_n_ctx,
    )
    chat_info = maybe_attach_or_launch(
        role="chat",
        port=chat_port,
        model=state.chat_gguf_path,
        n_ctx=state.chat_n_ctx,
    )

    servers_ready = bool(
        (embed_info.get("probe") or {}).get("reachable")
        and (chat_info.get("probe") or {}).get("reachable")
    )
    ui = check_ui_ready(root)
    token = resolve_hf_token()
    reasons: List[str] = []
    if not servers_ready:
        reasons.append("SERVERS_NOT_READY")
    if not ui.get("ui_ready"):
        reasons.append("UI_NOT_READY")

    path = write_readiness(
        root,
        ui_ready=bool(ui.get("ui_ready")),
        servers_ready=servers_ready,
        full_deps_ok=full_deps_marker(root),
        venv_python=str(ui.get("venv_python") or ""),
        embed={
            "port": embed_port,
            "reachable": bool((embed_info.get("probe") or {}).get("reachable")),
            "model_path": state.embed_gguf_path,
            "model_name": Path(state.embed_gguf_path).name,
            "pid": embed_info.get("pid"),
            "attached": embed_info.get("attached"),
        },
        chat={
            "port": chat_port,
            "reachable": bool((chat_info.get("probe") or {}).get("reachable")),
            "model_path": state.chat_gguf_path,
            "model_name": Path(state.chat_gguf_path).name,
            "pid": chat_info.get("pid"),
            "attached": chat_info.get("attached"),
        },
        reasons=reasons,
        next_ui_prompts=collect_next_ui_prompts(root, hf_token_present=bool(token)),
    )
    _log(cb, format_llama_line(embed_info.get("probe") or {}, label="embed"))
    _log(cb, format_llama_line(chat_info.get("probe") or {}, label="chat"))
    _log(cb, f"Readiness -> {path}")
    return {
        "ok": servers_ready,
        "embed": embed_info,
        "chat": chat_info,
        "readiness_path": str(path),
        "servers_ready": servers_ready,
        "ui_ready": bool(ui.get("ui_ready")),
    }


def cmd_reembed(
    root: Optional[Path] = None,
    *,
    clear_only: bool = True,
    assume_yes: bool = False,
    embeddings_url: str = "http://localhost:8080/embeddings",
    cb: ProgressCb = None,
) -> Dict[str, Any]:
    """Clear document embeddings (keep docs) and print next steps / live status."""
    from spock_rag_adapter.reembed import (
        clear_embeddings,
        embedding_status,
        format_clear_result,
        format_status,
    )

    root = _root(root)
    db = str(root / "ship_computer.db")
    if not assume_yes:
        _log(
            cb,
            "Use --yes for non-interactive clear. Refusing without confirmation flag.",
        )
        return {"ok": False, "error": "confirmation required (--yes)"}

    _log(cb, f"Clearing embeddings in {db} (documents kept)...")
    cleared = clear_embeddings(db)
    for line in format_clear_result(cleared).splitlines():
        _log(cb, line)

    status = embedding_status(db, embeddings_url=embeddings_url)
    _log(cb, "")
    _log(cb, "Status after clear:")
    for line in format_status(status).splitlines():
        _log(cb, line)

    live = status.get("live") or {}
    ready = bool(live.get("reachable") and live.get("model_path"))
    if clear_only or not ready:
        if not ready:
            _log(
                cb,
                "Embedding server not ready - run Bringup step 3-4, then step 9 Wiki Scan.",
            )
        return {
            "ok": True,
            "cleared": cleared,
            "status": status,
            "ready_for_scan": ready,
        }

    return {
        "ok": True,
        "cleared": cleared,
        "status": status,
        "ready_for_scan": ready,
    }


def cmd_down(
    root: Optional[Path] = None,
    *,
    owned_only: bool = True,
    cb: ProgressCb = None,
) -> Dict[str, Any]:
    root = _root(root)
    state = load_summary(root)
    llama = (state.llama_server_path if state else "") or ""
    mgr = _mgr(root, llama)
    if owned_only:
        n = mgr.stop_owned()
        _log(cb, f"Stopped {n} owned llama-server process(es)")
        return {"ok": True, "stopped": n, "owned_only": True}
    n = 0
    for role in ("embedding", "chat"):
        n += mgr.stop_role(role)
    _log(cb, f"Stopped {n} embedding/chat llama-server process(es)")
    return {"ok": True, "stopped": n, "owned_only": False}


def cmd_status(
    root: Optional[Path] = None,
    *,
    embed_port: int = DEFAULT_EMBED_PORT,
    chat_port: int = DEFAULT_CHAT_PORT,
    cb: ProgressCb = None,
) -> Dict[str, Any]:
    root = _root(root)
    probes = probe_embed_chat(embed_port=embed_port, chat_port=chat_port)
    ui = check_ui_ready(root)
    token = resolve_hf_token()
    reasons: List[str] = []
    if not probes["servers_ready"]:
        reasons.append("SERVERS_NOT_READY")
    if not ui.get("ui_ready"):
        reasons.append("UI_NOT_READY")
    state = load_summary(root)
    if state is None:
        reasons.append("NEED_ACQUIRE")
    path = write_readiness(
        root,
        ui_ready=bool(ui.get("ui_ready")),
        servers_ready=bool(probes["servers_ready"]),
        full_deps_ok=full_deps_marker(root),
        venv_python=str(ui.get("venv_python") or ""),
        embed={
            "port": embed_port,
            **{
                k: probes["embed"].get(k)
                for k in ("reachable", "model_path", "model_name", "n_ctx")
            },
        },
        chat={
            "port": chat_port,
            **{
                k: probes["chat"].get(k)
                for k in ("reachable", "model_path", "model_name", "n_ctx")
            },
        },
        reasons=reasons,
        next_ui_prompts=collect_next_ui_prompts(root, hf_token_present=bool(token)),
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    text = format_status_text(data)
    _log(cb, text)
    return {
        "ok": bool(probes["servers_ready"] and ui.get("ui_ready")),
        "readiness": data,
        "text": text,
    }
