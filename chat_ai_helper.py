"""Chat AI Helper — suite how-to Q&A from AIHelperDocuments (chat LLM only).

Embeddings / ship_computer.db RAG are optional bonus context when available.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from WarpCore.theme import THEMES

SCRIPT_DIR = Path(__file__).resolve().parent
HELPER_DIR_NAME = "AIHelperDocuments"
BACKGROUND_HELPER = "00-Background-HELPER.md"

_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    "logs",
    "models",
}


def project_root() -> Path:
    return SCRIPT_DIR


def helper_docs_root(root: Optional[Path] = None) -> Path:
    return (root or project_root()).resolve() / HELPER_DIR_NAME


def markdown_paths_under_root(root: Optional[Path] = None) -> List[Path]:
    """List *.md files under AIHelperDocuments/ only (curated HELPER docs)."""
    docs = helper_docs_root(root)
    found: List[Path] = []
    if not docs.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(docs):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
        for name in filenames:
            if name.lower().endswith(".md"):
                found.append(Path(dirpath) / name)
    found.sort(key=lambda p: str(p).lower())
    return found


def sql_md_path_filter(root: Optional[Path] = None) -> str:
    """SQLite filter: documents under AIHelperDocuments ending in .md (optional RAG)."""
    docs = helper_docs_root(root).resolve()
    root_bs = str(docs).replace("'", "''")
    root_fwd = root_bs.replace("\\", "/")
    return (
        "("
        f"(path LIKE '{root_bs}{os.sep}%' OR path LIKE '{root_bs}/%' "
        f"OR path LIKE '{root_fwd}/%' OR lower(path) LIKE '%aihelperdocument%')"
        " AND lower(path) LIKE '%.md'"
        ")"
    )


def _extract_terms(query: str) -> List[str]:
    stop = {
        "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "how",
        "what", "does", "do", "is", "are", "can", "with", "this", "that",
        "spock", "bridge", "please", "me", "my",
    }
    tokens = re.findall(r"[A-Za-z0-9_]{2,}", query or "")
    out: List[str] = []
    seen = set()
    for t in tokens:
        low = t.lower()
        if low in stop or low in seen:
            continue
        seen.add(low)
        out.append(low)
    return out[:12]


# path -> (mtime_ns, text)
_DOC_TEXT_CACHE: Dict[str, Tuple[int, str]] = {}


def invalidate_doc_cache() -> None:
    """Drop cached HELPER markdown bodies (tests / forced refresh)."""
    _DOC_TEXT_CACHE.clear()


def _read_markdown_cached(path: Path) -> Optional[str]:
    """Read UTF-8 markdown with an mtime-keyed in-memory cache."""
    try:
        st = path.stat()
        mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    except OSError:
        return None
    key = str(path.resolve())
    hit = _DOC_TEXT_CACHE.get(key)
    if hit and hit[0] == mtime_ns:
        return hit[1]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    _DOC_TEXT_CACHE[key] = (mtime_ns, text)
    return text


def score_markdown_files(
    query: str,
    root: Optional[Path] = None,
    limit: int = 8,
    max_chars: int = 3500,
) -> List[Dict[str, Any]]:
    """Keyword-rank HELPER *.md files under AIHelperDocuments/ for helper context."""
    terms = _extract_terms(query)
    hits: List[Tuple[float, Path, str]] = []
    for path in markdown_paths_under_root(root):
        text = _read_markdown_cached(path)
        if text is None:
            continue
        blob = f"{path.name}\n{text}".lower()
        if terms:
            score = float(sum(blob.count(t) for t in terms))
            # Prefer background + HELPER naming when tied
            name_l = path.name.lower()
            if name_l == BACKGROUND_HELPER.lower():
                score += 1.0
            elif name_l.endswith("-helper.md"):
                score += 0.5
            if score <= 0:
                continue
        else:
            score = 1.0 if path.name.lower() == BACKGROUND_HELPER.lower() else 0.0
            if score <= 0:
                continue
        snippet = text[:max_chars] + ("..." if len(text) > max_chars else "")
        hits.append((score, path, snippet))
    hits.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for score, path, snippet in hits[:limit]:
        out.append(
            {
                "title": path.name,
                "path": str(path),
                "score": score,
                "snippet": snippet,
                "source": "disk-md",
            }
        )
    return out


def _ensure_background_source(
    sources: List[Dict[str, Any]],
    root: Optional[Path] = None,
    max_chars: int = 3500,
) -> List[Dict[str, Any]]:
    """Always include 00-Background-HELPER.md when present."""
    bg = helper_docs_root(root) / BACKGROUND_HELPER
    if not bg.is_file():
        return sources
    bg_s = str(bg.resolve()).lower()
    if any(str(s.get("path", "")).lower() == bg_s for s in sources):
        return sources
    text = _read_markdown_cached(bg)
    if text is None:
        return sources
    snippet = text[:max_chars] + ("..." if len(text) > max_chars else "")
    return [
        {
            "title": bg.name,
            "path": str(bg),
            "score": 999.0,
            "snippet": snippet,
            "source": "disk-md-background",
        },
        *sources,
    ]

class CopyableResultDialog(QDialog):
    """Gemma-style result modal with Select All / Copy to clipboard."""

    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 440)
        layout = QVBoxLayout(self)
        self.box = QTextEdit()
        self.box.setReadOnly(True)
        self.box.setFont(QFont("Consolas", 10))
        self.box.setPlainText(content)
        layout.addWidget(self.box)
        row = QHBoxLayout()
        select_btn = QPushButton("Select All")
        copy_btn = QPushButton("Copy")
        close_btn = QPushButton("Close")
        select_btn.clicked.connect(self.box.selectAll)
        copy_btn.setToolTip("Copy all text to the clipboard")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(self.box.toPlainText())
        )
        close_btn.clicked.connect(self.accept)
        row.addWidget(select_btn)
        row.addWidget(copy_btn)
        row.addStretch()
        row.addWidget(close_btn)
        layout.addLayout(row)


class ChatAIHelperWorker(QThread):
    """Background: scoped md search (+ optional DB embeddings) then LLM answer."""

    response_ready = pyqtSignal(str)
    token_received = pyqtSignal(str)
    sources_ready = pyqtSignal(list)
    status_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        question: str,
        llm_client: Any,
        db_path: str,
        embeddings_url: str,
        hybrid_search_fn: Optional[Callable[..., Any]] = None,
        embeddings_ok_fn: Optional[Callable[..., Tuple[bool, str]]] = None,
        root: Optional[Path] = None,
    ):
        super().__init__()
        self.question = question
        self.llm_client = llm_client
        self.db_path = db_path
        self.embeddings_url = embeddings_url
        self.hybrid_search_fn = hybrid_search_fn
        self.embeddings_ok_fn = embeddings_ok_fn
        self.root = (root or project_root()).resolve()

    def run(self):
        try:
            sources: List[Dict[str, Any]] = []
            docs_root = helper_docs_root(self.root)
            if self.embeddings_ok_fn:
                try:
                    ok, detail = self.embeddings_ok_fn(
                        self.embeddings_url, timeout=0.5, light=True
                    )
                except Exception as e:
                    ok, detail = False, str(e)
                if ok:
                    self.status_ready.emit(
                        f"Embeddings reachable ({self.embeddings_url}) — optional RAG bonus."
                    )
                else:
                    self.status_ready.emit(
                        f"Embeddings offline ({detail}). Using AIHelperDocuments only."
                    )

            disk_hits = score_markdown_files(self.question, root=self.root, limit=8)
            sources.extend(disk_hits)
            sources = _ensure_background_source(sources, root=self.root)

            # Optional bonus: DB RAG limited to AIHelperDocuments paths only.
            if self.hybrid_search_fn and os.path.isfile(self.db_path):
                try:
                    filt = sql_md_path_filter(self.root)
                    db_results = self.hybrid_search_fn(
                        self.db_path,
                        self.question,
                        top_k=8,
                        embeddings_url=self.embeddings_url,
                        filter_clause=filt,
                    )
                    seen = {s["path"].lower() for s in sources}
                    docs_s = str(docs_root).lower().replace("/", "\\")
                    for r in db_results or []:
                        path = getattr(r, "path", "") or ""
                        path_norm = path.lower().replace("/", "\\")
                        if path_norm in seen:
                            continue
                        if not path_norm.endswith(".md"):
                            continue
                        if "aihelperdocument" not in path_norm and docs_s not in path_norm:
                            continue
                        sources.append(
                            {
                                "title": getattr(r, "title", "") or Path(path).name,
                                "path": path,
                                "score": float(getattr(r, "score", 0.0) or 0.0),
                                "snippet": getattr(r, "content_snippet", "") or "",
                                "source": "db-rag",
                            }
                        )
                        seen.add(path_norm)
                except Exception as e:
                    self.status_ready.emit(f"DB RAG skipped (optional): {e}")

            if self.isInterruptionRequested():
                return

            self.sources_ready.emit(sources[:12])

            if sources:
                parts = []
                for i, s in enumerate(sources[:8], 1):
                    parts.append(
                        f"[Doc {i}] {s.get('title')}\n"
                        f"  Path: {s.get('path')}\n"
                        f"  Source: {s.get('source')} score={s.get('score')}\n"
                        f"  Content:\n{s.get('snippet')}\n"
                    )
                context = "\n".join(parts)
            else:
                md_list = "\n".join(
                    f"  - {p.name}" for p in markdown_paths_under_root(self.root)[:20]
                )
                context = (
                    "(No matching HELPER markdown snippets found.)\n"
                    f"Markdown files under {docs_root}:\n{md_list or '(folder missing)'}"
                )

            system_prompt = (
                "You are the Spock-UIE-Wiki-KB Chat AI Helper. "
                "Answer ONLY using the provided context from curated HELPER markdown "
                f"under {docs_root} (especially 00-Background-HELPER.md and *-HELPER.md). "
                "Explain how the suite works: Bootstrap, Onboarding, Orchestrator, "
                "Navigation, Engineering, Science, Enterprise, UIEG, Maintenance, "
                "ports, SQLite DBs, and interoperability. "
                "If the context is insufficient, say so and tell the user to use in-app "
                "Google Search or Gemini for outside help. "
                "Do not invent APIs or paths outside this project."
            )

            chunks: List[str] = []
            stream_fn = getattr(self.llm_client, "ask_with_context_stream", None)
            if callable(stream_fn):
                self.status_ready.emit("Streaming answer…")
                for tok in stream_fn(
                    self.question, context, system_prompt, timeout=300
                ):
                    if self.isInterruptionRequested():
                        break
                    if not tok:
                        continue
                    chunks.append(tok)
                    self.token_received.emit(tok)
                answer = "".join(chunks).strip()
            else:
                answer = (
                    self.llm_client.ask_with_context(
                        self.question, context, system_prompt
                    )
                    or ""
                ).strip()

            if not answer:
                answer = "No response from chat provider."
            self.response_ready.emit(answer)
        except Exception as e:
            self.error_occurred.emit(str(e))


class ChatAIHelperWindow(QWidget):
    """Non-modal Chat AI Helper window (Gemma-style bubbles + provider tests)."""

    def __init__(
        self,
        theme: dict,
        main_window: Any,
        llm_client_factory: Callable[[], Any],
        hybrid_search_fn: Callable[..., Any],
        embeddings_ok_fn: Callable[..., Tuple[bool, str]],
        db_path: str,
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.main = main_window
        self.llm_client_factory = llm_client_factory
        self.hybrid_search_fn = hybrid_search_fn
        self.embeddings_ok_fn = embeddings_ok_fn
        self.db_path = db_path
        self.root = project_root()
        self._worker: Optional[ChatAIHelperWorker] = None
        self._waiting = False
        self._status_color = "green"
        self._stream_started = False
        self._stream_buf = ""

        self.setWindowTitle("Chat AI Helper — Spock-UIE-Wiki-KB")
        self.setMinimumSize(820, 640)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self._build_ui()
        self.apply_theme()
        docs = helper_docs_root(self.root)
        self._append_system(
            f"Scoped to {docs} (*-HELPER.md). Chat LLM required; embeddings optional. "
            "Ask how the Spock suite works. For outside topics use Google Search / Gemini."
        )
        self.set_status("Ready", "green")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Chat AI Helper")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        self.title_label = title
        layout.addWidget(title)

        hint = QLabel(
            "Answers from AIHelperDocuments/*-HELPER.md (disk). "
            "Embeddings / ship_computer.db RAG are optional. Not a general web search — "
            "use Google Search or Gemini for outside help."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.lbl_status = QLabel("Ready")
        layout.addWidget(self.lbl_status)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.chat_display, 1)

        self.sources_label = QLabel("Sources: (none yet)")
        self.sources_label.setWordWrap(True)
        layout.addWidget(self.sources_label)

        input_row = QHBoxLayout()
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText(
            "Ask how the Spock suite works… (Ctrl+Enter to send)"
        )
        self.input_text.setMaximumHeight(100)
        self.input_text.setFont(QFont("Segoe UI", 10))
        self.input_text.keyPressEvent = self._on_input_key_press  # type: ignore[method-assign]
        input_row.addWidget(self.input_text)

        self.btn_send = QPushButton("Send")
        self.btn_send.setMinimumHeight(80)
        self.btn_send.setMinimumWidth(80)
        self.btn_send.clicked.connect(self.on_send)
        input_row.addWidget(self.btn_send)
        layout.addLayout(input_row)

        bottom = QHBoxLayout()
        clear_btn = QPushButton("Clear chat")
        clear_btn.clicked.connect(self._on_clear)
        bottom.addWidget(clear_btn)
        select_all_btn = QPushButton("Select All")
        select_all_btn.setToolTip("Select all chat text")
        select_all_btn.clicked.connect(self._on_select_all)
        bottom.addWidget(select_all_btn)
        copy_btn = QPushButton("Copy")
        copy_btn.setToolTip("Copy chat text to the clipboard")
        copy_btn.clicked.connect(self._on_copy_chat)
        bottom.addWidget(copy_btn)
        bottom.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def _c(self, key: str) -> str:
        """Palette lookup with a dark-theme fallback for partial theme dicts."""
        return (self.theme or {}).get(key) or THEMES["dark"][key]

    def apply_theme(self):
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {self._c('bg')}; color: {self._c('text')};
            }}
            QTextEdit {{
                background-color: {self._c('bg2')}; color: {self._c('text')};
                border: 1px solid {self._c('border')};
                border-radius: 4px; padding: 4px;
                selection-background-color: {self._c('accent')};
                selection-color: {self._c('on_accent')};
            }}
            QPushButton {{
                background-color: {self._c('accent')}; color: {self._c('on_accent')};
                border: none; padding: 6px 10px; border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self._c('accent2')}; color: {self._c('on_accent2')};
            }}
            QLabel {{ color: {self._c('text')}; background-color: transparent; }}
            """
        )
        self.title_label.setStyleSheet(f"color: {self._c('accent2')};")
        self.sources_label.setStyleSheet(
            f"color: {self._c('muted')}; font-size: 11px;"
        )
        self.set_status(self.lbl_status.text(), self._status_color)

    def set_status(self, status: str, color: str = "green"):
        self._status_color = color
        role = {
            "green": "good",
            "blue": "accent2",
            "orange": "warn",
            "red": "bad",
        }.get(color)
        resolved = self._c(role) if role else color
        self.lbl_status.setText(status)
        self.lbl_status.setStyleSheet(
            f"color: {resolved}; font-weight: bold; padding: 4px;"
        )

    def append_line(self, who: str, text: str, is_error: bool = False):
        text_escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        text_formatted = (
            text_escaped.replace("\r\n", "<br>")
            .replace("\n", "<br>")
            .replace("\r", "<br>")
            .replace("  ", "&nbsp;&nbsp;")
        )
        if is_error:
            fill, rule, name = self._c("bg3"), self._c("bad"), self._c("bad")
        elif "You" in who:
            fill, rule, name = self._c("bg3"), self._c("accent"), self._c("accent2")
        else:
            fill, rule, name = self._c("bg2"), self._c("good"), self._c("good")
        # Body text is always the palette's own text color: Qt's rich-text engine
        # ignores `background` on block elements in some builds, so a bubble-tinted
        # foreground would end up unreadable straight on the widget background.
        body = self._c("text")
        self.chat_display.append(
            f"<div style='margin: 8px 0; padding: 8px; background-color: {fill}; "
            f"border-left: 4px solid {rule};'>"
            f"<b style='color: {name};'>{who}:</b><br>"
            f"<span style='color: {body}; white-space: pre-wrap;'>{text_formatted}</span>"
            "</div>"
        )
        self.chat_display.moveCursor(QTextCursor.MoveOperation.End)

    def _append_system(self, text: str):
        esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.chat_display.append(
            f"<div style='margin:4px 0;color:{self._c('muted')};'><i>ℹ️ {esc}</i></div>"
        )

    def _on_input_key_press(self, event):
        if (
            event.key() == Qt.Key.Key_Return
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.on_send()
        else:
            QTextEdit.keyPressEvent(self.input_text, event)

    def on_send(self):
        if self._waiting:
            self.set_status("Already waiting for a response…", "orange")
            return
        prompt = self.input_text.toPlainText().strip()
        if not prompt:
            self.set_status("Empty message", "orange")
            return

        if hasattr(self.main, "_apply_ask_ai_provider_config"):
            self.main._apply_ask_ai_provider_config()

        try:
            client = self.llm_client_factory()
        except Exception as e:
            self.append_line(
                "❌ Error", f"Chat provider setup failed: {e}", is_error=True
            )
            return

        if not getattr(client, "is_available", False):
            self.append_line(
                "❌ Error",
                "No chat provider available. Open Engineering Deck → "
                "Configure Spock AI and connect a backend.",
                is_error=True,
            )
            self.set_status("No chat provider", "red")
            return

        self.append_line("👤 You", prompt)
        self.input_text.clear()
        self._waiting = True
        self._stream_started = False
        self._stream_buf = ""
        self.btn_send.setEnabled(False)
        self.set_status("💫 Searching Spock docs + asking AI…", "blue")

        from model_selector_core import merge_embedding_profile

        ep = merge_embedding_profile((self.main.config or {}).get("embedding_profile"))
        emb_url = ep.get("embeddings_url", "http://localhost:8080/embeddings")

        self._worker = ChatAIHelperWorker(
            question=prompt,
            llm_client=client,
            db_path=self.db_path,
            embeddings_url=emb_url,
            hybrid_search_fn=self.hybrid_search_fn,
            embeddings_ok_fn=self.embeddings_ok_fn,
            root=self.root,
        )
        self._worker.response_ready.connect(self._on_response)
        self._worker.token_received.connect(self._on_token)
        self._worker.sources_ready.connect(self._on_sources)
        self._worker.status_ready.connect(lambda s: self._append_system(s))
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _begin_stream_bubble(self) -> None:
        fill, rule, name = self._c("bg2"), self._c("good"), self._c("good")
        body = self._c("text")
        self.chat_display.append(
            f"<div style='margin: 8px 0; padding: 8px; background-color: {fill}; "
            f"border-left: 4px solid {rule};'>"
            f"<b style='color: {name};'>🤖 Spock:</b><br>"
            f"<span style='color: {body}; white-space: pre-wrap;'></span>"
            "</div>"
        )
        self.chat_display.moveCursor(QTextCursor.MoveOperation.End)

    def _on_token(self, token: str):
        if not token:
            return
        if not self._stream_started:
            self._stream_started = True
            self._stream_buf = ""
            self._begin_stream_bubble()
            self.set_status("Streaming…", "blue")
        self._stream_buf += token
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def _on_response(self, response: str):
        if self._stream_started:
            # Tokens already shown; if stream was empty, fall back to full reply.
            if not self._stream_buf.strip() and (response or "").strip():
                self.append_line("🤖 Spock", response)
            self.set_status("Ready", "green")
            return
        self.append_line("🤖 Spock", response)
        self.set_status("Ready", "green")

    def _on_sources(self, sources: list):
        if not sources:
            self.sources_label.setText("Sources: (no markdown hits)")
            return
        bits = [f"{s.get('title')} [{s.get('source')}]" for s in sources[:8]]
        self.sources_label.setText("Sources: " + " · ".join(bits))

    def _on_error(self, err: str):
        self.append_line("❌ Error", err, is_error=True)
        self.set_status("Error", "red")

    def _on_finished(self):
        self._waiting = False
        self.btn_send.setEnabled(True)
        self._worker = None
        self._stream_started = False
        self._stream_buf = ""

    def prepare_shutdown(self):
        """Stop background work so app exit is not blocked."""
        self._force_close = True
        w = self._worker
        if w is not None and w.isRunning():
            try:
                w.requestInterruption()
            except Exception:
                pass
            if not w.wait(1500):
                w.terminate()
                w.wait(500)
        self._worker = None

    def closeEvent(self, event):
        if getattr(self, "_force_close", False):
            self.prepare_shutdown()
            event.accept()
            return
        # Keep window object for re-open from left nav.
        # WSLg needs accept()+hide(); ignore()+hide() can leave the window stuck.
        event.accept()
        self.hide()

    def _on_clear(self):
        self.chat_display.clear()
        self.sources_label.setText("Sources: (none yet)")
        self._append_system(
            f"Scoped to {helper_docs_root(self.root)} (*-HELPER.md). "
            "Ask how the Spock suite works."
        )
        self.set_status("Ready", "green")

    def _on_select_all(self):
        self.chat_display.setFocus()
        self.chat_display.selectAll()

    def _on_copy_chat(self):
        text = self.chat_display.toPlainText()
        if not text.strip():
            self.set_status("Nothing to copy — chat is empty", "orange")
            return
        QApplication.clipboard().setText(text)
        self.set_status("Chat copied to clipboard", "green")

