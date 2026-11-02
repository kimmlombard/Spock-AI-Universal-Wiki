"""Qt helpers for host-recipe create / primary AI GPU selection."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


def prompt_primary_ai_gpu(
    parent: Optional[QWidget],
    hardware: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Ask which GPU runs embed + chat when the host has more than one.

    Returns the chosen nvidia-smi index, the sole GPU index when there is only
    one card, or ``None`` if the user cancels the multi-GPU dialog.
    """
    from WarpCore import host_recipe as hr

    rows = hr.gpu_choice_rows(hardware)
    if not rows:
        return 0
    if len(rows) == 1:
        return int(rows[0]["index"]) if rows[0].get("index") is not None else 0

    default = hr.default_primary_ai_gpu_index(hardware)
    # parent=None + ApplicationModal: avoids dialogs stuck behind SuiteShell.
    dlg = QDialog(None)
    dlg.setWindowTitle("Primary AI GPU")
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumWidth(560)
    layout = QVBoxLayout(dlg)
    layout.addWidget(
        QLabel(
            "This machine has multiple GPUs.\n"
            "Which GPU should run embedding and chat LLM servers?\n\n"
            "Pick the compute card if another GPU is used for video/display\n"
            "(for example Quadro P2200 for monitors, RTX 6000 for AI)."
        )
    )
    group = QButtonGroup(dlg)
    radios: list = []
    for r in rows:
        # GPU 0 is valid — never use ``index or 0``.
        idx = int(r["index"]) if r.get("index") is not None else 0
        btn = QRadioButton(str(r.get("label") or f"GPU {idx}"))
        if idx == default:
            btn.setChecked(True)
        group.addButton(btn)
        layout.addWidget(btn)
        radios.append((btn, idx))
    if not any(b.isChecked() for b, _ in radios) and radios:
        radios[0][0].setChecked(True)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    for btn, idx in radios:
        if btn.isChecked():
            return idx
    return default


def propose_recipe_with_primary_prompt(
    parent: Optional[QWidget],
    *,
    hardware: Optional[Dict[str, Any]] = None,
    force_primary_prompt: bool = False,
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Live probe → optional primary-GPU prompt → recipe.

    Returns ``(hardware, recipe)`` or ``None`` if the user cancels a multi-GPU
    primary selection.
    """
    from WarpCore import host_recipe as hr

    hw = hardware if isinstance(hardware, dict) else hr.probe_hardware()
    proposed = hr.propose_recipe(hw)
    ask = force_primary_prompt or hr.needs_primary_ai_gpu_prompt(hw, proposed)
    if ask and hr.multi_gpu_host(hw):
        idx = prompt_primary_ai_gpu(parent, hw)
        if idx is None:
            return None
        proposed = hr.apply_primary_ai_gpu(proposed, idx, hardware=hw)
    elif not hr.multi_gpu_host(hw):
        # Single-GPU / CPU: nothing to choose; mark confirmed so later probes
        # do not keep re-asking if a second card appears mid-session.
        proposed = dict(proposed)
        proposed["primary_ai_gpu_confirmed"] = True
    return hw, proposed


def create_or_confirm_host_recipe(
    parent: Optional[QWidget],
    db_path: str,
    *,
    reason: str,
    created_by: str,
    confirm_title: str = "Create host recipe",
    confirm_body: str = "",
) -> Optional[Dict[str, Any]]:
    """Probe → primary GPU prompt (multi-GPU) → Yes/No → create or update.

    Used by Bringup, Maintenance reset rebuild, and Navigation Station so the
    same question cannot be skipped by a silent ``ensure_recipe``.
    """
    import json

    from PyQt6.QtWidgets import QMessageBox

    from WarpCore import host_recipe as hr

    live = hr.probe_hardware()
    current = hr.get_current_recipe(db_path)
    need_create = current is None
    need_confirm = hr.needs_primary_ai_gpu_prompt(
        live, (current or {}).get("recipe") if current else None
    )
    if not need_create and not need_confirm:
        return current

    built = propose_recipe_with_primary_prompt(
        parent, hardware=live, force_primary_prompt=need_confirm
    )
    if built is None:
        return None
    live, proposed = built
    preview = json.dumps(
        {
            "gpu_policy": proposed.get("gpu_policy"),
            "embed_gpu_index": proposed.get("embed_gpu_index"),
            "chat_gpu_index": proposed.get("chat_gpu_index"),
            "tensor_split": proposed.get("tensor_split"),
            "embed_n_ctx": proposed.get("embed_n_ctx"),
            "chat_n_ctx": proposed.get("chat_n_ctx"),
            "gpu_summary": proposed.get("gpu_summary"),
            "host_ram_gb": proposed.get("host_ram_gb"),
        },
        indent=2,
    )
    body = confirm_body.strip() or (
        "No host recipe yet. Create Launch defaults from this machine?"
        if need_create
        else "Confirm the primary AI GPU and save an updated host recipe?"
    )
    reply = QMessageBox.question(
        parent,
        confirm_title,
        f"{body}\n\n{preview}\n\n"
        "(You can Update later in Engineering Maintenance → Recipe.)",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return None
    if need_create:
        return hr.create_recipe(
            db_path,
            hardware=live,
            recipe=proposed,
            reason=reason,
            created_by=created_by,
        )
    return hr.update_recipe(
        db_path,
        reason=reason,
        hardware=live,
        recipe=proposed,
        created_by=created_by,
    )
