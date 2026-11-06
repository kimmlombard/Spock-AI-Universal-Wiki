"""Lean embed+chat GGUF pick + download for greenfield bringup."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

ProgressCb = Optional[Callable[[str], None]]


@dataclass
class ModelPick:
    embed_repo: str
    chat_repo: str
    embed_quant: str
    chat_quant: str
    embed_n_ctx: int
    chat_n_ctx: int
    note: str


# Conservative catalog ordered by approximate VRAM need (chat-dominant).
# Prefer *public* GGUF mirrors so a GitHub try-out works without HF_TOKEN.
# Official google/* Gemma repos are gated (license click-through + auth).
_CATALOG: List[Tuple[float, ModelPick]] = [
    (
        20.0,
        ModelPick(
            "ggml-org/embeddinggemma-2-GGUF",
            "bartowski/gemma-3-12b-it-GGUF",
            "Q8_0",
            "Q4_K_M",
            4096,
            32768,
            "High VRAM: EmbeddingGemma 2 + Gemma 3 12B (public mirror)",
        ),
    ),
    (
        10.0,
        ModelPick(
            "ggml-org/embeddinggemma-2-GGUF",
            "bartowski/gemma-3-4b-it-GGUF",
            "Q8_0",
            "Q4_K_M",
            2048,
            16384,
            "Mid VRAM: EmbeddingGemma 2 + Gemma 3 4B (public mirror)",
        ),
    ),
    (
        0.0,
        ModelPick(
            "ggml-org/embeddinggemma-2-GGUF",
            "bartowski/gemma-2-9b-it-GGUF",
            "Q8_0",
            "Q4_K_M",
            2048,
            8192,
            "Low VRAM / CPU-friendly: EmbeddingGemma 2 + Gemma 2 9B",
        ),
    ),
]

# When no HF token, remap gated official Google repos to public GGUF mirrors.
# Values are (public_repo_id, preferred_quant_or_None_to_keep).
_GATED_REPO_PUBLIC_FALLBACK: dict = {
    "google/gemma-3-4b-it-qat-q4_0-gguf": ("bartowski/gemma-3-4b-it-GGUF", "Q4_K_M"),
    "google/gemma-3-12b-it-qat-q4_0-gguf": ("bartowski/gemma-3-12b-it-GGUF", "Q4_K_M"),
    "google/gemma-3-27b-it-qat-q4_0-gguf": ("bartowski/gemma-3-27b-it-GGUF", "Q4_K_M"),
    # Common alternate spellings / non-qat ids still under google/
    "google/gemma-3-4b-it-GGUF": ("bartowski/gemma-3-4b-it-GGUF", "Q4_K_M"),
    "google/gemma-3-12b-it-GGUF": ("bartowski/gemma-3-12b-it-GGUF", "Q4_K_M"),
}


def estimate_vram_gb() -> float:
    env = os.environ.get("SPOCK_VRAM_GB", "").strip()
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    try:
        from spock_onboarding import llmfit_bridge

        info = llmfit_bridge.system_info()
        if isinstance(info, dict):
            for key in ("vram_gb", "gpu_vram_gb", "total_vram_gb"):
                if info.get(key) is not None:
                    return float(info[key])
            gpus = info.get("gpus") or info.get("gpu") or []
            if isinstance(gpus, list) and gpus and isinstance(gpus[0], dict):
                for k in ("vram_gb", "memory_gb", "total_memory_gb"):
                    if gpus[0].get(k) is not None:
                        return float(gpus[0][k])
    except Exception:
        pass
    return 8.0


def pick_model_pair(vram_gb: Optional[float] = None) -> ModelPick:
    """Pick the highest catalog tier whose min VRAM the machine meets."""
    vram = float(vram_gb if vram_gb is not None else estimate_vram_gb())
    # _CATALOG is ordered high→low VRAM floors
    for min_vram, pick in _CATALOG:
        if vram >= min_vram:
            return ModelPick(
                pick.embed_repo,
                pick.chat_repo,
                pick.embed_quant,
                pick.chat_quant,
                pick.embed_n_ctx,
                pick.chat_n_ctx,
                f"{pick.note} (vram~{vram:.1f}GB)",
            )
    pick = _CATALOG[-1][1]
    return ModelPick(
        pick.embed_repo,
        pick.chat_repo,
        pick.embed_quant,
        pick.chat_quant,
        pick.embed_n_ctx,
        pick.chat_n_ctx,
        f"{pick.note} (vram~{vram:.1f}GB)",
    )


def pick_from_recipe(root: Optional[Path] = None) -> Optional[ModelPick]:
    """Best-fitting pair for the host recipe, or None when it cannot be read.

    This is the headless twin of the Bringup step 3 shortlist: same recipe,
    same fit maths, top pick per role instead of a menu.
    """
    try:
        from spock_onboarding.fit_select import shortlists
        from spock_shell.paths import SHIP_COMPUTER_DB
        from WarpCore import host_recipe as hr

        plan = hr.effective_recipe(
            SHIP_COMPUTER_DB,
            reason="Auto-created for Acquire",
            created_by="acquire",
        )
        recipe = plan["recipe"]
        hardware = plan["hardware"]
        lists = shortlists(recipe=recipe, hardware=hardware, limit=1, use_hub=True)
        embed = (lists.get("embed") or {}).get("picks") or []
        chat = (lists.get("chat") or {}).get("picks") or []
        if not embed or not chat:
            return None
        e, c = embed[0], chat[0]
        note = (
            f"recipe fit ({plan['source']}, {hardware.get('gpu_summary')}, "
            f"ram {hardware.get('host_ram_gb')}GB): "
            f"embed {e.get('fit_level')} ~{e.get('need_gb')}GB, "
            f"chat {c.get('fit_level')} ~{c.get('need_gb')}GB"
        )
        if plan["drift"]:
            note += " — hardware drift: " + "; ".join(plan["drift"])
        return ModelPick(
            str(e["id"]),
            str(c["id"]),
            str(e.get("fit_quant") or "q8_0").upper(),
            str(c.get("fit_quant") or "q4_k_m").upper(),
            int(e.get("fit_n_ctx") or 4096),
            int(c.get("fit_n_ctx") or 8192),
            note,
        )
    except Exception:
        return None


def pick_from_selection(
    *,
    embed_repo: str,
    chat_repo: str,
    embed_quant: str = "Q8_0",
    chat_quant: str = "Q4_K_M",
    embed_n_ctx: int = 4096,
    chat_n_ctx: int = 8192,
    note: str = "user selection",
) -> ModelPick:
    """Pair the user chose from the step 3 fit shortlist."""
    return ModelPick(
        embed_repo,
        chat_repo,
        (embed_quant or "Q8_0").upper(),
        (chat_quant or "Q4_K_M").upper(),
        int(embed_n_ctx or 4096),
        int(chat_n_ctx or 8192),
        note,
    )


def _quant_tokens(q: str) -> List[str]:
    q = (q or "").upper().replace(".", "_")
    return [q, q.replace("_", "-"), q.lower()]


def _find_gguf(folder: Path, quant: str) -> Optional[Path]:
    if not folder.is_dir():
        return None
    tokens = _quant_tokens(quant)
    ggufs = sorted(folder.rglob("*.gguf"))
    for g in ggufs:
        name = g.name.upper()
        if any(t.upper().replace("-", "_") in name.replace("-", "_") for t in tokens):
            return g
    return ggufs[0] if ggufs else None


def public_repo_fallback(repo_id: str) -> Optional[Tuple[str, Optional[str]]]:
    """Return ``(public_repo, quant_override)`` for a known gated HF id, else None."""
    key = (repo_id or "").strip()
    hit = _GATED_REPO_PUBLIC_FALLBACK.get(key)
    if hit:
        return hit
    # Soft match: google/gemma-3-4b* → bartowski 4b, etc.
    low = key.lower()
    if low.startswith("google/gemma-3-4b"):
        return ("bartowski/gemma-3-4b-it-GGUF", "Q4_K_M")
    if low.startswith("google/gemma-3-12b"):
        return ("bartowski/gemma-3-12b-it-GGUF", "Q4_K_M")
    if low.startswith("google/gemma-3-27b"):
        return ("bartowski/gemma-3-27b-it-GGUF", "Q4_K_M")
    return None


def prefer_public_pick(pick: ModelPick, *, token: Optional[str] = None) -> ModelPick:
    """Rewrite a pick to public mirrors when the user has no HF token."""
    if token:
        return pick
    embed_repo, embed_quant = pick.embed_repo, pick.embed_quant
    chat_repo, chat_quant = pick.chat_repo, pick.chat_quant
    notes: List[str] = []
    emb_fb = public_repo_fallback(embed_repo)
    if emb_fb:
        embed_repo, q = emb_fb
        if q:
            embed_quant = q
        notes.append(f"embed {pick.embed_repo} → {embed_repo}")
    chat_fb = public_repo_fallback(chat_repo)
    if chat_fb:
        chat_repo, q = chat_fb
        if q:
            chat_quant = q
        notes.append(f"chat {pick.chat_repo} → {chat_repo}")
    if not notes:
        return pick
    note = pick.note
    suffix = "public mirror (no HF token): " + "; ".join(notes)
    note = f"{note}; {suffix}" if note else suffix
    return ModelPick(
        embed_repo=embed_repo,
        chat_repo=chat_repo,
        embed_quant=embed_quant,
        chat_quant=chat_quant,
        embed_n_ctx=pick.embed_n_ctx,
        chat_n_ctx=pick.chat_n_ctx,
        note=note,
    )


def _is_hf_auth_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        s in text
        for s in (
            "401",
            "403",
            "gated",
            "restricted",
            "cannot access gated",
            "invalid username",
            "must have access",
            "be authenticated",
        )
    )


def download_repo_gguf(
    repo_id: str,
    dest_dir: Path,
    *,
    quant: str,
    token: Optional[str] = None,
    cb: ProgressCb = None,
    allow_public_fallback: bool = True,
) -> Path:
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError as e:
        raise RuntimeError("huggingface_hub is required for model download") from e

    dest_dir.mkdir(parents=True, exist_ok=True)
    existing = _find_gguf(dest_dir, quant)
    if existing:
        if cb:
            cb(f"Using existing {existing.name}")
        return existing

    def _pull(rid: str, q: str, into: Path) -> Path:
        into.mkdir(parents=True, exist_ok=True)
        hit = _find_gguf(into, q)
        if hit:
            if cb:
                cb(f"Using existing {hit.name}")
            return hit
        if cb:
            cb(f"Listing files for {rid} …")
        files = list_repo_files(rid, repo_type="model", token=token)
        ggufs = [f for f in files if f.lower().endswith(".gguf")]
        if not ggufs:
            raise RuntimeError(f"No GGUF files in {rid}")

        tokens = _quant_tokens(q)
        chosen = None
        for f in ggufs:
            up = f.upper().replace("-", "_")
            if any(t.upper().replace("-", "_") in up for t in tokens):
                chosen = f
                break
        if chosen is None:
            for pref in ("Q4_K_M", "Q5_K_M", "Q8_0", "Q4_0"):
                for f in ggufs:
                    if pref in f.upper().replace("-", "_"):
                        chosen = f
                        break
                if chosen:
                    break
        if chosen is None:
            chosen = ggufs[0]

        if cb:
            cb(f"Downloading {rid}/{chosen} …")
        path = hf_hub_download(
            repo_id=rid,
            filename=chosen,
            local_dir=str(into),
            token=token,
        )
        return Path(path)

    try:
        return _pull(repo_id, quant, dest_dir)
    except Exception as e:
        fb = public_repo_fallback(repo_id) if allow_public_fallback else None
        if not fb or token or not _is_hf_auth_error(e):
            if _is_hf_auth_error(e) and not token:
                raise RuntimeError(
                    f"{e}\n\n"
                    f"Repo {repo_id} requires Hugging Face login (gated model). "
                    "Spock try-out does not require a token for public GGUFs — "
                    "pick a bartowski/* or ggml-org/* mirror, or set HF_TOKEN after "
                    "accepting the model license on huggingface.co."
                ) from e
            raise
        alt_repo, alt_quant = fb
        use_quant = alt_quant or quant
        alt_dir = dest_dir.parent / alt_repo.split("/")[-1]
        if cb:
            cb(
                f"{repo_id} is gated without HF_TOKEN — "
                f"retrying public mirror {alt_repo} ({use_quant})"
            )
        return _pull(alt_repo, use_quant, alt_dir)


def download_pair(
    root: Path,
    pick: ModelPick,
    *,
    token: Optional[str] = None,
    cb: ProgressCb = None,
) -> Tuple[Path, Path]:
    pick = prefer_public_pick(pick, token=token)
    if cb and "public mirror" in (pick.note or ""):
        cb(f"Model pick adjusted: {pick.note}")
    models = root / "models"
    embed_dir = models / pick.embed_repo.split("/")[-1]
    chat_dir = models / pick.chat_repo.split("/")[-1]
    embed = download_repo_gguf(
        pick.embed_repo, embed_dir, quant=pick.embed_quant, token=token, cb=cb
    )
    chat = download_repo_gguf(
        pick.chat_repo, chat_dir, quant=pick.chat_quant, token=token, cb=cb
    )
    return embed, chat


def resolve_hf_token(explicit: Optional[str] = None) -> Optional[str]:
    if explicit and explicit.strip():
        p = Path(explicit.strip())
        if p.is_file():
            return p.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        return explicit.strip()
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "SPOCK_HF_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    for cand in (Path(".HF_TOKEN"), Path(".env")):
        if cand.is_file():
            try:
                for line in cand.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.upper().startswith("HF_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
                    if cand.name == ".HF_TOKEN":
                        return line
            except OSError:
                pass
    return None
