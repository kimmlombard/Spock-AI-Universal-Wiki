#!/usr/bin/env python3
"""
Starfleet Universal Extractor
Duty Officer: Scotty (engineering) + Bones (security screening)
General Order 12: Contain Unknown Specimens

Ingests any file type, extracts text/data safely, queues for wiki.
No external services. All processing local.
"""
import os
import re
import json
import hashlib
import mimetypes
import sqlite3
import shutil
import struct
import sys
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

# Core libs - all pip installable, no services.
# `magic` is not in any tier; install python-magic yourself for libmagic MIME
# detection, otherwise detect_mime falls back to extension matching.
try:
    import magic  # MIME detection via libmagic
except ImportError:  # pragma: no cover - missing native libmagic
    magic = None
import pymupdf as fitz  # PyMuPDF for PDFs (modern import; the deprecated `fitz` shim prints a startup warning)
from PIL import Image

# OCR is opt-in and needs both halves: `pip install -r requirements-ocr.txt` and
# the Tesseract binary (`winget install UB-Mannheim.TesseractOCR`). Missing
# either one skips image text instead of failing the scan.
try:
    import pytesseract  # OCR
except ImportError:  # pragma: no cover - OCR tier not installed
    pytesseract = None

TESSERACT_CMD = os.environ.get(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)
if pytesseract is not None:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

_OCR_STATE: Dict[str, Any] = {"checked": False, "ready": False, "warned": False}


def ocr_status() -> Tuple[bool, str]:
    """(ready, reason) for image OCR — resolved once per process."""
    if not _OCR_STATE["checked"]:
        _OCR_STATE["checked"] = True
        if pytesseract is None:
            _OCR_STATE["reason"] = (
                "pytesseract not installed (pip install -r requirements-ocr.txt)"
            )
        elif not (shutil.which(TESSERACT_CMD) or os.path.isfile(TESSERACT_CMD)):
            _OCR_STATE["reason"] = (
                f"Tesseract binary not found at {TESSERACT_CMD} "
                "(winget install UB-Mannheim.TesseractOCR, or set TESSERACT_CMD)"
            )
        else:
            _OCR_STATE["ready"] = True
            _OCR_STATE["reason"] = TESSERACT_CMD
    return bool(_OCR_STATE["ready"]), str(_OCR_STATE.get("reason") or "")


def ocr_image(source: Any) -> str:
    """Read text from an image path / bytes buffer. Empty string when OCR is off."""
    ready, reason = ocr_status()
    if not ready:
        if not _OCR_STATE["warned"]:
            _OCR_STATE["warned"] = True
            print(f"[OCR] Image text skipped - {reason}", flush=True)
        return ""
    try:
        return pytesseract.image_to_string(Image.open(source))
    except Exception as e:
        return f"[OCR failed: {e}]"


from bs4 import BeautifulSoup
import lxml # HTML parser
from docx import Document # python-docx
import openpyxl
import pandas as pd
import zipfile
import tarfile
import base64
import io

# --- Starfleet Configuration ---
WIKI_ROOT = Path(__file__).parent.resolve()
DB_PATH = WIKI_ROOT / os.environ.get("DB_NAME", "ship_computer.db")
BLOB_DIR = WIKI_ROOT / "data" / "blobs"
QUARANTINE_DIR = WIKI_ROOT / "data" / "quarantine"

# Thread lock for SQLite writes
_db_lock = threading.RLock()


def _db_connect(timeout: float = 30.0):
    """WAL + busy_timeout via WarpCore; same PRAGMAs if WarpCore is unavailable."""
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore.db import connect as _wc_connect

        return _wc_connect(str(DB_PATH), timeout=timeout)
    except Exception:
        conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=%d" % int(timeout * 1000))
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

# Load scan_roots from Spock_Console (mirrored in scan_config.json)
def _load_scan_roots() -> list:
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        settings_store.ensure_paths_healed(str(DB_PATH))
        roots = settings_store.get(str(DB_PATH), "scan.scan_roots")
        if roots:
            return [str(r) for r in roots]
    except Exception:
        pass
    cfg_path = WIKI_ROOT / "scan_config.json"
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
        return cfg.get("scan_roots", [])
    return [str(WIKI_ROOT)]

def _norm_federation_path(path: str | Path) -> str:
    """Case-fold on Windows so scan roots match queued paths (normcase)."""
    raw = str(path or "")
    if not raw:
        return ""
    try:
        resolved = str(Path(raw).expanduser().resolve())
    except OSError:
        resolved = os.path.abspath(os.path.expanduser(raw))
    if os.name == "nt":
        return os.path.normcase(os.path.normpath(resolved)).rstrip("\\/")
    return os.path.normpath(resolved).rstrip("/\\")


_scan_roots = _load_scan_roots()
_raw_candidates = [
    _norm_federation_path(WIKI_ROOT / "research_raw"),
    _norm_federation_path(WIKI_ROOT),
] + [_norm_federation_path(r) for r in _scan_roots]
RAW_ROOTS: List[str] = []
_seen_roots: set[str] = set()
for _r in _raw_candidates:
    if _r and _r not in _seen_roots:
        _seen_roots.add(_r)
        RAW_ROOTS.append(_r)

# Embeddings config
EMBEDDINGS_URL = os.environ.get("EMBEDDINGS_URL", "http://localhost:8080/embeddings")
EMBEDDINGS_DIM = int(os.environ.get("EMBEDDINGS_DIM", "4096"))
EMBEDDINGS_TRUNCATE = int(os.environ.get("EMBEDDINGS_TRUNCATE", "1500"))
EMBEDDINGS_BATCH_CHUNK = int(os.environ.get("EMBEDDINGS_BATCH_CHUNK", "32"))
EMBEDDINGS_BATCH_WORKERS = int(os.environ.get("EMBEDDINGS_BATCH_WORKERS", "8"))
_NULL_EMBED_PATHS: List[str] = []
# How many files to extract before embed+DB flush (keeps Embedding Status live).
INGEST_FLUSH_SIZE = int(os.environ.get("INGEST_FLUSH_SIZE", str(EMBEDDINGS_BATCH_CHUNK)))
EMBEDDING_MODEL_PATH = os.environ.get("SPOCK_EMBED_MODEL_PATH", "").strip()
EMBEDDING_MODEL_ID = os.environ.get("SPOCK_EMBED_MODEL_ID", "").strip()
INGEST_PROGRESS_PATH = Path(
    os.environ.get(
        "SPOCK_INGEST_PROGRESS",
        str(WIKI_ROOT / "logs" / "wiki_ingest_progress.json"),
    )
)

BLOB_DIR.mkdir(parents=True, exist_ok=True)
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

# General Order 12: Risk levels
RISK_LEVELS = {
    'application/pdf': 'MEDIUM', # can contain JS
    'application/msword': 'MEDIUM',
    'application/vnd.openxmlformats-officedocument': 'MEDIUM',
    'application/zip': 'MEDIUM', # zip bombs
    'application/x-executable': 'HIGH',
    'application/x-sharedlib': 'HIGH',
    'text/plain': 'LOW',
    'image/': 'LOW', # prefix match
    'video/': 'LOW', # we only transcribe, not execute
    'audio/': 'LOW',
}

# Match credential-like *names*, not substrings (e.g. WarpCore/secrets.py is app code).
FORBIDDEN_PATTERNS = [
    r"\bsecret\b",
    r"\bpassword\b",
    r"api[_-]?key",
    r"\.pem$",
    r"\.key$",
    r"\.db-wal$",
    r"\.db-shm$",
    r"\.db-journal$",
]
MAX_INLINE_BLOB_MB = 1 # Above this, store as blob_path only
MAX_FILE_MB = 50 # Prime Directive: refuse anything bigger

# Source/config extensions to read as plain text. libmagic sniffs these from
# content, but the mimetypes fallback has no entry for .sql/.rs/.go and maps .ts
# to video/vnd.dlna.mpeg-tts, so source files read as application/octet-stream.
TEXT_EXTENSIONS = {
    ".adoc", ".bash", ".bat", ".c", ".cc", ".cfg", ".clj", ".cmake", ".cmd",
    ".conf", ".cpp", ".cs", ".css", ".dart", ".ex", ".exs", ".erl", ".fs",
    ".go", ".gradle", ".graphql", ".groovy", ".h", ".hpp", ".hs", ".ini",
    ".java", ".jl", ".js", ".json", ".jsonc", ".jsx", ".kt", ".kts", ".less",
    ".log", ".lua", ".m", ".md", ".mjs", ".mk", ".mm", ".nim", ".php", ".pl",
    ".properties", ".proto", ".ps1", ".psm1", ".py", ".pyi", ".r", ".rb",
    ".rs", ".rst", ".scala", ".scss", ".sh", ".sql", ".svelte", ".swift",
    ".tf", ".toml", ".ts", ".tsx", ".txt", ".vue", ".xml", ".yaml", ".yml",
    ".zig", ".zsh",
}

def stardate() -> str:
    return datetime.now().strftime("%Y.%m.%d.%H.%M.%S")

def log(officer: str, action: str, target: str, message: str, alert: str = "GREEN", skill: str = "universal_onboard"):
    with _db_lock:
        with _db_connect() as conn:
            conn.execute("""
                INSERT INTO captains_log (stardate, alert_level, officer, skill_name, action, target_path, message)
                VALUES (?,?,?,?,?,?,?)
            """, (stardate(), alert, officer, skill, action, str(target), message))

def _parse_embedding(raw) -> list:
    """Parse llama.cpp embedding response into a flat list of floats.

    Nested token rows are averaged. A null entry is a NaN from llama-server
    and raises ValueError instead of failing the addition.
    """
    from spock_rag_adapter.embedding_utils import flatten_embedding

    return flatten_embedding(raw)


def _embed_port() -> int:
    from urllib.parse import urlparse

    parsed = urlparse(EMBEDDINGS_URL)
    return int(parsed.port or 80)


def _post_embeddings(body, timeout: int):
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        EMBEDDINGS_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _restart_embed_server() -> bool:
    """Replace the embedding llama-server so a NaN response cannot poison the next file."""
    from spock_shell.llama_gui_command import restart_llama_server

    note = restart_llama_server(_embed_port())
    log("scotty", "EMBED_SERVER_RESTART", "system", note, "YELLOW")
    return note.startswith("Restarted")


def _pack_vector(vec) -> Optional[bytes]:
    if not vec:
        return None
    return struct.pack(f"{len(vec)}f", *vec)


def compute_embedding(text: str):
    """Generate embedding via local llama.cpp server, store as float32 BLOB.

    Returns (blob, dim) or (None, 0) on failure.
    """
    truncated = text[:EMBEDDINGS_TRUNCATE]
    try:
        result = _post_embeddings({"input": truncated}, 30)
        # llama.cpp returns [{index, embedding}]
        if isinstance(result, list):
            emb = result[0]["embedding"]
        else:
            emb = result["data"][0]["embedding"]
        avg = _parse_embedding(emb)
        if EMBEDDINGS_DIM and len(avg) != EMBEDDINGS_DIM:
            log(
                "scotty",
                "EMBED_DIM_MISMATCH",
                "system",
                f"got {len(avg)} dims, expected {EMBEDDINGS_DIM}",
                "YELLOW",
            )
            # Do not silently truncate/pad — store actual vector; caller/DB must match
        return struct.pack(f"{len(avg)}f", *avg), len(avg)
    except ValueError:
        raise
    except Exception as e:
        log("scotty", "EMBED_FAILED", "system", str(e), "YELLOW")
        return None, 0

def _embed_chunk(chunk: List[str]) -> List[Optional[bytes]]:
    """Embed one POST. A null vector is retried once after the server is restarted.

    On this GPU a single NaN response makes every later request null until the
    llama-server process is replaced. Documents that still come back null are
    stored with no vector so the rest of the scan can finish.
    """
    from spock_rag_adapter.embedding_utils import embeddings_from_response

    try:
        result = _post_embeddings({"input": chunk}, 120)
        vectors, saw_null = embeddings_from_response(result, len(chunk))
    except Exception as e:
        log("scotty", "EMBED_BATCH_FAILED", "system", str(e), "YELLOW")
        return [None] * len(chunk)

    if saw_null:
        if not _restart_embed_server():
            return [_pack_vector(vec) for vec in vectors]
        for index, vec in enumerate(vectors):
            if vec is not None:
                continue
            try:
                again = _post_embeddings({"input": chunk[index]}, 120)
                retried, retry_null = embeddings_from_response(again, 1)
                vectors[index] = retried[0] if retried else None
            except Exception as e:
                log("scotty", "EMBED_FAILED", "system", str(e), "YELLOW")
                vectors[index] = None
                retry_null = False
            if vectors[index] is None and retry_null:
                _restart_embed_server()
    return [_pack_vector(vec) for vec in vectors]


def compute_embeddings_batch(texts: List[str], max_workers: int = None) -> List[bytes]:
    """Batch embedding via llama.cpp server. Uses threading for parallel requests."""
    if max_workers is None:
        max_workers = EMBEDDINGS_BATCH_WORKERS
    CHUNK = EMBEDDINGS_BATCH_CHUNK
    chunks = []
    for i in range(0, len(texts), CHUNK):
        chunk = [t[:EMBEDDINGS_TRUNCATE] for t in texts[i:i+CHUNK]]
        chunks.append(chunk)

    if not chunks:
        return []

    if len(chunks) == 1:
        return _embed_chunk(chunks[0])

    results = [None] * len(chunks)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(chunks))) as pool:
        futures = {pool.submit(_embed_chunk, chunk): idx for idx, chunk in enumerate(chunks)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except ValueError:
                raise
            except Exception:
                results[idx] = [None] * len(chunks[idx])

    out = []
    for r in results:
        out.extend(r)
    return out

def detect_mime(path: Path) -> str:
    """Identify MIME type via libmagic, with extension fallback for Windows."""
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return "text/plain"
    if magic is not None:
        try:
            return magic.from_file(str(path), mime=True)
        except Exception:
            pass
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"

def get_risk_level(mime: str) -> str:
    for k, v in RISK_LEVELS.items():
        if mime.startswith(k):
            return v
    return 'MEDIUM' # unknown = cautious

def prime_directive_check(path: Path) -> bool:
    # Check allowed roots (Windows: case-insensitive; wiki_agent queues normcase paths)
    key = _norm_federation_path(path)
    def _under(root: str) -> bool:
        if not root:
            return False
        return key == root or key.startswith(root + os.sep)

    if not any(_under(r) for r in RAW_ROOTS):
        log('bones', 'BLOCKED', path, 'Outside Federation space', 'RED')
        return False
    # Check forbidden names
    if any(re.search(p, path.name, re.I) for p in FORBIDDEN_PATTERNS):
        log('bones', 'BLOCKED', path, 'Forbidden pattern in filename', 'RED')
        return False
    # Check size
    if path.stat().st_size > MAX_FILE_MB * 1024 * 1024:
        log('bones', 'BLOCKED', path, f'Exceeds {MAX_FILE_MB}MB limit', 'YELLOW')
        return False
    return True

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def extract_pdf(path: Path) -> Dict[str, Any]:
    doc = fitz.open(path)
    text_parts = []
    attachments = []
    for i, page in enumerate(doc):
        text_parts.append(page.get_text())
        # Extract images from page
        for img_idx, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.n < 5: # not CMYK
                img_bytes = pix.tobytes("png")
                img_hash = hashlib.sha256(img_bytes).hexdigest()
                blob_path = BLOB_DIR / f"{img_hash}.png"
                if not blob_path.exists():
                    blob_path.write_bytes(img_bytes)
                ocr_text = ocr_image(blob_path)
                attachments.append({
                    'filename': f"page{i+1}_img{img_idx+1}.png",
                    'mime_type': 'image/png',
                    'blob_path': str(blob_path),
                    'extracted_text': ocr_text,
                    'sha256': img_hash
                })
    return {
        'title': path.stem,
        'text': "\n\n".join(text_parts),
        'attachments': attachments
    }

def extract_docx(path: Path) -> Dict[str, Any]:
    doc = Document(path)
    text = "\n".join([p.text for p in doc.paragraphs])
    # Extract tables as markdown
    for table in doc.tables:
        df = pd.DataFrame([[cell.text for cell in row.cells] for row in table.rows])
        text += "\n\n" + df.to_markdown(index=False) + "\n"
    return {'title': path.stem, 'text': text, 'attachments': []}

def extract_spreadsheet(path: Path) -> Dict[str, Any]:
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path, sheet_name=None) # all sheets
        if isinstance(df, dict):
            df = pd.concat(df.values(), keys=df.keys())
    text = f"# Spreadsheet: {path.name}\n\n{df.to_markdown(index=False)}"
    return {'title': path.stem, 'text': text, 'attachments': []}

def extract_image(path: Path) -> Dict[str, Any]:
    return {'title': path.stem, 'text': ocr_image(path), 'attachments': []}

def extract_html(path: Path) -> Dict[str, Any]:
    """Extract text and OCR images from HTML using BeautifulSoup."""
    html = path.read_text(encoding='utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'lxml')

    # Remove script and style elements
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()

    # Extract text content
    text_parts = []
    for elem in soup.find_all(['h1','h2','h3','h4','h5','h6','p','li','td','th','pre','code','blockquote']):
        t = elem.get_text(separator=' ', strip=True)
        if t:
            tag_name = elem.name
            if tag_name.startswith('h'):
                level = int(tag_name[1])
                text_parts.append(f"{'#' * level} {t}")
            elif tag_name == 'li':
                text_parts.append(f"- {t}")
            elif tag_name == 'pre' or tag_name == 'code':
                text_parts.append(f"```\n{t}\n```")
            else:
                text_parts.append(t)

    text = "\n\n".join(text_parts)
    if not text.strip():
        text = soup.get_text(separator='\n', strip=True)

    # Extract and OCR images
    attachments = []
    img_count = 0
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if not src:
            continue

        img_bytes = None
        filename = None

        # Handle base64 data URIs
        if src.startswith('data:image/'):
            try:
                header, data = src.split(',', 1)
                img_bytes = base64.b64decode(data)
                ext = header.split(';')[0].split('/')[-1]
                img_hash = hashlib.sha256(img_bytes).hexdigest()
                filename = f"img_{img_count}.{ext}"
                blob_path = BLOB_DIR / f"{img_hash}.{ext}"
                if not blob_path.exists():
                    blob_path.write_bytes(img_bytes)
            except Exception:
                continue

        # Handle relative/absolute file paths
        elif not src.startswith(('http://', 'https://', 'mailto:')):
            try:
                img_path = (path.parent / src).resolve()
                if img_path.exists() and img_path.is_file():
                    img_bytes = img_path.read_bytes()
                    img_hash = hashlib.sha256(img_bytes).hexdigest()
                    filename = img_path.name
                    blob_path = BLOB_DIR / f"{img_hash}{img_path.suffix}"
                    if not blob_path.exists():
                        blob_path.write_bytes(img_bytes)
            except Exception:
                continue

        if img_bytes and filename:
            ocr_text = ocr_image(io.BytesIO(img_bytes))
            attachments.append({
                'filename': filename,
                'mime_type': f"image/{filename.split('.')[-1]}",
                'blob_path': str(blob_path),
                'extracted_text': ocr_text,
                'sha256': img_hash
            })
            if ocr_text.strip():
                text += f"\n\n[Image: {filename}]\n{ocr_text}"
            img_count += 1

    # Extract tables as markdown
    for table in soup.find_all('table'):
        rows = []
        for tr in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if cells:
                rows.append(cells)
        if rows:
            df = pd.DataFrame(rows)
            text += "\n\n" + df.to_markdown(index=False) + "\n"

    title = soup.title.get_text(strip=True) if soup.title else path.stem
    return {'title': title, 'text': text, 'attachments': attachments}

def extract_archive(path: Path) -> Dict[str, Any]:
    members = []
    extract_dir = QUARANTINE_DIR / f"unpack_{sha256_file(path)[:8]}"
    extract_dir.mkdir(exist_ok=True)
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as z:
            z.extractall(extract_dir)
            members = z.namelist()
    elif path.suffix in ['.tar', '.gz', '.tgz']:
        with tarfile.open(path) as t:
            t.extractall(extract_dir)
            members = t.getnames()
    # Queue each member for ingestion
    for m in members:
        enqueue_skill('universal_onboard', {'path': str(extract_dir / m)})
    text = f"# Archive: {path.name}\n\nContains {len(members)} files:\n" + "\n".join(f"- {m}" for m in members[:50])
    return {'title': path.stem, 'text': text, 'attachments': []}

EXTRACTORS = {
    'application/pdf': extract_pdf,
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': extract_docx,
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': extract_spreadsheet,
    'text/csv': extract_spreadsheet,
    'text/html': extract_html,
    'application/zip': extract_archive,
    'application/x-tar': extract_archive,
    'application/gzip': extract_archive,
}

def infer_role(path: Path, text: str) -> str:
    p = str(path).lower()
    if '/architecture/' in p or 'design' in p: return 'spock'
    if '/security/' in p or re.search(r'\b(cve|vuln|auth|oauth)\b', text, re.I): return 'bones'
    if '/howto/' in p or '/runbook/' in p or '```' in text: return 'scotty'
    return 'kirk'

def secret_scan(text: str) -> List[str]:
    patterns = [r'AKIA[0-9A-Z]{16}', r'sk-[a-zA-Z0-9]{48}', r'password\s*=\s*["\'][^"\']+["\']']
    hits = []
    for p in patterns:
        hits.extend(re.findall(p, text, re.I))
    return hits

def enqueue_skill(skill_name: str, payload: Dict):
    with _db_lock:
        with _db_connect() as conn:
            conn.execute("""
                INSERT INTO agent_queue (skill_name, officer, payload_json, status)
                VALUES (?,?,?, 'pending')
            """, (skill_name, 'scotty', json.dumps(payload)))

def flag_for_review(path: Path, reason: str):
    """Record a file Bones excluded from the wiki, and leave it where it is.

    Scanning is read-only: Spock indexes repositories it does not own, so a
    screening verdict withholds the file from the KB rather than relocating it.
    """
    with _db_lock:
        with _db_connect() as conn:
            conn.execute("INSERT INTO quarantine (path, reason, detected_by) VALUES (?,?,?)",
                         (str(path), reason, 'bones'))
    log('bones', 'EXCLUDED', path, reason, 'YELLOW')

def _stamp_corpus(embedding_dim: Optional[int]) -> None:
    model_path = EMBEDDING_MODEL_PATH or ""
    if not model_path:
        return
    try:
        from spock_shell.embedding_corpus import ensure_schema, write_corpus

        ensure_schema(str(DB_PATH))
        write_corpus(
            model_path=model_path,
            embeddings_url=EMBEDDINGS_URL,
            embeddings_dim=embedding_dim or EMBEDDINGS_DIM,
            model_id=EMBEDDING_MODEL_ID,
            db_path=str(DB_PATH),
        )
    except Exception:
        pass


def _ensure_embed_columns(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN embedding_model_path TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN embedding_dim INTEGER")
    except sqlite3.OperationalError:
        pass


def _upsert_document_row(
    conn: sqlite3.Connection,
    data: Dict,
    embedding_blob,
    embedding_dim,
    model_path: str,
) -> int:
    existing = conn.execute(
        "SELECT id FROM documents WHERE path = ?", (data["path"],)
    ).fetchone()
    if existing:
        doc_id = existing[0]
        conn.execute(
            """
            UPDATE documents SET
                filename=?, title=?, content_md=?, content_plain=?, role=?,
                duty_officer='scotty', source_type='local',
                hash_sha256=?, file_mtime=?, file_size=?, mime_type=?,
                blob_path=?, extracted_json=?, embedding=?,
                embedding_model_path=?, embedding_dim=?,
                updated_at=strftime('%s','now')
            WHERE id=?
            """,
            (
                data["filename"],
                data["title"],
                data.get("content_md"),
                data["content_plain"],
                data["role"],
                data["hash_sha256"],
                data["file_mtime"],
                data["file_size"],
                data["mime_type"],
                data.get("blob_path"),
                json.dumps(data.get("extracted_json")),
                embedding_blob,
                model_path or None,
                embedding_dim,
                doc_id,
            ),
        )
        # docs_fts is maintained by documents_au / documents_ai triggers —
        # do not write FTS here (double-write corrupts content= FTS5).
        conn.execute("DELETE FROM document_attachments WHERE doc_id = ?", (doc_id,))
    else:
        cur = conn.execute(
            """
            INSERT INTO documents
            (path, filename, title, content_md, content_plain, role, duty_officer,
             source_type, hash_sha256, file_mtime, file_size, mime_type, blob_path,
             extracted_json, embedding, embedding_model_path, embedding_dim)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data["path"],
                data["filename"],
                data["title"],
                data.get("content_md"),
                data["content_plain"],
                data["role"],
                "scotty",
                "local",
                data["hash_sha256"],
                data["file_mtime"],
                data["file_size"],
                data["mime_type"],
                data.get("blob_path"),
                json.dumps(data.get("extracted_json")),
                embedding_blob,
                model_path or None,
                embedding_dim,
            ),
        )
        doc_id = cur.lastrowid
    for att in data.get("attachments", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO document_attachments
            (doc_id, filename, mime_type, blob_path, extracted_text, sha256)
            VALUES (?,?,?,?,?,?)
            """,
            (
                doc_id,
                att["filename"],
                att["mime_type"],
                att["blob_path"],
                att.get("extracted_text"),
                att["sha256"],
            ),
        )
    return doc_id


def insert_documents_batch(docs: List[Dict]) -> List[int]:
    """Embed in POSTs of 32, then write all rows in one SQLite transaction."""
    if not docs:
        return []
    texts = [str(d.get("content_plain") or "") for d in docs]
    blobs = compute_embeddings_batch(texts, max_workers=1)
    while len(blobs) < len(docs):
        blobs.append(None)
    model_path = EMBEDDING_MODEL_PATH or ""
    dims: List[Optional[int]] = []
    for blob in blobs:
        if blob:
            dims.append(len(blob) // 4)
        else:
            dims.append(None)
    stamped = next((d for d in dims if d), None)
    if stamped:
        _stamp_corpus(stamped)

    ids: List[int] = []
    ingested: List[Tuple[Dict, int]] = []
    with _db_lock:
        with _db_connect() as conn:
            _ensure_embed_columns(conn)
            for data, blob, dim in zip(docs, blobs, dims):
                if not blob:
                    _NULL_EMBED_PATHS.append(str(data.get("path") or ""))
                doc_id = _upsert_document_row(conn, data, blob, dim, model_path)
                ids.append(doc_id)
                ingested.append((data, doc_id))
            try:
                from WarpCore.db import upsert_documents_vec

                upsert_documents_vec(conn, ids)
            except Exception:
                pass
    # Log after commit. log() opens its own connection; doing that inside the
    # write transaction hits sqlite "database is locked" and rolls back the batch.
    for data, doc_id in ingested:
        log(
            "scotty",
            "INGESTED",
            data.get("path") or "",
            f"DocID {doc_id}, role {data.get('role')}, "
            f"{len(data.get('content_plain') or '')} chars",
        )
    return ids


def insert_document(data: Dict) -> int:
    ids = insert_documents_batch([data])
    return ids[0] if ids else 0


def prepare_document(path: Path, reprocess: bool = False) -> Tuple[str, Optional[Dict]]:
    """Extract a file without embedding or inserting.

    Returns (status, doc_data) where status is 'ready', 'skip', or 'fail'.
    """
    log("scotty", "SCAN_START", path, "Beginning universal onboard")
    if not reprocess:
        try:
            disk_mtime = int(path.stat().st_mtime)
            disk_size = path.stat().st_size
            with _db_lock:
                with _db_connect() as conn:
                    row = conn.execute(
                        "SELECT file_mtime, file_size, hash_sha256, embedding "
                        "FROM documents WHERE path = ?",
                        (str(path),),
                    ).fetchone()
            if row is not None:
                db_mtime, db_size, db_hash, db_emb = row
                # Clear Embeddings leaves rows with NULL vectors; never skip those
                # even when mtime/hash match — otherwise Wiki Scan "re-queues" them
                # and the extractor silently no-ops (ingest looks successful).
                needs_embed = db_emb is None or (
                    isinstance(db_emb, (bytes, bytearray, memoryview)) and len(db_emb) == 0
                )
                if not needs_embed:
                    if disk_mtime == db_mtime and disk_size == db_size:
                        log("scotty", "SKIP", path, "Unchanged (mtime+size match)")
                        return "skip", None
                    file_hash = sha256_file(path)
                    if file_hash == db_hash:
                        with _db_lock:
                            with _db_connect() as conn:
                                conn.execute(
                                    "UPDATE documents SET file_mtime = ?, "
                                    "updated_at = strftime('%s','now') WHERE path = ?",
                                    (disk_mtime, str(path)),
                                )
                        log("scotty", "SKIP", path, "Unchanged (hash match, mtime updated)")
                        return "skip", None
                else:
                    log(
                        "scotty",
                        "REEMBED",
                        path,
                        "Missing embedding — re-extract despite unchanged file",
                    )
        except Exception:
            pass

    if not prime_directive_check(path):
        flag_for_review(path, "PRIME_DIRECTIVE_VIOLATION")
        return "fail", None

    mime = detect_mime(path)
    risk = get_risk_level(mime)
    if risk == "HIGH":
        flag_for_review(path, f"HIGH_RISK_MIME: {mime}")
        return "fail", None

    try:
        extractor = EXTRACTORS.get(mime)
        if mime.startswith("image/"):
            extractor = extract_image
        elif mime.startswith("text/") and not extractor:
            text = path.read_text(encoding="utf-8", errors="ignore")
            extracted = {"title": path.stem, "text": text, "attachments": []}
        elif extractor:
            extracted = extractor(path)
        else:
            log("scotty", "SKIP", path, f"No extractor for {mime}", "YELLOW")
            return "skip", None
    except Exception as e:
        log("scotty", "EXTRACT_FAILED", path, str(e), "YELLOW")
        return "skip", None

    secrets = secret_scan(extracted["text"])
    if secrets:
        flag_for_review(path, f"SECRETS_DETECTED: {len(secrets)} hits")
        return "fail", None

    file_hash = sha256_file(path)
    blob_path = None
    if path.stat().st_size > MAX_INLINE_BLOB_MB * 1024 * 1024:
        blob_path = BLOB_DIR / f"{file_hash}{path.suffix}"
        if not blob_path.exists():
            shutil.copy2(path, blob_path)
        content_md = f"Binary file. See blob: {blob_path.name}"
    else:
        content_md = (
            extracted["text"] if mime.startswith("text/") else f"Extracted from {mime}"
        )

    return "ready", {
        "path": str(path),
        "filename": path.name,
        "title": extracted["title"],
        "content_md": content_md,
        "content_plain": extracted["text"],
        "role": infer_role(path, extracted["text"]),
        "hash_sha256": file_hash,
        "file_mtime": int(path.stat().st_mtime),
        "file_size": path.stat().st_size,
        "mime_type": mime,
        "blob_path": str(blob_path) if blob_path else None,
        "attachments": extracted["attachments"],
    }


def process_file(path: Path, reprocess: bool = False) -> bool:
    """Single-file ingest (watchdog / CLI). Batch embed of one still hits :8080 once."""
    status, data = prepare_document(path, reprocess=reprocess)
    if status == "skip":
        return True
    if status != "ready" or not data:
        return False
    insert_documents_batch([data])
    return True


def _write_ingest_progress(payload: Dict[str, Any]) -> None:
    """Atomic-ish progress file for wiki_agent_status during long batch ingest."""
    try:
        INGEST_PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = INGEST_PROGRESS_PATH.with_suffix(".json.tmp")
        data = dict(payload)
        data["pid"] = os.getpid()
        data["updated_at"] = int(time.time())
        tmp.write_text(json.dumps(data, indent=0), encoding="utf-8")
        tmp.replace(INGEST_PROGRESS_PATH)
    except OSError:
        pass


def _clear_ingest_progress() -> None:
    try:
        INGEST_PROGRESS_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _report_null_embeddings() -> None:
    paths = [path for path in _NULL_EMBED_PATHS if path]
    if not paths:
        return
    extra = f" and {len(paths) - 1} more" if len(paths) > 1 else ""
    message = (
        f"EMBED_SKIPPED {len(paths)} document(s) stored with no embedding "
        f"because llama-server returned a null vector. Example: {paths[0]}{extra}"
    )
    print(message, file=sys.stderr)
    log("scotty", "EMBED_SKIPPED", paths[0], message, "YELLOW")


def ingest_paths(
    files: List[Path],
    reprocess: bool = False,
    workers: int = 8,
) -> Dict[str, int]:
    """Extract files in windows, embed+insert each window so status stays live."""
    files = [Path(p) for p in files if Path(p).is_file()]
    if not files:
        _clear_ingest_progress()
        return {"ready": 0, "skipped": 0, "failed": 0}

    total = len(files)
    workers = max(1, int(workers))
    flush_size = max(1, int(INGEST_FLUSH_SIZE))
    started_at = int(time.time())
    ready_n = 0
    skipped = 0
    failed = 0
    processed = 0
    last_path = str(files[0])
    _NULL_EMBED_PATHS.clear()

    log(
        "system",
        "BATCH_START",
        files[0].parent if total > 1 else files[0],
        f"Extracting {total} files with {workers} workers, "
        f"flush every {flush_size}",
    )
    _write_ingest_progress(
        {
            "total": total,
            "processed": 0,
            "ready": 0,
            "skipped": 0,
            "failed": 0,
            "last_path": last_path,
            "started_at": started_at,
            "phase": "extract",
        }
    )

    def _prepare_window(window: List[Path]) -> Tuple[List[Dict], int, int, str]:
        win_ready: List[Dict] = []
        win_skip = 0
        win_fail = 0
        win_last = str(window[-1]) if window else ""
        if len(window) == 1:
            status, data = prepare_document(window[0], reprocess=reprocess)
            win_last = str(window[0])
            if status == "ready" and data:
                win_ready.append(data)
            elif status == "skip":
                win_skip += 1
            else:
                win_fail += 1
            return win_ready, win_skip, win_fail, win_last

        with ThreadPoolExecutor(max_workers=min(workers, len(window))) as pool:
            futures = {
                pool.submit(prepare_document, p, reprocess): p for p in window
            }
            for future in as_completed(futures):
                path = futures[future]
                win_last = str(path)
                try:
                    status, data = future.result()
                except Exception as e:
                    log("system", "CRASH", path, str(e), "RED")
                    win_fail += 1
                    continue
                if status == "ready" and data:
                    win_ready.append(data)
                elif status == "skip":
                    win_skip += 1
                else:
                    win_fail += 1
        return win_ready, win_skip, win_fail, win_last

    try:
        for i in range(0, total, flush_size):
            window = files[i : i + flush_size]
            _write_ingest_progress(
                {
                    "total": total,
                    "processed": processed,
                    "ready": ready_n,
                    "skipped": skipped,
                    "failed": failed,
                    "last_path": last_path,
                    "started_at": started_at,
                    "phase": "extract",
                }
            )
            win_ready, win_skip, win_fail, last_path = _prepare_window(window)
            skipped += win_skip
            failed += win_fail
            if win_ready:
                _write_ingest_progress(
                    {
                        "total": total,
                        "processed": processed,
                        "ready": ready_n,
                        "skipped": skipped,
                        "failed": failed,
                        "last_path": last_path,
                        "started_at": started_at,
                        "phase": "embed",
                        "embed_batch": len(win_ready),
                    }
                )
                insert_documents_batch(win_ready)
                ready_n += len(win_ready)
            processed = min(total, i + len(window))
            _write_ingest_progress(
                {
                    "total": total,
                    "processed": processed,
                    "ready": ready_n,
                    "skipped": skipped,
                    "failed": failed,
                    "last_path": last_path,
                    "started_at": started_at,
                    "phase": "flush",
                }
            )
            log(
                "system",
                "BATCH_PROGRESS",
                last_path,
                f"{processed}/{total} "
                f"(ready {ready_n}, skipped {skipped}, failed {failed})",
            )
    finally:
        _write_ingest_progress(
            {
                "total": total,
                "processed": processed,
                "ready": ready_n,
                "skipped": skipped,
                "failed": failed,
                "last_path": last_path,
                "started_at": started_at,
                "phase": "done",
            }
        )

    log(
        "system",
        "BATCH_DONE",
        files[0].parent if files else "",
        f"Ready: {ready_n}, skipped: {skipped}, failed: {failed}",
    )
    _report_null_embeddings()
    _clear_ingest_progress()
    return {"ready": ready_n, "skipped": skipped, "failed": failed}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Starfleet Universal Extractor")
    parser.add_argument("path", nargs="?", type=Path, help="File or directory to process")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Text file of paths (one per line) for folder ingest",
    )
    parser.add_argument("--reprocess", action="store_true", help="Ignore hash, re-ingest")
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Thread workers for extraction (embed stays batched at 32)",
    )
    args = parser.parse_args()

    files: List[Path] = []
    if args.manifest:
        text = Path(args.manifest).read_text(encoding="utf-8", errors="replace")
        files = [Path(line.strip()) for line in text.splitlines() if line.strip()]
    elif args.path:
        paths = [args.path] if args.path.is_file() else list(args.path.rglob("*"))
        files = [p for p in paths if p.is_file()]
    else:
        parser.error("pass a path or --manifest")

    ingest_paths(files, reprocess=args.reprocess, workers=args.workers)


if __name__ == "__main__":
    main()