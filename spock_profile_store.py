"""Spock configuration profiles — re-export WarpCore.profile_store."""

from __future__ import annotations

import _warpcore_path

_warpcore_path.ensure()

from WarpCore.profile_store import (  # noqa: E402
    count_profiles,
    delete_profiles,
    ensure_schema,
    find_profile_by_name,
    get_profile,
    insert_profile,
    list_profile_summaries,
    list_profiles,
    stardate,
    upsert_profile,
)

__all__ = [
    "count_profiles",
    "delete_profiles",
    "ensure_schema",
    "find_profile_by_name",
    "get_profile",
    "insert_profile",
    "list_profile_summaries",
    "list_profiles",
    "stardate",
    "upsert_profile",
]
