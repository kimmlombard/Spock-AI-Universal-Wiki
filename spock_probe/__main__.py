"""python -m spock_probe — readiness / health report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from spock_bringup import cmd_status
from spock_onboarding.llama_process import DEFAULT_CHAT_PORT, DEFAULT_EMBED_PORT


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="spock_probe", description="Spock readiness probe")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--embed-port", type=int, default=DEFAULT_EMBED_PORT)
    p.add_argument("--chat-port", type=int, default=DEFAULT_CHAT_PORT)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    result = cmd_status(
        args.root.resolve(),
        embed_port=args.embed_port,
        chat_port=args.chat_port,
    )
    if args.json:
        print(json.dumps(result.get("readiness") or {}, indent=2))
    else:
        print(result.get("text") or "")
    r = result.get("readiness") or {}
    if r.get("ui_ready") and r.get("servers_ready"):
        return 0
    if r.get("ui_ready") or r.get("servers_ready"):
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
