"""Install root paths for MCP adapter (Spock-Onboarding)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIP_COMPUTER_DB = str(ROOT / "ship_computer.db")
