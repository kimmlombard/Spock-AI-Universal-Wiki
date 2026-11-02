"""Enhance docs/*.md sources in place using the LLM hook pipeline.

Reuses llm_enhance.on_page_markdown (chunked, /no_think reasoning disabled,
auto-generated `reference/` pages are left untouched) but writes the improved
markdown back to disk instead of the built site.

Usage: python enhance_docs.py [docs_dir]
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import llm_enhance


def enhance_file(path: Path, docs_root: Path) -> bool:
    """Enhance one markdown file; return True if the content changed."""
    rel = path.relative_to(docs_root)
    page = SimpleNamespace(file=SimpleNamespace(src_uri=rel.as_posix()))
    original = path.read_text(encoding="utf-8")
    enhanced = llm_enhance.on_page_markdown(original, page)
    if enhanced == original:
        return False
    # newline="" avoids re-writing \n as \r\n on Windows
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(enhanced)
    return True


def main() -> int:
    docs_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs")
    if not docs_root.is_dir():
        print(f"[enhance] docs dir not found: {docs_root}")
        return 1

    files = sorted(docs_root.rglob("*.md"))
    changed = 0
    for path in files:
        try:
            if enhance_file(path, docs_root):
                changed += 1
                print(f"[enhance] updated {path.relative_to(docs_root)}")
        except Exception as e:  # noqa: BLE001 - keep going, one bad file shouldn't stop the batch
            print(f"[enhance] FAILED {path}: {e}")

    print(f"[enhance] {changed}/{len(files)} files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())