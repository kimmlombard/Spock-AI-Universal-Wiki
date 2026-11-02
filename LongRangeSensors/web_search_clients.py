"""Thin GitHub + Brave Search API clients for Spock right-dock Run Search.

No UI / no DB writes. Env overrides config:
  GITHUB_TOKEN / BRAVE_API_KEY first, then app_config.json → search.*
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

USER_AGENT = "Spock-to-bridge-ExternalSearch/1.0"

# GitHub Search is keyword/operator based — not natural-language Q&A.
_GH_STOP = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "how",
    "what", "which", "where", "when", "who", "why", "does", "do", "is",
    "are", "can", "with", "this", "that", "from", "into", "about", "me",
    "my", "please", "find", "show", "get", "good", "best", "great",
    "replacement", "alternative", "alternatives", "instead", "vs",
    "repo", "repos", "repository", "repositories", "project", "projects",
    "github", "looking", "need", "want", "like", "similar",
}

_GH_OPERATOR_RE = re.compile(
    r"\b(language|user|org|repo|in|stars|forks|created|pushed|size|license|topic|is|mirror|archived|followers):\S+",
    re.I,
)


def merge_search_config(raw: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    cfg = {"github_token": "", "brave_api_key": ""}
    if raw:
        for k in cfg:
            if raw.get(k) is not None:
                cfg[k] = str(raw.get(k) or "")
    # Env wins when set
    env_gh = os.environ.get("GITHUB_TOKEN", "").strip()
    env_brave = os.environ.get("BRAVE_API_KEY", "").strip()
    if env_gh:
        cfg["github_token"] = env_gh
    if env_brave:
        cfg["brave_api_key"] = env_brave
    return cfg


def resolve_credentials(search_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    return merge_search_config(search_cfg)


def github_search_query(user_query: str) -> Tuple[str, bool]:
    """Turn a natural-language question into GitHub Search keywords.

    Returns (api_q, rewritten). If the user already used GitHub operators or a
    short keyword string, the original query is kept.
    """
    raw = (user_query or "").strip()
    if not raw:
        return "", False
    # Already looks like GitHub search syntax
    if _GH_OPERATOR_RE.search(raw) or " OR " in raw or " AND " in raw:
        return raw, False
    # Quoted phrase / short keyword — pass through
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9._\-/+]{1,}", raw)
    if not tokens:
        return raw, False
    if len(tokens) <= 3 and not raw.endswith("?"):
        return raw, False

    kept: List[str] = []
    seen = set()
    for t in tokens:
        low = t.lower()
        if low in _GH_STOP or low in seen:
            continue
        seen.add(low)
        kept.append(t)
        if len(kept) >= 8:
            break
    if not kept:
        return raw, False
    rewritten = " ".join(kept)
    return rewritten, rewritten.lower() != raw.lower()


def _normalize_item(
    *,
    title: str,
    url: str,
    snippet: str,
    source: str,
    meta: str = "",
    kind: str = "web",
) -> Dict[str, Any]:
    return {
        "title": title or "(untitled)",
        "url": url or "",
        "snippet": snippet or "",
        "source": source,
        "meta": meta or "",
        "kind": kind,  # "github_repo" | "web"
    }


def search_github_repos(
    query: str,
    *,
    limit: int = 10,
    token: str = "",
    timeout: float = 30.0,
) -> Tuple[List[Dict[str, Any]], str]:
    """Search GitHub repositories. Returns (items, status_note)."""
    raw_q = (query or "").strip()
    if not raw_q:
        return [], "Empty query"

    q, rewritten = github_search_query(raw_q)

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    tok = (token or "").strip()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    per_page = max(1, min(int(limit or 10), 100))
    try:
        r = requests.get(
            GITHUB_SEARCH_URL,
            headers=headers,
            params={"q": q, "sort": "stars", "order": "desc", "per_page": per_page},
            timeout=timeout,
        )
    except requests.RequestException as e:
        return [], f"GitHub request failed: {e}"

    if r.status_code == 401:
        return [], "GitHub auth failed - check GITHUB_TOKEN / search.github_token"
    if r.status_code == 403:
        remaining = r.headers.get("X-RateLimit-Remaining", "?")
        return [], (
            f"GitHub rate limited (remaining={remaining}). "
            "Set GITHUB_TOKEN for higher limits."
        )
    if r.status_code != 200:
        return [], f"GitHub HTTP {r.status_code}: {(r.text or '')[:240]}"

    try:
        data = r.json()
    except Exception as e:
        return [], f"GitHub JSON error: {e}"

    items_raw = data.get("items") or []
    out: List[Dict[str, Any]] = []
    for repo in items_raw:
        owner = (repo.get("owner") or {}).get("login", "")
        name = repo.get("name", "")
        full = repo.get("full_name") or f"{owner}/{name}"
        desc = repo.get("description") or ""
        stars = repo.get("stargazers_count", 0)
        lang = repo.get("language") or "?"
        url = repo.get("html_url") or f"https://github.com/{full}"
        out.append(
            _normalize_item(
                title=full,
                url=url,
                snippet=desc,
                source="github",
                meta=f"stars:{stars} · {lang}",
                kind="github_repo",
            )
        )

    note = f"GitHub: {len(out)} repo(s)"
    if rewritten:
        note += f' (query rewritten to "{q}")'
    if not tok:
        note += " (no token: lower rate limits; set GITHUB_TOKEN optional)"
    if not out:
        note += (
            " - try keywords like: singlefile OR SingleFile language:javascript"
        )
    return out, note


def search_brave_web(
    query: str,
    *,
    limit: int = 10,
    api_key: str = "",
    timeout: float = 30.0,
) -> Tuple[List[Dict[str, Any]], str]:
    """Brave Web Search API. Returns (items, status_note)."""
    q = (query or "").strip()
    if not q:
        return [], "Empty query"

    key = (api_key or "").strip()
    if not key:
        return [], (
            "Brave API key missing. Set BRAVE_API_KEY or "
            "app_config.json -> search.brave_api_key"
        )

    count = max(1, min(int(limit or 10), 20))
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": key,
        "User-Agent": USER_AGENT,
    }
    try:
        r = requests.get(
            BRAVE_SEARCH_URL,
            headers=headers,
            params={"q": q, "count": count},
            timeout=timeout,
        )
    except requests.RequestException as e:
        return [], f"Brave request failed: {e}"

    if r.status_code in (401, 403):
        return [], f"Brave auth failed (HTTP {r.status_code}) — check BRAVE_API_KEY"
    if r.status_code != 200:
        return [], f"Brave HTTP {r.status_code}: {(r.text or '')[:240]}"

    try:
        data = r.json()
    except Exception as e:
        return [], f"Brave JSON error: {e}"

    web = (data.get("web") or {}).get("results") or []
    out: List[Dict[str, Any]] = []
    for item in web[:count]:
        out.append(
            _normalize_item(
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("description") or "",
                source="brave",
                meta=item.get("age") or "",
                kind="web",
            )
        )
    return out, f"Brave: {len(out)} result(s)"


def run_external_search(
    source: str,
    query: str,
    *,
    limit: int = 10,
    search_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Dispatch by Source combo text. Returns (items, status_or_error)."""
    creds = resolve_credentials(search_cfg)
    src = (source or "").strip().lower()

    if "github" in src:
        return search_github_repos(
            query, limit=limit, token=creds.get("github_token", "")
        )
    if "brave" in src:
        return search_brave_web(
            query, limit=limit, api_key=creds.get("brave_api_key", "")
        )
    if "huggingface" in src or "hugging face" in src:
        return [], "HuggingFace live search is not wired yet (stub)."
    if "kaggle" in src:
        return [], "Kaggle live search is not wired yet (stub)."
    return [], f"Unknown search source: {source}"
