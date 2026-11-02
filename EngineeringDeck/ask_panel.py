"""In-app Ask AI + Deep Dive center panel for Engineering Deck."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QMutex, QThread, Qt, QWaitCondition, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spock_shell.paths import SHIP_COMPUTER_DB, ensure_root_on_path

_PATH_IN_ANSWER_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/]|[\\/])[^\s\"'`<>|]+\.(?:md|html?|MD|HTML?))",
)


class _TimeoutContinueDialog(QDialog):
    """Choose a new wait window, wait forever, or cancel with retry hints."""

    RESULT_CANCEL = 0
    RESULT_RETRY_MINUTES = 1
    RESULT_UNTIL_CANCELED = 2

    def __init__(self, parent=None, body: str = "", default_minutes: int = 5):
        super().__init__(parent)
        self.setWindowTitle("LLM timed out")
        self.setModal(True)
        self._choice = self.RESULT_CANCEL
        layout = QVBoxLayout(self)
        msg = QLabel(body)
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(msg)

        row = QHBoxLayout()
        row.addWidget(QLabel("New timeout (minutes):"))
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 180)
        self.minutes.setValue(max(1, min(180, int(default_minutes or 5))))
        self.minutes.setToolTip("Maximum seconds to wait on the next attempt (minutes × 60).")
        row.addWidget(self.minutes)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox()
        self._btn_retry = buttons.addButton(
            "Retry with new timeout", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._btn_forever = buttons.addButton(
            "Continue until canceled", QDialogButtonBox.ButtonRole.ActionRole
        )
        self._btn_cancel = buttons.addButton(
            "Cancel now and provide feedback", QDialogButtonBox.ButtonRole.RejectRole
        )
        self._btn_retry.clicked.connect(self._on_retry)
        self._btn_forever.clicked.connect(self._on_forever)
        self._btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(buttons)
        self.resize(520, 280)

    def _on_retry(self) -> None:
        self._choice = self.RESULT_RETRY_MINUTES
        self.accept()

    def _on_forever(self) -> None:
        self._choice = self.RESULT_UNTIL_CANCELED
        self.accept()

    def _on_cancel(self) -> None:
        self._choice = self.RESULT_CANCEL
        self.reject()

    def choice(self) -> int:
        return self._choice

    def timeout_seconds(self) -> int:
        return int(self.minutes.value()) * 60


class _AskWorker(QThread):
    finished_ok = pyqtSignal(str, list, dict)
    failed = pyqtSignal(str)
    token_received = pyqtSignal(str)
    status_msg = pyqtSignal(str)
    # Emitted on the worker thread; main thread must call set_continue_answer.
    need_continue = pyqtSignal(str)

    def __init__(
        self,
        question: str,
        path_filter: str,
        ext_filter: str,
        exclude_ext: str,
        deep: bool,
        llm,
        hybrid_search_fn,
        emb_url: str,
        parent=None,
        packing_opts: Optional[Dict[str, Any]] = None,
        exclude_generated: bool = True,
    ):
        super().__init__(parent)
        self.question = question
        self.path_filter = path_filter
        self.ext_filter = ext_filter
        self.exclude_ext = exclude_ext
        self.exclude_generated = exclude_generated
        self.deep = deep
        self.llm = llm
        self.hybrid_search_fn = hybrid_search_fn
        self.emb_url = emb_url
        self.packing_opts = packing_opts or {}
        self._continue_mutex = QMutex()
        self._continue_cond = QWaitCondition()
        # None = waiting; False = cancel; True = same timeout; int = new seconds (0=unlimited)
        self._continue_answer: Optional[Any] = None

    def set_continue_answer(self, decision: Any) -> None:
        """Wake the worker. False cancels; True keeps timeout; int sets seconds (0=unlimited)."""
        self._continue_mutex.lock()
        try:
            self._continue_answer = decision
            self._continue_cond.wakeAll()
        finally:
            self._continue_mutex.unlock()

    def _ask_continue_after_timeout(self, detail: str) -> Any:
        """Block until the UI chooses cancel / new timeout / wait forever."""
        msg = (detail or "LLM request timed out.").strip()
        self.status_msg.emit("LLM timed out — waiting for your choice…")
        self._continue_mutex.lock()
        try:
            self._continue_answer = None
            self.need_continue.emit(msg)
            while self._continue_answer is None:
                self._continue_cond.wait(self._continue_mutex)
            return self._continue_answer
        finally:
            self._continue_mutex.unlock()

    def run(self) -> None:
        import time

        try:
            ensure_root_on_path()
            from deep_dive import build_documents_filter_clause, run_http_deep_dive
            from WarpCore.config_defaults import merge_ctx_settings

            opts = self.packing_opts or {}
            ctx_opts = merge_ctx_settings(
                opts.get("ctx") if isinstance(opts.get("ctx"), dict) else {}
            )
            stream = bool(ctx_opts.get("stream_response"))
            timing_on = bool(ctx_opts.get("timing_enabled", True))
            on_timeout = self._ask_continue_after_timeout

            filt = build_documents_filter_clause(
                self.path_filter or "",
                self.ext_filter or "",
                self.exclude_ext or "",
                exclude_generated=self.exclude_generated,
            )
            filter_info = {
                "path": self.path_filter or "",
                "include": self.ext_filter or "",
                "exclude": self.exclude_ext or "",
                "filter_clause": filt or "",
            }
            if self.deep:
                if stream:
                    self.status_msg.emit("Deep Dive — packing context…")
                result = run_http_deep_dive(
                    question=self.question,
                    filter_clause=filt,
                    history=[],
                    llm=self.llm,
                    embeddings_url=self.emb_url,
                    db_path=SHIP_COMPUTER_DB,
                    hybrid_search_fn=self.hybrid_search_fn,
                    n_ctx=int(opts.get("n_ctx") or 32768),
                    max_out_tokens=int(opts.get("max_out_tokens") or 2048),
                    ask_ai_provider=str(opts.get("ask_ai_provider") or ""),
                    chat_url=str(opts.get("chat_url") or ""),
                    record_timing=timing_on,
                    ctx=ctx_opts,
                    stream=stream,
                    on_token=(
                        (lambda tok: self.token_received.emit(tok)) if stream else None
                    ),
                    on_timeout_continue=on_timeout,
                )
                answer = (result or {}).get("answer") or ""
                sources = list((result or {}).get("sources") or [])
                timing = dict((result or {}).get("stats") or {})
            else:
                t0 = time.perf_counter()
                t_ret0 = time.perf_counter()
                self.status_msg.emit("Ask AI — retrieving…")
                results = self.hybrid_search_fn(
                    SHIP_COMPUTER_DB,
                    self.question,
                    top_k=int(ctx_opts.get("ask_top_k") or 12),
                    embeddings_url=self.emb_url,
                    filter_clause=filt,
                )
                retrieve_ms = int((time.perf_counter() - t_ret0) * 1000)
                parts: List[str] = []
                sources = []
                for r in results or []:
                    title = getattr(r, "title", None) or ""
                    path = getattr(r, "path", None) or ""
                    snip = (
                        getattr(r, "content_snippet", None)
                        or getattr(r, "snippet", None)
                        or ""
                    )
                    sources.append({"title": title, "path": path})
                    parts.append(f"### {title}\nPath: {path}\n{snip}")
                ctx = "\n\n".join(parts) if parts else "(no matching documents)"
                # ask_top_k is user-editable, so trim to what the chat window can
                # actually hold rather than trusting the knobs.
                from deep_dive import context_token_budget

                budget = int(
                    context_token_budget(
                        int(opts.get("n_ctx") or 8192),
                        max_out_tokens=int(opts.get("max_out_tokens") or 2048),
                    )
                    * float(ctx_opts.get("chars_per_token") or 2.2)
                )
                if len(ctx) > budget:
                    ctx = ctx[:budget] + "\n\n[Context truncated]"
                t_llm0 = time.perf_counter()
                stream_fn = (
                    getattr(self.llm, "ask_with_context_stream", None)
                    if stream
                    else None
                )
                from llm_client import ASK_SYSTEM_PROMPT

                if stream and callable(stream_fn):
                    self.status_msg.emit("Ask AI — streaming…")
                    chunks: List[str] = []
                    for tok in stream_fn(
                        self.question,
                        ctx,
                        ASK_SYSTEM_PROMPT,
                        history=[],
                        on_timeout_continue=on_timeout,
                    ):
                        if not tok:
                            continue
                        chunks.append(tok)
                        self.token_received.emit(tok)
                    answer = "".join(chunks) or ""
                else:
                    answer = (
                        self.llm.ask_with_context(
                            self.question,
                            ctx,
                            ASK_SYSTEM_PROMPT,
                            history=[],
                            on_timeout_continue=on_timeout,
                        )
                        or ""
                    )
                llm_ms = int((time.perf_counter() - t_llm0) * 1000)
                total_ms = int((time.perf_counter() - t0) * 1000)
                pack_summary = (
                    f"Ask AI: {len(sources)} hit(s) · {len(ctx):,} context chars"
                )
                timing = {
                    "mode": "ask",
                    "total_ms": total_ms,
                    "retrieve_ms": retrieve_ms,
                    "pack_ms": 0,
                    "llm_ms": llm_ms,
                    "docs_used": len(sources),
                    "match_count": len(sources),
                    "response_length": len(answer or ""),
                    "budget_used": len(ctx),
                    "pack_summary": pack_summary,
                    "streamed": bool(stream and callable(stream_fn)),
                }
                if timing_on:
                    try:
                        from WarpCore.ask_timing_store import insert_timing

                        insert_timing(
                            mode="ask",
                            question=self.question,
                            response_length=len(answer or ""),
                            total_ms=total_ms,
                            retrieve_ms=retrieve_ms,
                            pack_ms=0,
                            llm_ms=llm_ms,
                            docs_used=len(sources),
                            match_count=len(sources),
                            budget_used=len(ctx),
                            pack_summary=pack_summary,
                            provider=str(opts.get("ask_ai_provider") or ""),
                            stage_timings=timing,
                            filter_info=filter_info,
                            meta={"streamed": timing["streamed"]},
                            updated_by="ask_panel",
                            db_path=SHIP_COMPUTER_DB,
                        )
                    except Exception:
                        pass
            self.finished_ok.emit(answer, sources, timing)
        except Exception as e:
            self.failed.emit(str(e))


class _AnswerPreviewDialog(QDialog):
    """Render Markdown / HTML using Spock's text / WebEngine viewers."""

    def __init__(
        self, title: str, body: str, kind: str, theme: Dict[str, str], parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 650)
        lay = QVBoxLayout(self)
        bg = theme.get("panel_bg", "#1a1a1a")
        fg = theme.get("fg", "#e0e0e0")
        if kind == "html":
            try:
                from PyQt6.QtWebEngineWidgets import QWebEngineView

                view = QWebEngineView()
                view.setHtml(body)
                lay.addWidget(view, 1)
            except Exception:
                browser = QTextBrowser()
                browser.setOpenExternalLinks(True)
                browser.setHtml(body)
                lay.addWidget(browser, 1)
        else:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setStyleSheet(f"background:{bg}; color:{fg};")
            try:
                browser.setMarkdown(body)
            except Exception:
                browser.setPlainText(body)
            lay.addWidget(browser, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)


class AskAiPanel(QWidget):
    def __init__(
        self,
        theme: Dict[str, str],
        get_llm: Callable[[], Any],
        hybrid_search_fn: Callable[..., Any],
        get_emb_url: Callable[[], str],
        parent=None,
        get_config: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.get_llm = get_llm
        self.hybrid_search_fn = hybrid_search_fn
        self.get_emb_url = get_emb_url
        self.get_config = get_config
        self._worker: Optional[_AskWorker] = None
        self._last_answer = ""
        self._chat_log: List[Dict[str, str]] = []
        self._stream_started = False
        self._stream_q = ""

        lay = QVBoxLayout(self)
        title = QLabel("Engineering Deck — Ask AI / Deep Dive")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lay.addWidget(title)

        filt_row = QHBoxLayout()
        filt_row.addWidget(QLabel("Path:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            "e.g. llmfit or D:\\Spock-UIE-Wiki-KB — blank = all"
        )
        self.path_edit.setToolTip(
            "Path fragment or folder. Semicolon = several repos at once "
            "(e.g. Spock-Universal-AI-Wiki; LLMFIT). Blank = whole corpus.\n"
            "Opening Ask AI after Ship's Logs may offer to copy that Path filter."
        )
        filt_row.addWidget(self.path_edit, 1)
        filt_row.addWidget(QLabel("Include:"))
        self.ext_combo = QComboBox()
        self.ext_combo.setEditable(True)
        self.ext_combo.addItems(
            [
                "*",
                ".py,.ts,.tsx,.js,.jsx,.rs,.go",
                ".py",
                ".ts,.tsx",
                ".js,.jsx",
                ".rs",
                ".go",
                ".java,.kt",
                ".cs",
                ".cpp,.c,.h",
            ]
        )
        self.ext_combo.setCurrentText(".py,.ts,.tsx,.js,.jsx,.rs,.go")
        self.ext_combo.setMinimumWidth(140)
        self.ext_combo.setToolTip("Comma = match any extension (OR). * = any.")
        filt_row.addWidget(self.ext_combo)
        lay.addLayout(filt_row)

        excl_row = QHBoxLayout()
        self.exclude_docs = QCheckBox("Exclude .md / .txt / .rst")
        self.exclude_docs.setChecked(True)
        self.exclude_docs.setToolTip(
            "Drop documentation files from retrieval (SQL exclude, not a prompt hint)."
        )
        excl_row.addWidget(self.exclude_docs)
        self.exclude_generated = QCheckBox("Exclude generated site")
        self.exclude_generated.setChecked(True)
        self.exclude_generated.setToolTip(
            "Drop MkDocs site/ and search_index.json from retrieval. "
            "A path that already names site still searches that tree."
        )
        excl_row.addWidget(self.exclude_generated)
        excl_row.addWidget(QLabel("Also exclude:"))
        self.exclude_edit = QLineEdit()
        self.exclude_edit.setPlaceholderText("optional e.g. .html,.css")
        excl_row.addWidget(self.exclude_edit, 1)
        lay.addLayout(excl_row)

        tools = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Clear the chat transcript and start a fresh session.")
        clear_btn.clicked.connect(self._clear_chat)
        tools.addWidget(clear_btn)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search chat…")
        self.search_edit.returnPressed.connect(self._search_chat)
        tools.addWidget(self.search_edit, 1)
        find_btn = QPushButton("Search Chat")
        find_btn.clicked.connect(self._search_chat)
        tools.addWidget(find_btn)
        save_btn = QPushButton("Save to .MD")
        save_btn.clicked.connect(self._save_md)
        tools.addWidget(save_btn)
        render_btn = QPushButton("Render MD/HTML")
        render_btn.setToolTip(
            "Preview the last answer (or a .md/.html path cited in it) "
            "with Spock's markdown / HTML viewers."
        )
        render_btn.clicked.connect(self._render_answer)
        tools.addWidget(render_btn)
        lay.addLayout(tools)

        self.out = QTextEdit()
        self.out.setReadOnly(True)
        lay.addWidget(self.out, 1)
        self.inp = QTextEdit()
        self.inp.setPlaceholderText("Ask the ship computer…")
        self.inp.setMaximumHeight(100)
        lay.addWidget(self.inp)
        row = QHBoxLayout()
        self.ask_btn = QPushButton("Ask AI")
        self.ask_btn.clicked.connect(lambda: self._send(False))
        self.deep_btn = QPushButton("Deep Dive")
        self.deep_btn.clicked.connect(lambda: self._send(True))
        row.addWidget(self.ask_btn)
        row.addWidget(self.deep_btn)
        row.addStretch()
        lay.addLayout(row)
        from spock_shell.busy_ui import make_progress_bar

        self._progress = make_progress_bar()
        lay.addWidget(self._progress)
        self._status = QLabel("Ready")
        lay.addWidget(self._status)

    def path_filter(self) -> str:
        return (self.path_edit.text() or "").strip()

    def set_path_filter(self, path: str) -> None:
        self.path_edit.setText((path or "").strip())

    def _exclude_extensions(self) -> str:
        parts: List[str] = []
        if self.exclude_docs.isChecked():
            parts.extend([".md", ".txt", ".rst"])
        extra = (self.exclude_edit.text() or "").strip()
        if extra:
            parts.append(extra)
        return ",".join(parts)

    def _send(self, deep: bool) -> None:
        q = (self.inp.toPlainText() or "").strip()
        if not q or self._worker is not None:
            return
        self.ask_btn.setEnabled(False)
        self.deep_btn.setEnabled(False)
        from spock_shell.busy_ui import clear_override_cursors, set_busy

        clear_override_cursors()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        self._status.setText("Deep Dive…" if deep else "Asking…")
        set_busy(self._progress, True)
        try:
            try:
                from spock_shell.embedding_corpus import live_vs_corpus

                report = live_vs_corpus(self.get_emb_url())
                if report.get("mismatch") and report.get("message"):
                    clear_override_cursors()
                    set_busy(self._progress, False)
                    reply = QMessageBox.question(
                        self,
                        "Embedding model",
                        report["message"] + "\n\nSearch anyway with the live server?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        self._status.setText(
                            "Cancelled — embedding GGUF does not match the wiki-scan corpus"
                        )
                        self.ask_btn.setEnabled(True)
                        self.deep_btn.setEnabled(True)
                        return
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    QApplication.processEvents()
                    set_busy(self._progress, True)
            except Exception:
                pass
            packing_opts: Dict[str, Any] = {}
            if self.get_config is not None:
                try:
                    from deep_dive import packing_opts_for_llm, packing_opts_from_config
                    from WarpCore.config_defaults import merge_ctx_settings
                    from WarpCore.settings_store import ensure_ctx_defaults_in_store

                    try:
                        ensure_ctx_defaults_in_store(SHIP_COMPUTER_DB)
                    except Exception:
                        pass
                    cfg = self.get_config() or {}
                    if "ctx" not in cfg or not isinstance(cfg.get("ctx"), dict):
                        cfg = dict(cfg)
                        cfg["ctx"] = merge_ctx_settings(None)
                    try:
                        packing_opts = packing_opts_for_llm(cfg, self.get_llm())
                    except Exception:
                        packing_opts = packing_opts_from_config(cfg)
                except Exception:
                    packing_opts = {}
            ext = self.ext_combo.currentText().strip()
            if ext in ("*", "Any", "any"):
                ext = ""
            self._stream_started = False
            self._stream_q = q
            self._worker = _AskWorker(
                q,
                self.path_edit.text().strip(),
                ext,
                self._exclude_extensions(),
                deep,
                self.get_llm(),
                self.hybrid_search_fn,
                self.get_emb_url(),
                packing_opts=packing_opts,
                exclude_generated=self.exclude_generated.isChecked(),
            )
            self._worker.finished_ok.connect(self._on_ok)
            self._worker.failed.connect(self._on_fail)
            self._worker.token_received.connect(self._on_token)
            self._worker.status_msg.connect(self._status.setText)
            self._worker.need_continue.connect(self._on_need_continue)
            self._worker.finished.connect(self._on_done)
            self._worker.start()
        except Exception as e:
            clear_override_cursors()
            from spock_shell.busy_ui import set_busy

            set_busy(self._progress, False)
            self.ask_btn.setEnabled(True)
            self.deep_btn.setEnabled(True)
            self._status.setText("Error")
            self.out.append(f"\nError starting Ask AI: {e}\n")

    def _on_need_continue(self, message: str) -> None:
        """Main-thread prompt after an LLM timeout (worker is blocked waiting)."""
        from spock_shell.busy_ui import clear_override_cursors, set_busy
        from spock_shell.good_results_coach import tip_timeout

        clear_override_cursors()
        set_busy(self._progress, False)
        worker = self._worker
        if worker is None:
            return
        body = (message or "").strip()
        tip = tip_timeout()
        if tip and tip not in body:
            body = body + "\n\n" + tip
        body = (
            body
            + "\n\nChoose a new timeout in minutes, continue until canceled "
            "(no client timeout), or cancel now for retry hints."
        )
        dlg = _TimeoutContinueDialog(self, body=body, default_minutes=5)
        dlg.exec()
        choice = dlg.choice()
        if choice == _TimeoutContinueDialog.RESULT_RETRY_MINUTES:
            sec = dlg.timeout_seconds()
            self._status.setText(f"Retrying LLM (timeout {sec}s)…")
            set_busy(self._progress, True)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            worker.set_continue_answer(sec)
            return
        if choice == _TimeoutContinueDialog.RESULT_UNTIL_CANCELED:
            self._status.setText("Waiting until canceled (no client timeout)…")
            set_busy(self._progress, True)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            worker.set_continue_answer(0)
            return
        self._status.setText("Cancelled after LLM timeout")
        worker.set_continue_answer(False)

    def _on_token(self, token: str) -> None:
        if not token:
            return
        if not self._stream_started:
            self._stream_started = True
            from spock_shell.busy_ui import clear_override_cursors

            clear_override_cursors()
            self.out.append(f"\n### You\n{self._stream_q}\n")
            self.out.append("### Computer\n")
            self._status.setText("Streaming…")
        self.out.moveCursor(QTextCursor.MoveOperation.End)
        self.out.insertPlainText(token)
        self.out.ensureCursorVisible()

    def _on_ok(self, answer: str, sources: list, timing: dict = None) -> None:
        q = self._stream_q or self.inp.toPlainText().strip()
        self._chat_log.append({"role": "user", "content": q})
        self._chat_log.append({"role": "assistant", "content": answer or ""})
        self._last_answer = answer or ""
        if not self._stream_started:
            self.out.append(f"\n### You\n{q}\n")
            self.out.append(f"### Computer\n{answer}\n")
        elif sources:
            self.out.append("")
        if sources:
            self.out.append("Sources:")
            for s in sources[:8]:
                self.out.append(
                    f"- {s.get('title') or 'doc'} — {s.get('path') or ''}"
                )
        summary = (timing or {}).get("pack_summary") or (timing or {}).get("summary")
        if summary:
            self.out.append(f"_{summary}_")
        if (timing or {}).get("mode") == "ask":
            self.out.append(
                "_Snippet answer. For code architecture, tick Deep Dive — it packs "
                "whole files, and a repo path filter narrows it further._"
            )
        try:
            from spock_shell.good_results_coach import collect_ask_tips

            tips = collect_ask_tips(
                question=q,
                path_filter=self.path_edit.text().strip(),
                timing=timing,
                answer=answer or "",
            )
        except Exception:
            tips = []
        for tip in tips:
            self.out.append(f"_{tip}_")
        self.inp.clear()
        timing = timing or {}
        total_ms = timing.get("total_ms")
        if total_ms is not None:
            ret = timing.get("retrieve_ms")
            pack = timing.get("pack_ms")
            llm = timing.get("llm_ms")
            bits = [f"{total_ms} ms total"]
            if ret is not None:
                bits.append(f"retrieve {ret}")
            if pack is not None and int(pack or 0) > 0:
                bits.append(f"pack {pack}")
            if llm is not None:
                bits.append(f"llm {llm}")
            resp_len = timing.get("response_length")
            if resp_len is None:
                resp_len = len(answer or "")
            bits.append(f"{resp_len} chars out")
            if timing.get("streamed"):
                bits.append("streamed")
            status = "Ready — " + " · ".join(bits)
            if tips:
                status = status + " · " + tips[0]
            self._status.setText(status)
        else:
            self._status.setText(tips[0] if tips else "Ready")
        self._stream_started = False
        self._stream_q = ""

    def _on_fail(self, err: str) -> None:
        self.out.append(f"\nError: {err}\n")
        try:
            from spock_shell.good_results_coach import collect_ask_tips

            tips = collect_ask_tips(
                question=self._stream_q or "",
                path_filter=self.path_edit.text().strip(),
                answer=err or "",
                timed_out="timed out" in (err or "").lower(),
            )
        except Exception:
            tips = []
        for tip in tips:
            self.out.append(f"_{tip}_")
        self._status.setText(tips[0] if tips else "Error")
        self._stream_started = False
        self._stream_q = ""

    def _on_done(self) -> None:
        from spock_shell.busy_ui import clear_override_cursors, set_busy

        clear_override_cursors()
        set_busy(self._progress, False)
        self._worker = None
        self.ask_btn.setEnabled(True)
        self.deep_btn.setEnabled(True)

    def _clear_chat(self) -> None:
        """Wipe transcript and saved turns so the next Ask / Deep Dive starts fresh."""
        self._chat_log.clear()
        self._last_answer = ""
        self.out.clear()
        self.search_edit.clear()
        self._status.setText("Ready — chat cleared")

    def _search_chat(self) -> None:
        needle = (self.search_edit.text() or "").strip()
        if not needle:
            return
        doc = self.out.document()
        cursor = self.out.textCursor()
        start = cursor.selectionEnd() if cursor.hasSelection() else cursor.position()
        found = doc.find(needle, start)
        if found.isNull():
            found = doc.find(needle, 0)
        if found.isNull():
            self._status.setText(f'No match for "{needle}"')
            return
        self.out.setTextCursor(found)
        self.out.ensureCursorVisible()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#665c00"))
        found.mergeCharFormat(fmt)
        self._status.setText(f'Found "{needle}"')

    def _save_md(self) -> None:
        if not self._chat_log and not (self.out.toPlainText() or "").strip():
            QMessageBox.information(self, "Save to .MD", "Nothing to save yet.")
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Ask AI chat",
            f"spock-ask-ai-{stamp}.md",
            "Markdown (*.md);;All (*.*)",
        )
        if not path:
            return
        lines = [f"# Spock Ask AI — {stamp}", ""]
        if self._chat_log:
            for turn in self._chat_log:
                role = "You" if turn.get("role") == "user" else "Computer"
                lines.append(f"## {role}")
                lines.append("")
                lines.append(turn.get("content") or "")
                lines.append("")
        else:
            lines.append(self.out.toPlainText())
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            self._status.setText(f"Saved {path}")
        except OSError as e:
            QMessageBox.warning(self, "Save to .MD", str(e))

    def _render_answer(self) -> None:
        text = (self._last_answer or self.out.toPlainText() or "").strip()
        if not text:
            QMessageBox.information(self, "Render", "No answer to render yet.")
            return
        for m in _PATH_IN_ANSWER_RE.finditer(text):
            path = m.group("path")
            if os.path.isfile(path):
                try:
                    from db_browser import PreviewDialog

                    PreviewDialog(path, parent=self, theme=self.theme).exec()
                    return
                except Exception as e:
                    self._status.setText(f"Preview failed: {e}")
                    break
        fence = re.search(
            r"```(?:html|htm)\s*\n(.*?)```", text, re.IGNORECASE | re.DOTALL
        )
        if fence:
            _AnswerPreviewDialog(
                "Ask AI — HTML", fence.group(1), "html", self.theme, self
            ).exec()
            return
        stripped = text.lstrip().lower()
        if stripped.startswith("<!doctype html") or stripped.startswith("<html"):
            _AnswerPreviewDialog(
                "Ask AI — HTML", text, "html", self.theme, self
            ).exec()
            return
        _AnswerPreviewDialog(
            "Ask AI — Markdown", text, "md", self.theme, self
        ).exec()
