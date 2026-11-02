"""Good Results coach — short tips that cut Ask / Deep Dive trial-and-error.

Signals use live timing, Launch sizing heuristics, and Path filter vs question.
Tips are advisory only; they never change -c or filters automatically.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# Question looks like it is about this Spock install / UI.
_SPOCK_APP_RE = re.compile(
    r"\b("
    r"spock|navigation\s*station|bringup|wiki\s*scan|ask\s*ai|deep\s*dive|"
    r"host\s*recipe|launch\s*panel|ship'?s?\s*computer|embedding\s*status|"
    r"configure\s*spock|within\s+the\s+app|in[- ]app"
    r")\b",
    re.I,
)

_SPOCK_ROOT_MARKERS = (
    "spock-universal-ai-wiki",
    "spock-onboarding",
    "aihelperdocument",
)


def _norm(s: str) -> str:
    return os.path.normcase(os.path.normpath((s or "").replace("/", "\\")))


def path_filter_excludes_spock(path_filter: str) -> bool:
    """True when a non-empty Path filter likely hides Spock app sources."""
    raw = (path_filter or "").strip()
    if not raw:
        return False
    parts = [p.strip() for p in re.split(r"[;|]", raw) if p.strip()]
    if not parts:
        return False
    for part in parts:
        low = _norm(part).replace("\\", "/").lower()
        if any(m in low for m in _SPOCK_ROOT_MARKERS):
            return False
        # Bare fragment that still matches Spock tree names
        if "spock" in low and "llama.cpp" not in low:
            return False
    return True


def tip_path_vs_question(question: str, path_filter: str) -> Optional[str]:
    q = (question or "").strip()
    if not q or not _SPOCK_APP_RE.search(q):
        return None
    if not path_filter_excludes_spock(path_filter):
        return None
    return (
        "Tip: Path filter may hide Spock HELPERs / app code. "
        "Clear Path or add Spock-Universal-AI-Wiki when the question is about this app "
        "(keep a llama.cpp-only filter when you intend upstream-only answers)."
    )


def tip_pack_saturation(timing: Optional[Dict[str, Any]]) -> Optional[str]:
    """Deep Dive packed to the token window — suggest -c or narrower Path."""
    t = timing or {}
    mode = str(t.get("mode") or "")
    if mode != "deep_dive":
        return None
    try:
        pct = float(t.get("budget_used_pct") or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    if pct < 95.0:
        return None
    used = t.get("used_docs") if t.get("used_docs") is not None else t.get("docs_used")
    n_ctx = t.get("n_ctx")
    budget = t.get("budget")
    bits = [
        f"Tip: Deep Dive filled ~{pct:.0f}% of the pack budget"
    ]
    if used is not None:
        bits.append(f"({used} docs used)")
    if n_ctx:
        bits.append(f"at live n_ctx={n_ctx}")
    elif budget:
        bits.append(f"(budget {budget})")
    bits.append(
        "— raise Launch Context (-c) if VRAM allows (Suggest Context), "
        "or narrow Path so fewer large files compete for the window."
    )
    return " ".join(bits)


def tip_timeout() -> str:
    return (
        "Tip: Timeouts often mean the chat GGUF does not fit the GPU at this -c "
        "(layers spill to CPU/RAM). Check Task Manager GPU vs CPU, try Suggest Context "
        "/ a smaller quant, raise the client timeout (minutes), or continue until canceled "
        "if the server is still generating."
    )


def tip_launch_fit(
    *,
    model_path: str,
    n_ctx: int,
    vram_gb: float,
    role: str = "chat",
    sibling_size_gb: float = 0.0,
) -> Optional[str]:
    """Warn before Launch when weights+KV look too large for the selected GPU."""
    role = (role or "chat").lower()
    if role.startswith("embed"):
        return None
    path = Path(model_path or "")
    if not path.is_file():
        return None
    try:
        weights_gb = path.stat().st_size / (1024**3)
    except OSError:
        return None
    vram = float(vram_gb or 0.0)
    if vram <= 0:
        return None
    try:
        from spock_scanner_core import recommend_n_ctx
    except Exception:
        return None

    info = recommend_n_ctx(
        vram,
        role="chat",
        model_size_gb=weights_gb,
        sibling_size_gb=float(sibling_size_gb or 0.0),
    )
    recommended = int(info.get("n_ctx") or 0)
    headroom = info.get("headroom_gb")
    tips: List[str] = []

    # Weights alone exceed usable card (rough — ignores partial offload).
    if weights_gb * 1.05 > vram * 0.92:
        tips.append(
            f"GGUF ~{weights_gb:.1f}GB is tight for ~{vram:.0f}GB VRAM — "
            "expect CPU offload and slow/timeout Deep Dive answers."
        )
    if recommended and int(n_ctx) > recommended * 1.5:
        tips.append(
            f"Context (-c) {int(n_ctx)} is well above Suggest Context ({recommended}) "
            f"for this card/model — KV may force CPU layers."
        )
    if headroom is not None and float(headroom) <= 0 and weights_gb > 0:
        tips.append(
            "Little/no VRAM headroom left for KV after weights — "
            "lower -c via Suggest Context or use a smaller quant."
        )
    if not tips:
        return None
    return "Fit warning: " + " ".join(tips)


def collect_ask_tips(
    *,
    question: str,
    path_filter: str,
    timing: Optional[Dict[str, Any]] = None,
    answer: str = "",
    timed_out: bool = False,
) -> List[str]:
    """Ordered tips for the Ask AI panel (status + optional transcript line)."""
    tips: List[str] = []
    if timed_out or "timed out" in (answer or "").lower():
        tips.append(tip_timeout())
    pack = tip_pack_saturation(timing)
    if pack:
        tips.append(pack)
    path_tip = tip_path_vs_question(question, path_filter)
    if path_tip:
        tips.append(path_tip)
    return tips
