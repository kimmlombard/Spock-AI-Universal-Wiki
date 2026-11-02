"""File preview: pure logic (no PyQt) — shared by the GUI and tools."""

from __future__ import annotations

import os

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
RICH_EXTENSIONS = {".html", ".htm", ".pdf"}


def is_image_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def is_rich_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in RICH_EXTENSIONS


def _preview_read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="latin-1") as f:
                return f.read()
        except Exception as e:
            return f"[Error reading file] {e}"
    except Exception as e:
        return f"[Error reading file] {e}"


def _preview_html(path: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _preview_read_text(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n")
        return text[:5000]
    except Exception as e:
        return f"[Error reading HTML] {e}"


def _preview_pdf(path: str) -> str:
    try:
        import pymupdf
    except ImportError:
        return "[PyMuPDF not installed — cannot preview PDF]"
    try:
        with pymupdf.open(path) as doc:
            texts = [page.get_text() or "" for page in doc.pages(0, min(5, doc.page_count))]
        return "\n\n".join(texts)
    except Exception as e:
        return f"[Error reading PDF] {e}"


def _preview_image_info(path: str) -> str:
    try:
        from PIL import Image

        img = Image.open(path)
        return f"PNG Image: {img.size[0]}x{img.size[1]}"
    except ImportError:
        return f"[Pillow not installed — cannot preview image]"
    except Exception as e:
        return f"[Error reading image] {e}"


def preview_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".md":
        return _preview_read_text(path)
    if ext in (".html", ".htm"):
        return _preview_html(path)
    if ext in (".txt", ".py", ".ts", ".json", ".css", ".js"):
        return _preview_read_text(path)
    if ext == ".pdf":
        return _preview_pdf(path)
    if ext in IMAGE_EXTENSIONS:
        return _preview_image_info(path)
    return _preview_read_text(path)
