"""Load / save app config via WarpCore settings_store."""

from __future__ import annotations

from typing import Any, Dict, Optional

from spock_shell.paths import ROOT, SHIP_COMPUTER_DB, ensure_root_on_path

# One heal per process — suites load_config often; DB move is rare mid-run.
_PATH_HEAL_DONE = False
_LAST_PATH_HEAL: Optional[Dict[str, Any]] = None


def heal_paths_if_needed(*, force: bool = False) -> Dict[str, Any]:
    """Remap Spock_Console absolute paths after Linux↔Windows (or root) moves."""
    global _PATH_HEAL_DONE, _LAST_PATH_HEAL
    ensure_root_on_path()
    import _warpcore_path

    _warpcore_path.ensure()
    if _PATH_HEAL_DONE and not force:
        return _LAST_PATH_HEAL or {"ok": True, "skipped": True}
    from WarpCore.path_relocate import heal_relocated_paths

    report = heal_relocated_paths(SHIP_COMPUTER_DB, root=ROOT, by="suite")
    _PATH_HEAL_DONE = True
    _LAST_PATH_HEAL = report
    return report


def load_config() -> Dict[str, Any]:
    ensure_root_on_path()
    import _warpcore_path

    _warpcore_path.ensure()
    from WarpCore import settings_store

    heal_paths_if_needed()
    return settings_store.load_app_config(SHIP_COMPUTER_DB)


def save_config(config: Dict[str, Any], by: str = "suite") -> None:
    ensure_root_on_path()
    import _warpcore_path

    _warpcore_path.ensure()
    from WarpCore import settings_store

    settings_store.save_app_config(SHIP_COMPUTER_DB, config, by=by)
    # Keep install-root stamp aligned after saves from this host.
    try:
        from WarpCore.path_relocate import host_os_name

        settings_store.set(SHIP_COMPUTER_DB, "settings.spock_root", str(ROOT), by=by)
        settings_store.set(SHIP_COMPUTER_DB, "settings.host_os", host_os_name(), by=by)
    except Exception:
        pass
