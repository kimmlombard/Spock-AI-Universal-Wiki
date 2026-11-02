#!/usr/bin/env python3
"""Pre-scan ShareX PNGs in ./assets → resized JPG gallery via LM Studio vision.

Does not modify files under assets/. Workspace defaults to C:\\Spock-Images-Temp.
Writes D:\\Spock-AI-Universal-Wiki\\gallery\\ (docs/images/, manifest.json, docs/*.md).
MkDocs only serves files under docs_dir, so JPEGs live in docs/images/.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSETS = ROOT / "assets"
DEFAULT_TEMP = Path(r"C:\Spock-Images-Temp")
DEFAULT_GALLERY = ROOT / "gallery"
DEFAULT_LM = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen/qwen3.8-27b"

PROMPT = (
    "Describe this Spock UI screenshot for documentation. "
    'Reply with JSON only (no markdown fences): '
    '{"slug":"kebab-case-short-title","caption":"1-2 factual sentences"}. '
    "Slug: lowercase letters, digits, hyphens; 3-8 words; no extension. "
    "Caption: mention the visible Spock panel or feature when recognizable."
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _slugify(text: str, fallback: str) -> str:
    s = (text or "").strip().lower()
    s = s.replace("_", "-").replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]+", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if not s:
        s = re.sub(r"[^a-z0-9\-]+", "-", fallback.lower()).strip("-") or "screenshot"
    return s[:80]


def _parse_model_json(raw: str) -> Tuple[str, str]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            slug = str(data.get("slug") or "")
            caption = str(data.get("caption") or data.get("description") or "").strip()
            return slug, caption
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return (
                    str(data.get("slug") or ""),
                    str(data.get("caption") or data.get("description") or "").strip(),
                )
        except json.JSONDecodeError:
            pass
    # Fallback: first line slug-ish, rest caption
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    caption = " ".join(lines)[:400] if lines else "Spock UI screenshot."
    return "", caption


def _pick_model(base: str, preferred: str, timeout: float) -> str:
    try:
        r = requests.get(f"{base.rstrip('/')}/models", timeout=timeout)
        r.raise_for_status()
        data = r.json()
        ids = [str(m.get("id") or "") for m in (data.get("data") or []) if isinstance(m, dict)]
        ids = [i for i in ids if i]
        if preferred and preferred in ids:
            return preferred
        # Prefer non-embedding ids
        for i in ids:
            low = i.lower()
            if "embed" in low:
                continue
            if preferred and preferred.split("/")[-1] in low:
                return i
        for i in ids:
            if "embed" not in i.lower():
                return i
        if ids:
            return ids[0]
    except requests.RequestException as e:
        print(f"WARN: could not list models ({e}); using preferred={preferred!r}", file=sys.stderr)
    return preferred


def _caption_image(
    png_path: Path,
    *,
    base: str,
    model: str,
    timeout: float,
) -> Tuple[str, str]:
    b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
    # Qwen thinking models spend completion budget on reasoning_content; keep headroom.
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
    }
    r = requests.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": "Bearer lm-studio"},
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    choices = body.get("choices") or []
    content = ""
    if choices:
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "")
        if not content.strip():
            # Some builds put the answer only in reasoning; last resort.
            content = str(msg.get("reasoning_content") or "")
    slug, caption = _parse_model_json(content)
    # Reject leaked chain-of-thought when JSON parse missed the answer.
    low = caption.lower()
    if (
        "the user wants a json" in low
        or "i need to look carefully" in low
        or caption.count("\n") > 3
    ):
        print(f"  WARN: rejecting reasoning-like caption ({caption[:80]!r}…)", file=sys.stderr)
        slug, caption = "", ""
    if not caption:
        print(f"  WARN: unparsed model content: {content[:240]!r}", file=sys.stderr)
    return slug, caption


def _unique_slug(base_slug: str, used: Dict[str, str]) -> str:
    slug = base_slug
    n = 2
    while slug in used:
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def _to_jpeg(src: Path, dest: Path, *, max_width: int, quality: int) -> Tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        if w > max_width:
            nh = max(1, int(round(h * (max_width / float(w)))))
            im = im.resize((max_width, nh), Image.Resampling.LANCZOS)
            w, h = im.size
        im.save(dest, format="JPEG", quality=quality, optimize=True)
    return w, h


def _asset_mtime(path: Path) -> float:
    """Capture order for ShareX dumps — LastWriteTime, not copy CreationTime."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _sorted_asset_pngs(assets: Path) -> List[Path]:
    return sorted(assets.glob("*.png"), key=lambda p: (_asset_mtime(p), p.name.lower()))


def _fmt_capture_time(ts: float) -> str:
    if not ts:
        return ""
    return time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(ts)).lstrip("0").replace(" 0", " ")


def _write_gallery_docs(gallery: Path, entries: List[Dict[str, Any]]) -> None:
    docs = gallery / "docs"
    imgs = docs / "images"
    docs.mkdir(parents=True, exist_ok=True)
    imgs.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Spock Screenshots",
        "",
        "ShareX captures from `assets/`, pre-scanned with LM Studio vision, "
        "resized to JPEG for GitHub-friendly docs.",
        "",
        "Ordered by original capture time (`LastWriteTime` on the source PNG).",
        "",
        f"**{len(entries)}** image(s).",
        "",
    ]
    cap_lines = [
        "# Captions",
        "",
        "Ordered by original capture time (same sequence the screenshots were taken).",
        "",
        "| # | Captured | File | Caption | Source PNG |",
        "|---|----------|------|---------|------------|",
    ]
    for i, e in enumerate(entries, 1):
        rel = e["file"].replace("\\", "/")
        caption = e.get("caption") or ""
        src = e.get("source") or ""
        captured = e.get("captured_at") or ""
        lines.append(f"## {i}. {Path(rel).stem}")
        lines.append("")
        if captured:
            lines.append(f"*Captured: {captured}*")
            lines.append("")
        lines.append(f"![{caption}]({rel})")
        lines.append("")
        lines.append(caption)
        lines.append("")
        cap_lines.append(
            f"| {i} | {captured} | `{Path(rel).name}` | {caption} | `{src}` |"
        )

    (docs / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (docs / "captions.md").write_text("\n".join(cap_lines) + "\n", encoding="utf-8")


def _ensure_gallery_mkdocs(gallery: Path) -> None:
    yml = gallery / "mkdocs.yml"
    if yml.exists():
        return
    yml.write_text(
        """site_name: Spock Screenshots
site_description: Pre-scanned ShareX UI screenshots for Spock-Onboarding
site_url: ""
repo_url: ""

docs_dir: docs
site_dir: site

theme:
  name: material
  palette:
    - scheme: slate
      primary: deep purple
      accent: amber
      toggle:
        icon: material/brightness-7
        name: Switch to light mode
    - scheme: default
      primary: deep purple
      accent: amber
      toggle:
        icon: material/brightness-4
        name: Switch to dark mode

nav:
  - Gallery: index.md
  - Captions: captions.md

markdown_extensions:
  - attr_list
  - md_in_html
  - tables
  - toc:
      permalink: true
""",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "items": {}}
    if not isinstance(data, dict):
        return {"version": 1, "items": {}}
    items = data.get("items")
    if not isinstance(items, dict):
        data["items"] = {}
    return data


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Pre-scan assets PNGs → gallery JPGs via LM Studio")
    p.add_argument("--assets-root", type=Path, default=DEFAULT_ASSETS)
    p.add_argument("--temp-root", type=Path, default=DEFAULT_TEMP)
    p.add_argument("--gallery-root", type=Path, default=DEFAULT_GALLERY)
    p.add_argument("--lm-studio-url", default=DEFAULT_LM)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--max-width", type=int, default=1280)
    p.add_argument("--jpeg-quality", type=int, default=82)
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Process at most N images (0 = all)")
    args = p.parse_args(argv)

    assets: Path = args.assets_root.resolve()
    temp: Path = args.temp_root.resolve()
    gallery: Path = args.gallery_root.resolve()
    base = args.lm_studio_url.rstrip("/")

    if not assets.is_dir():
        print(f"ERROR: assets root missing: {assets}", file=sys.stderr)
        return 2

    pngs = _sorted_asset_pngs(assets)
    if args.limit and args.limit > 0:
        pngs = pngs[: args.limit]
    if not pngs:
        print(f"No PNG files in {assets}")
        return 0

    inbox = temp / "inbox"
    work = temp / "work"
    out = temp / "out"
    for d in (inbox, work, out):
        d.mkdir(parents=True, exist_ok=True)

    model = _pick_model(base, args.model, timeout=min(10.0, args.timeout))
    print(f"LM Studio model: {model}")
    print(f"Assets: {assets} ({len(pngs)} png)")
    print(f"Temp:   {temp}")
    print(f"Gallery:{gallery}")

    manifest_path = gallery / "manifest.json"
    gallery.mkdir(parents=True, exist_ok=True)
    (gallery / "docs" / "images").mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(manifest_path)
    items: Dict[str, Any] = dict(manifest.get("items") or {})

    used_slugs: Dict[str, str] = {}
    for src_name, meta in items.items():
        if isinstance(meta, dict) and meta.get("slug"):
            used_slugs[str(meta["slug"])] = src_name

    entries: List[Dict[str, Any]] = []
    ok = 0
    skipped = 0
    failed = 0

    for i, src in enumerate(pngs, 1):
        digest = _sha256(src)
        prev = items.get(src.name)
        if (
            not args.force
            and isinstance(prev, dict)
            and prev.get("sha256") == digest
            and prev.get("file")
            and (gallery / "docs" / str(prev["file"])).is_file()
        ):
            print(f"[{i}/{len(pngs)}] skip {src.name} (unchanged)")
            entries.append(
                {
                    "source": src.name,
                    "file": prev["file"],
                    "caption": prev.get("caption") or "",
                    "slug": prev.get("slug") or Path(str(prev["file"])).stem,
                }
            )
            skipped += 1
            continue

        dest_inbox = inbox / src.name
        shutil.copy2(src, dest_inbox)
        print(f"[{i}/{len(pngs)}] caption {src.name} …", flush=True)
        try:
            raw_slug, caption = _caption_image(
                dest_inbox, base=base, model=model, timeout=args.timeout
            )
        except Exception as e:
            print(f"  FAIL caption: {e}", file=sys.stderr)
            failed += 1
            continue

        if not caption:
            caption = f"Spock UI screenshot ({src.stem})."
        slug = _unique_slug(_slugify(raw_slug, src.stem), used_slugs)
        used_slugs[slug] = src.name

        work_png = work / f"{slug}.png"
        shutil.copy2(dest_inbox, work_png)
        jpg_name = f"{slug}.jpg"
        out_jpg = out / jpg_name
        try:
            w, h = _to_jpeg(
                work_png, out_jpg, max_width=args.max_width, quality=args.jpeg_quality
            )
        except Exception as e:
            print(f"  FAIL jpeg: {e}", file=sys.stderr)
            failed += 1
            continue

        final_rel = f"images/{jpg_name}"
        # MkDocs docs_dir is gallery/docs — JPEGs must live under docs/images/.
        final_path = gallery / "docs" / final_rel
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_jpg, final_path)
        mtime = _asset_mtime(src)
        meta = {
            "source": src.name,
            "slug": slug,
            "file": final_rel.replace("\\", "/"),
            "caption": caption,
            "sha256": digest,
            "width": w,
            "height": h,
            "bytes": final_path.stat().st_size,
            "model": model,
            "mtime": mtime,
            "captured_at": _fmt_capture_time(mtime),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        items[src.name] = meta
        entries.append(meta)
        ok += 1
        print(f"  → {jpg_name} ({w}x{h}, {meta['bytes']} bytes)")
        print(f"     {caption}")

    # Docs order = capture time on remaining assets (LastWriteTime), not filename.
    by_source = {e["source"]: e for e in entries if e.get("source")}
    for src in _sorted_asset_pngs(assets):
        prev = items.get(src.name)
        if not isinstance(prev, dict) or not prev.get("file"):
            continue
        mtime = float(prev.get("mtime") or _asset_mtime(src))
        captured = prev.get("captured_at") or _fmt_capture_time(mtime)
        # Keep manifest timestamps fresh for skipped items.
        prev["mtime"] = mtime
        prev["captured_at"] = captured
        items[src.name] = prev
        by_source[src.name] = {
            "source": src.name,
            "file": prev["file"],
            "caption": prev.get("caption") or "",
            "slug": prev.get("slug") or Path(str(prev["file"])).stem,
            "mtime": mtime,
            "captured_at": captured,
        }
    ordered = [by_source[s.name] for s in _sorted_asset_pngs(assets) if s.name in by_source]

    manifest["version"] = 1
    manifest["items"] = items
    manifest["model"] = model
    manifest["generated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    _ensure_gallery_mkdocs(gallery)
    _write_gallery_docs(gallery, ordered)

    print(
        f"Done. captioned/converted={ok} skipped={skipped} failed={failed} "
        f"gallery={gallery}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
