"""CLI: python -m spock_status"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spock_onboarding.spock_status import (
    format_spock_status_report,
    probe_spock_status,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="spock_status", description="Spock Status report")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--embed-port", type=int, default=8080)
    p.add_argument("--chat-port", type=int, default=8081)
    p.add_argument("--rag-url", default="http://127.0.0.1:8090/health")
    p.add_argument("--mcp-host", default="127.0.0.1")
    p.add_argument("--mcp-port", type=int, default=8765)
    args = p.parse_args(argv)
    data = probe_spock_status(
        root=args.root.resolve(),
        embed_port=args.embed_port,
        chat_port=args.chat_port,
        rag_url=args.rag_url,
        mcp_host=args.mcp_host,
        mcp_port=args.mcp_port,
    )
    print(format_spock_status_report(data))
    return 0 if data.get("servers_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
