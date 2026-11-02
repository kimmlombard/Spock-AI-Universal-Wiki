"""Background QThreads for model selector panels."""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import QThread, pyqtSignal

from model_selector_core import (
    download_models,
    fetch_model_card,
    query_hf_embedding_models,
    query_hf_models,
)
from spock_scanner_core import generate_llamaccp_config, run_full_hardware_assessment


class HardwareScanWorker(QThread):
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.finished_ok.emit(run_full_hardware_assessment())
        except Exception as e:
            self.failed.emit(str(e))


class LlamaConfigWorker(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.finished_ok.emit(generate_llamaccp_config())
        except Exception as e:
            self.failed.emit(str(e))


class HfQueryWorker(QThread):
    finished_ok = pyqtSignal(list, list)
    failed = pyqtSignal(str)

    def __init__(self, specs: dict, embedding: bool = False, parent=None):
        super().__init__(parent)
        self.specs = specs
        self.embedding = embedding

    def run(self):
        try:
            if self.embedding:
                models, close = query_hf_embedding_models(self.specs)
            else:
                models, close = query_hf_models(self.specs)
            self.finished_ok.emit(models, close)
        except Exception as e:
            self.failed.emit(str(e))


class DownloadWorker(QThread):
    progress = pyqtSignal(str, float)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, model_ids: List[str], parent=None):
        super().__init__(parent)
        self.model_ids = model_ids

    def run(self):
        try:
            def cb(text, value):
                self.progress.emit(text, value)

            result = download_models(self.model_ids, progress_cb=cb)
            ok = result.get("downloaded") or []
            bad = result.get("failed") or []
            gguf_n = int(result.get("gguf_total") or 0)
            if not ok:
                errs = "\n\n".join(
                    f"{f.get('id')}:\n{f.get('error')}" for f in bad[:2]
                ) or "unknown error"
                self.failed.emit(
                    "HF download failed (LM Studio is not required).\n\n"
                    f"{errs}"
                )
                return
            msg = (
                f"Download complete: {len(ok)} model(s), {gguf_n} GGUF file(s) "
                f"in .\\models — use Launch (llama-server), not LM Studio."
            )
            if bad:
                msg += f" ({len(bad)} failed)"
            self.finished_ok.emit(msg)
        except Exception as e:
            self.failed.emit(str(e))


class ModelCardWorker(QThread):
    finished_ok = pyqtSignal(str)

    def __init__(self, model_id: str, parent=None):
        super().__init__(parent)
        self.model_id = model_id

    def run(self):
        self.finished_ok.emit(fetch_model_card(self.model_id))
