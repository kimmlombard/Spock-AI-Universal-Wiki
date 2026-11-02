"""CLI: python -m spock_bringup acquire|up|down|status|reembed"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from spock_bringup import cmd_acquire, cmd_down, cmd_reembed, cmd_status, cmd_up
from spock_onboarding.llama_process import DEFAULT_CHAT_PORT, DEFAULT_EMBED_PORT


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=Path.cwd(), help="Install / repo root")

    p = argparse.ArgumentParser(prog="spock_bringup", description="Spock headless bringup")
    p.add_argument("--root", type=Path, default=Path.cwd(), help="Install / repo root")
    sub = p.add_subparsers(dest="cmd", required=True)

    ac = sub.add_parser(
        "acquire",
        parents=[common],
        help="Install llama-server + pick/download GGUFs",
    )
    ac.add_argument("--hf-token", default=None, help="HF token or path to token file")
    ac.add_argument("--no-download-llama", action="store_true")
    ac.add_argument("--no-download-models", action="store_true")
    # Explicit picks from the step 3 fit shortlist. Omit both repos to let
    # Acquire match the host recipe itself.
    ac.add_argument("--embed-repo", default="", help="HF GGUF repo for embeddings")
    ac.add_argument("--chat-repo", default="", help="HF GGUF repo for chat")
    ac.add_argument("--embed-quant", default="", help="e.g. Q8_0")
    ac.add_argument("--chat-quant", default="", help="e.g. Q4_K_M")
    ac.add_argument("--embed-n-ctx", type=int, default=0)
    ac.add_argument("--chat-n-ctx", type=int, default=0)

    up = sub.add_parser(
        "up",
        parents=[common],
        help="Attach or launch embed:8080 + chat:8081",
    )
    up.add_argument("--embed-port", type=int, default=DEFAULT_EMBED_PORT)
    up.add_argument("--chat-port", type=int, default=DEFAULT_CHAT_PORT)
    up.add_argument("--wait", type=float, default=180.0)

    dn = sub.add_parser("down", parents=[common], help="Stop llama-server processes")
    dn.add_argument(
        "--all",
        action="store_true",
        help="Stop discovered embed/chat, not only owned",
    )

    st = sub.add_parser(
        "status",
        parents=[common],
        help="Probe servers + write readiness JSON",
    )
    st.add_argument("--embed-port", type=int, default=DEFAULT_EMBED_PORT)
    st.add_argument("--chat-port", type=int, default=DEFAULT_CHAT_PORT)
    st.add_argument("--json", action="store_true", help="Print readiness JSON only")

    re = sub.add_parser(
        "reembed",
        parents=[common],
        help="Clear document embeddings for model switch (keeps documents)",
    )
    re.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Confirm clear without a prompt (required for menu/non-interactive)",
    )
    re.add_argument(
        "--embeddings-url",
        default="http://localhost:8080/embeddings",
    )

    args = p.parse_args(argv)
    root = args.root.resolve()

    if args.cmd == "acquire":
        result = cmd_acquire(
            root,
            hf_token=args.hf_token,
            download_llama=not args.no_download_llama,
            download_models=not args.no_download_models,
            embed_repo=args.embed_repo,
            chat_repo=args.chat_repo,
            embed_quant=args.embed_quant,
            chat_quant=args.chat_quant,
            embed_n_ctx=args.embed_n_ctx,
            chat_n_ctx=args.chat_n_ctx,
        )
        print(
            json.dumps({k: v for k, v in result.items() if k != "state"}, indent=2),
            flush=True,
        )
        return 0 if result.get("ok") else 1

    if args.cmd == "up":
        try:
            result = cmd_up(
                root,
                embed_port=args.embed_port,
                chat_port=args.chat_port,
                wait_s=args.wait,
            )
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr, flush=True)
            return 2
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in ("embed", "chat")},
                indent=2,
            ),
            flush=True,
        )
        return 0 if result.get("ok") else 1

    if args.cmd == "down":
        result = cmd_down(root, owned_only=not args.all)
        print(json.dumps(result, indent=2), flush=True)
        return 0

    if args.cmd == "status":
        result = cmd_status(root, embed_port=args.embed_port, chat_port=args.chat_port)
        if args.json:
            print(json.dumps(result.get("readiness") or {}, indent=2), flush=True)
        else:
            print(result.get("text") or "", flush=True)
        r = result.get("readiness") or {}
        if r.get("ui_ready") and r.get("servers_ready"):
            return 0
        if r.get("ui_ready") or r.get("servers_ready"):
            return 1
        return 2

    if args.cmd == "reembed":
        result = cmd_reembed(
            root,
            clear_only=True,
            assume_yes=bool(args.yes),
            embeddings_url=str(args.embeddings_url),
        )
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
