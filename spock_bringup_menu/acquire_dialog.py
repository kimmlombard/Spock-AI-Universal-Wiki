"""Step 3 Acquire — pick the embed and chat GGUFs that fit this host.

The shortlists come from the host recipe (the same artefact Launch reads), so
what is offered here is what the machine can actually run: several best-fitting
models per role, guided by ``llmfit_session_criteria.json`` (default Google /
Gemma + EmbeddingGemma) and labelled with llmfit's vocabulary — perfect, good,
tight. A dim mismatch means re-embed + wiki scan after download.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

_FIT_COLORS = {
    "perfect": "#4CAF50",
    "good": "#8BC34A",
    "tight": "#FF9800",
}


class _ShortlistWorker(QThread):
    """Hub queries take ~20 s; keep the dialog responsive."""

    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.db_path = db_path

    def run(self) -> None:
        try:
            from spock_onboarding.fit_select import shortlists
            from WarpCore import host_recipe as hr

            # Live probe, not the recipe's stored snapshot: ship_computer.db
            # travels between machines, and the models must fit *this* one.
            plan = hr.effective_recipe(
                self.db_path,
                reason="Auto-created for Acquire",
                created_by="bringup-acquire",
            )
            lists = shortlists(
                recipe=plan["recipe"],
                hardware=plan["hardware"],
                limit=6,
                use_hub=True,
            )
            self.finished_ok.emit({**plan, "lists": lists})
        except Exception as e:
            self.failed.emit(str(e))


class AcquireSelectDialog(QDialog):
    """Two radio groups — one model per role — over the recipe's fit budget."""

    def __init__(self, db_path: str, theme: Optional[Dict[str, str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3 Acquire — choose models that fit this host")
        self.setMinimumWidth(760)
        self._db_path = db_path
        self._theme = theme or {}
        self._buttons: Dict[str, List[QRadioButton]] = {"embed": [], "chat": []}
        self._picks: Dict[str, List[Dict[str, Any]]] = {"embed": [], "chat": []}
        self._plan: Dict[str, Any] = {}
        self._can_persist = False
        self.result_selection: Dict[str, Dict[str, Any]] = {}
        self.recipe_updated: str = ""

        self._lay = QVBoxLayout(self)
        self._status = QLabel("Reading host recipe and matching models…")
        self._status.setWordWrap(True)
        self._lay.addWidget(self._status)

        from spock_shell.busy_ui import make_progress_bar, set_busy

        self._progress = make_progress_bar()
        self._lay.addWidget(self._progress)
        set_busy(self._progress, True)

        self._groups: Dict[str, QGroupBox] = {}
        for role, title in (
            ("embed", "Embedding model (:8080)"),
            ("chat", "Chat model (:8081)"),
        ):
            box = QGroupBox(title)
            QVBoxLayout(box)
            self._groups[role] = box
            self._lay.addWidget(box)

        # Only shown when the saved recipe describes another machine.
        self._persist = QCheckBox()
        self._persist.setVisible(False)
        self._lay.addWidget(self._persist)

        self._buttons_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons_box.accepted.connect(self.accept)
        self._buttons_box.rejected.connect(self.reject)
        self._buttons_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._buttons_box.button(QDialogButtonBox.StandardButton.Ok).setText("Download")
        self._lay.addWidget(self._buttons_box)

        self._worker = _ShortlistWorker(db_path, self)
        self._worker.finished_ok.connect(self._on_ready)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_failed(self, err: str) -> None:
        from spock_shell.busy_ui import set_busy

        set_busy(self._progress, False)
        self._status.setText(
            f"Could not build a shortlist: {err}\n"
            "Acquire can still run — it will match the recipe itself, or fall "
            "back to the built-in catalog."
        )

    def _on_ready(self, payload: Dict[str, Any]) -> None:
        from spock_shell.busy_ui import set_busy

        set_busy(self._progress, False)
        recipe = payload.get("recipe") or {}
        hardware = payload.get("hardware") or {}
        lists = payload.get("lists") or {}
        self._plan = payload

        head = [
            f"This host: {hardware.get('gpu_summary')} · RAM "
            f"{hardware.get('host_ram_gb')} GB"
        ]
        source = payload.get("source")
        if source == "created":
            head.append(
                f"Host recipe created from this probe: {recipe.get('gpu_policy')}."
            )
        elif source == "live-proposal":
            stored = (payload.get("stored") or {}).get("recipe") or {}
            head.append(
                "Saved recipe describes different hardware, so these models are "
                f"sized for the live probe: {recipe.get('gpu_policy')} "
                f"(saved: {stored.get('gpu_policy')})."
            )
            head.append("Drift: " + "; ".join(payload.get("drift") or []))
        else:
            head.append(f"Host recipe: {recipe.get('gpu_policy')}.")
        self._status.setText("\n".join(head))

        if source == "live-proposal":
            self._persist.setText(
                "Also save this hardware as a new host recipe version "
                f"({recipe.get('gpu_policy')}, embed -c {recipe.get('embed_n_ctx')}, "
                f"chat -c {recipe.get('chat_n_ctx')}"
                + (
                    f", tensor-split {recipe.get('tensor_split')}"
                    if recipe.get("tensor_split")
                    else ""
                )
                + ") so Launch uses it too"
            )
            self._persist.setChecked(True)
            self._persist.setVisible(True)
            self._can_persist = True

        for role in ("embed", "chat"):
            data = lists.get(role) or {}
            self._picks[role] = list(data.get("picks") or [])
            self._fill_group(role, data)

        ok = bool(self._picks["embed"] and self._picks["chat"])
        self._buttons_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def _fill_group(self, role: str, data: Dict[str, Any]) -> None:
        box = self._groups[role]
        lay = box.layout()
        budget = data.get("budget") or {}
        source = data.get("source")
        note = QLabel(
            f"Budget {budget.get('budget_gb')} GB of {budget.get('pool_gb')} GB VRAM"
            + (
                f" (reserving {budget.get('reserve_gb')} GB for the embedding model)"
                if budget.get("reserve_gb")
                else ""
            )
            + f" · n_ctx {budget.get('n_ctx')} · candidates from "
            + (
                "llmfit dashboard"
                if source == "llmfit-dashboard"
                else ("Hugging Face" if source == "hub" else "built-in catalog")
            )
        )
        note.setWordWrap(True)
        lay.addWidget(note)
        if data.get("error"):
            hub_err = QLabel(f"Hub unavailable: {str(data['error'])[:160]}")
            hub_err.setWordWrap(True)
            lay.addWidget(hub_err)

        for i, pick in enumerate(self._picks[role]):
            btn = QRadioButton(self._label_for(pick))
            btn.setFont(QFont("Consolas", 9))
            color = _FIT_COLORS.get(str(pick.get("fit_level")), "#BDBDBD")
            btn.setStyleSheet(f"QRadioButton {{ color: {color}; }}")
            tip = [
                f"{pick.get('id')}",
                f"fit {pick.get('fit_level')} (from {pick.get('fit_source')})",
                f"needs ~{pick.get('need_gb')} GB, leaves {pick.get('headroom_gb')} GB",
            ]
            if pick.get("dim_mismatch"):
                tip.append(
                    f"dim {pick.get('dim')} differs from the {data.get('existing_dim')} "
                    "already in ship_computer.db — re-embed and re-run wiki scan"
                )
            btn.setToolTip("\n".join(tip))
            btn.setChecked(i == 0)
            lay.addWidget(btn)
            self._buttons[role].append(btn)

        if any(p.get("dim_mismatch") for p in self._picks[role]):
            warn = QLabel(
                f"Vectors in ship_computer.db use dim {data.get('existing_dim')}. "
                "Picking a different dim requires re-embed, then re-run wiki scan."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #FF9800;")
            lay.addWidget(warn)

    @staticmethod
    def _label_for(pick: Dict[str, Any]) -> str:
        bits = [
            f"{pick.get('fit_level', '?'):<9}",
            f"{str(pick.get('id'))}",
            f"{str(pick.get('fit_quant') or '').upper()}",
            f"~{pick.get('need_gb')} GB",
            f"-c {pick.get('fit_n_ctx')}",
        ]
        if pick.get("estimated_tps"):
            bits.append(f"~{float(pick['estimated_tps']):.0f} tok/s")
        if pick.get("dim"):
            bits.append(f"dim {pick['dim']}")
        return "  ".join(bits)

    def _selected(self, role: str) -> Optional[Dict[str, Any]]:
        for btn, pick in zip(self._buttons[role], self._picks[role]):
            if btn.isChecked():
                return pick
        return None

    def accept(self) -> None:
        embed = self._selected("embed")
        chat = self._selected("chat")
        if not embed or not chat:
            return
        self.result_selection = {"embed": embed, "chat": chat}
        if self._can_persist and self._persist.isChecked():
            self._save_recipe_version()
        super().accept()

    def _save_recipe_version(self) -> None:
        """Append a recipe version for the machine we just probed."""
        try:
            from WarpCore import host_recipe as hr

            row = hr.apply_drift_update(
                self._db_path,
                live=self._plan.get("hardware"),
                drift=self._plan.get("drift"),
                created_by="bringup-acquire",
            )
            recipe = row.get("recipe") or {}
            self.recipe_updated = (
                f"host recipe v{row.get('version')} saved — "
                f"{recipe.get('gpu_policy')}, embed -c {recipe.get('embed_n_ctx')}, "
                f"chat -c {recipe.get('chat_n_ctx')}"
                + (
                    f", tensor-split {recipe.get('tensor_split')}"
                    if recipe.get("tensor_split")
                    else ""
                )
            )
        except Exception as e:
            self.recipe_updated = f"host recipe update failed: {e}"

    def cli_args(self) -> List[str]:
        """Selections as ``spock_bringup acquire`` flags."""
        sel = self.result_selection
        if not sel:
            return []
        embed, chat = sel["embed"], sel["chat"]
        return [
            "--embed-repo",
            str(embed.get("id")),
            "--embed-quant",
            str(embed.get("fit_quant") or "Q8_0").upper(),
            "--embed-n-ctx",
            str(int(embed.get("fit_n_ctx") or 4096)),
            "--chat-repo",
            str(chat.get("id")),
            "--chat-quant",
            str(chat.get("fit_quant") or "Q4_K_M").upper(),
            "--chat-n-ctx",
            str(int(chat.get("fit_n_ctx") or 8192)),
        ]
