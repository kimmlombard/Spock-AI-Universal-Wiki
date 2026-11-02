"""Load / save app config via WarpCore settings_store."""

from __future__ import annotations

from typing import Any, Dict

from spock_shell.paths import SHIP_COMPUTER_DB, ensure_root_on_path


def load_config() -> Dict[str, Any]:
    ensure_root_on_path()
    import _warpcore_path

    _warpcore_path.ensure()
    from WarpCore import settings_store

    return settings_store.load_app_config(SHIP_COMPUTER_DB)


def save_config(config: Dict[str, Any], by: str = "suite") -> None:
    ensure_root_on_path()
    import _warpcore_path

    _warpcore_path.ensure()
    from WarpCore import settings_store

    settings_store.save_app_config(SHIP_COMPUTER_DB, config, by=by)
