"""Install root paths for Wiki Scan adapter."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIP_COMPUTER_DB = str(ROOT / "ship_computer.db")
WIKI_SCRIPT = ROOT / "wiki_agent.py"
WIKI_STATUS_SCRIPT = ROOT / "wiki_agent_status.py"
EMBED_HEALTH_SCRIPT = ROOT / "test_embeddings.py"
SCAN_CONFIG = ROOT / "scan_config.json"
