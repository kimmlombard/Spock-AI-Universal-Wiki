"""Spock Bringup Menu — novice-friendly SuiteShell for onboarding steps 1–16."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from spock_bringup_menu.center_log import BringupCenterPanel
from spock_bringup_menu.steps import (
    STEPS,
    build_cli_command,
    build_spawn_command,
    step_by_id,
)
from spock_shell.config import save_config
from spock_shell.paths import ROOT, SHIP_COMPUTER_DB, ensure_root_on_path
from spock_shell.profiles import (
    apply_profile_payload,
    build_profile_payload,
    harvest_live_config,
    maybe_load_profile,
    open_manage_profiles_dialog,
    pick_profile_payload,
    prompt_save_profile,
    save_profile_interactive,
)
from WarpCore.profile_store import count_profiles
from spock_shell.theme import THEMES
from spock_shell.widgets import SidePanel
from spock_shell.window import NavItem, SuiteShellWindow

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

HELPER_MD = "AIHelperDocuments/Spock-Bringup-Menu-HELPER.md"


def _terminate_process_tree(pid: int, timeout: float = 8.0) -> None:
    if psutil is None:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        return
    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    kids = parent.children(recursive=True)
    for child in kids:
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    try:
        parent.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    _, alive = psutil.wait_procs(kids + [parent], timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _servers_ready_from_json(root: Path) -> bool:
    path = root / "spock_ready_last.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if data.get("servers_ready") is True:
        return True
    embed = data.get("embed") if isinstance(data.get("embed"), dict) else {}
    chat = data.get("chat") if isinstance(data.get("chat"), dict) else {}
    return bool(embed.get("reachable") and chat.get("reachable"))


class BringupMenuWindow(SuiteShellWindow):
    app_title = "Spock Bringup Menu"
    app_subtitle = (
        "Lite onboarding console — run Phase A–B, acquire models, bring up "
        "servers, then launch suite tools."
    )

    def __init__(self, parent=None):
        ensure_root_on_path()
        self._root = Path(ROOT)
        self._suite_procs: List[subprocess.Popen] = []
        self._active_step_id: Optional[int] = None
        self._nav_enabled = True
        self._center: Optional[BringupCenterPanel] = None
        self._ask = None
        self._ai_helper_unlocked = _servers_ready_from_json(self._root)
        # Skip LlamaServerManager at startup (avoids scan lag); create on demand
        # when loading a profile that needs to relaunch :8080 / :8081.
        self.server_manager = None
        super().__init__(parent)
        if self._center is not None:
            self._center.progress.finished.connect(self._on_cli_finished)
        self._host_recipe_offer_done = False
        QTimer.singleShot(0, self._offer_profile_load)

    def on_ready(self) -> None:
        if self._center is not None:
            self.show_center(self._center)
        else:
            self.show_home()

    def schedule_host_recipe_offer(self, delay_ms: int = 250) -> None:
        """Public hook for ``__main__`` after ``show()`` — backup if profile path skips."""
        QTimer.singleShot(max(0, int(delay_ms)), self._offer_host_recipe)

    def build_home_widget(self) -> QWidget:
        # Center workspace is the progress panel; home markdown still available.
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        self._center = BringupCenterPanel()
        lay.addWidget(self._center)
        return wrap

    def build_right_dock(self, layout: QVBoxLayout) -> None:
        profiles = SidePanel("Profiles", self.theme)
        profiles.add_button("Save profile…", self._save_profile)
        profiles.add_button("Load profile…", self._load_profile)
        profiles.add_button("Manage profiles…", self._manage_profiles)
        layout.addWidget(profiles)
        super().build_right_dock(layout)

    def show_home(self) -> None:
        if self._center is not None:
            self.show_center(self._center)
        else:
            super().show_home()

    def nav_steps(self) -> Sequence[NavItem]:
        steps: List[NavItem] = []
        for s in STEPS:
            sid = s.id
            steps.append((s.nav_label, lambda *_, i=sid: self._run_step(i)))
        return steps

    def open_ai_helper(self) -> None:
        if not self._ai_helper_unlocked:
            QMessageBox.information(
                self,
                "AI Helper",
                "AI Helper unlocks after step 4 (Bring up servers) succeeds,\n"
                "or when spock_ready_last.json already reports servers ready.\n\n"
                "Run step 4 first.",
            )
            return
        super().open_ai_helper()

    def closeEvent(self, event) -> None:  # noqa: N802
        # First launch only: offer save when ship_computer has no profiles yet.
        # Later exits save from Navigation Station (or explicit Save profile…).
        try:
            no_profiles_yet = count_profiles(SHIP_COMPUTER_DB) <= 0
        except Exception:
            no_profiles_yet = False
        if no_profiles_yet and not prompt_save_profile(
            self, self._profile_payload()
        ):
            event.ignore()
            return
        if self._center and self._center.progress.is_running:
            self._center.progress.stop()
        self._reap_suite_children()
        super().closeEvent(event)

    def _ensure_server_manager(self):
        if self.server_manager is None:
            try:
                from llama_server_manager import LlamaServerManager

                self.server_manager = LlamaServerManager()
            except Exception:
                self.server_manager = None
        return self.server_manager

    def _profile_payload(self) -> Dict[str, Any]:
        harvest_live_config(self.config)
        payload = build_profile_payload(
            self.config,
            llama_manager=self.server_manager,
        )
        # Keep in-memory config aligned with embed (:8080) / chat (:8081) GGUFs.
        pc = payload.get("config") or {}
        ep = pc.get("embedding_profile")
        if isinstance(ep, dict):
            live_ep = self.config.setdefault("embedding_profile", {})
            if not isinstance(live_ep, dict):
                live_ep = {}
                self.config["embedding_profile"] = live_ep
            for key in ("model_path", "model_id"):
                if ep.get(key):
                    live_ep[key] = ep[key]
        if pc.get("chat_model_path"):
            self.config["chat_model_path"] = pc["chat_model_path"]
        if pc.get("chat_model_name"):
            self.config["chat_model_name"] = pc["chat_model_name"]
        return payload

    def _save_profile(self) -> None:
        save_profile_interactive(
            self,
            self._profile_payload(),
            prompt=(
                "Save Bringup settings as a named profile in ship_computer.db?\n"
                "(providers, embedding :8080, chat :8081, RAG/MCP flags)"
            ),
        )

    def _load_profile(self) -> None:
        payload = pick_profile_payload(self)
        if not payload:
            return
        self._pending_profile_payload = payload
        QTimer.singleShot(0, self._apply_pending_profile_payload)

    def _manage_profiles(self) -> None:
        open_manage_profiles_dialog(self)

    def _offer_profile_load(self) -> None:
        payload = maybe_load_profile(self)
        if payload:
            self._pending_profile_payload = payload
            # Apply first so host-recipe modals are not buried under profile work.
            self._apply_pending_profile_payload()
        QTimer.singleShot(100, self._offer_host_recipe)

    def _offer_host_recipe(self) -> None:
        """Create / confirm primary AI GPU on first run; on drift, offer update."""
        if getattr(self, "_host_recipe_offer_done", False):
            return
        self._host_recipe_offer_done = True
        try:
            from WarpCore import host_recipe as hr
            from spock_shell.host_recipe_ui import (
                create_or_confirm_host_recipe,
                propose_recipe_with_primary_prompt,
            )
            from spock_shell.paths import SHIP_COMPUTER_DB
            from spock_shell.profiles import prompts_enabled

            if not prompts_enabled():
                self._log_launch(
                    "Host recipe prompt skipped (SPOCK_PROFILE_PROMPTS/offscreen)"
                )
                return
            current = hr.get_current_recipe(SHIP_COMPUTER_DB)
            live = hr.probe_hardware()
            self._log_launch(
                f"Host recipe check: gpus={live.get('gpu_count')} "
                f"current={'v' + str(current.get('version')) if current else 'none'} "
                f"need_primary={hr.needs_primary_ai_gpu_prompt(live, (current or {}).get('recipe'))}"
            )
            # Missing recipe, or multi-GPU recipe never confirmed by the user
            # (silent ensure_recipe / effective_recipe left a heuristic behind).
            if current is None or hr.needs_primary_ai_gpu_prompt(
                live, current.get("recipe")
            ):
                row = create_or_confirm_host_recipe(
                    self,
                    SHIP_COMPUTER_DB,
                    reason=(
                        "Initial host recipe (Bringup)"
                        if current is None
                        else "Primary AI GPU confirmed (Bringup)"
                    ),
                    created_by="bringup",
                    confirm_title="Create host recipe"
                    if current is None
                    else "Confirm primary AI GPU",
                    confirm_body=(
                        "No host recipe yet. Create Launch defaults from this machine?"
                        if current is None
                        else "This multi-GPU host has no confirmed primary AI GPU yet.\n"
                        "Confirm which card should run embedding and chat."
                    ),
                )
                if row is None:
                    self._log_launch(
                        "Host recipe create/confirm cancelled "
                        "(primary GPU not chosen or declined)"
                    )
                    return
                proposed = row.get("recipe") or {}
                self._log_launch(
                    f"Host recipe v{row.get('version')} ready "
                    f"(policy={proposed.get('gpu_policy')}, "
                    f"AI GPU {proposed.get('embed_gpu_index')})"
                )
                return
            drift = hr.hardware_drift(current, live=live)
            if not drift:
                return
            self._log_launch("Host recipe drift: " + "; ".join(drift))
            # A drifted recipe usually means ship_computer.db moved to another
            # machine. Offer the update here rather than only logging it: Launch
            # reads the stored recipe, so a stale one mis-sizes -c and GPU flags.
            built = propose_recipe_with_primary_prompt(
                self, hardware=live, force_primary_prompt=hr.multi_gpu_host(live)
            )
            if built is None:
                self._log_launch(
                    "Host recipe update cancelled (primary GPU not chosen)"
                )
                return
            live, proposed = built
            saved = current.get("recipe") or {}
            reply = QMessageBox.question(
                self,
                "Host recipe — hardware changed",
                "This machine no longer matches the saved host recipe:\n\n"
                + "\n".join(f"  • {d}" for d in drift)
                + "\n\nSaved: "
                + f"{saved.get('gpu_policy')}, embed -c {saved.get('embed_n_ctx')}, "
                + f"chat -c {saved.get('chat_n_ctx')}"
                + "\nThis host: "
                + f"{proposed.get('gpu_policy')}, AI GPU {proposed.get('embed_gpu_index')}, "
                + f"embed -c {proposed.get('embed_n_ctx')}, "
                + f"chat -c {proposed.get('chat_n_ctx')}"
                + (
                    f", tensor-split {proposed.get('tensor_split')}"
                    if proposed.get("tensor_split")
                    else ""
                )
                + "\n\nSave a new recipe version for this host?\n"
                "(Versions are kept — history is in Maintenance → Recipe. "
                "Model selection in step 3 uses the live probe either way.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._log_launch(
                    "Host recipe left as-is — Update later in Maintenance → Recipe"
                )
                return
            row = hr.update_recipe(
                SHIP_COMPUTER_DB,
                reason="Hardware drift (Bringup): " + "; ".join(drift),
                hardware=live,
                recipe=proposed,
                created_by="bringup",
            )
            self._log_launch(
                f"Host recipe v{row.get('version')} saved "
                f"(policy={proposed.get('gpu_policy')}, "
                f"AI GPU {proposed.get('embed_gpu_index')})"
            )
        except Exception as e:
            if self._center is not None:
                stamp = datetime.now().strftime("%H:%M:%S")
                self._center.append_launch(f"[{stamp}] Host recipe check skipped: {e}")

    def _apply_pending_profile_payload(self) -> None:
        payload = getattr(self, "_pending_profile_payload", None)
        self._pending_profile_payload = None
        if not payload:
            return
        from spock_shell.busy_ui import busy_scope, clear_override_cursors

        manager = self._ensure_server_manager()
        with busy_scope(self, "Loading configuration profile…"):
            apply_profile_payload(
                payload,
                self.config,
                save_config=lambda: save_config(self.config),
                parent=self,
                llama_manager=manager,
                on_theme=self._apply_profile_theme,
            )
        clear_override_cursors()
        QMessageBox.information(
            self,
            "Load profile",
            "Profile loaded. Settings restored; llama-servers were started only when needed.",
        )
        if self._center is not None:
            stamp = datetime.now().strftime("%H:%M:%S")
            self._center.append_launch(f"[{stamp}] Loaded configuration profile")

    def _apply_profile_theme(self, theme_name: str) -> None:
        if theme_name not in THEMES or theme_name == self.current_theme:
            return
        if getattr(self, "theme_combo", None) is not None:
            self.theme_combo.setCurrentText(theme_name)
        else:
            self.change_theme(theme_name)

    def _set_nav_enabled(self, enabled: bool) -> None:
        self._nav_enabled = enabled
        for btn in getattr(self, "_nav_buttons", []):
            btn.setEnabled(enabled)

    def _run_step(self, step_id: int) -> None:
        step = step_by_id(step_id)
        if step is None:
            return
        if not self._nav_enabled and step.kind != "exit":
            return
        if self._center is None:
            return

        if step.kind == "exit":
            self.close()
            return

        if step.kind == "panel":
            self._show_ask_ai()
            return

        # CLI / spawn steps use the progress center; restore it if Ask AI is showing.
        self.show_center(self._center)

        if step.kind == "spawn":
            self._spawn_step(step_id)
            return

        # cli
        if self._center.progress.is_running:
            QMessageBox.warning(
                self, "Busy", "A step is already running. Stop it first or wait."
            )
            return
        if step_id == 15 and not self._confirm_reembed():
            if self._center:
                self._center.append_launch(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    "Step 15 Re-embed skipped (user cancelled)"
                )
            return
        extra_args: List[str] = []
        if step_id == 3:
            extra_args = self._choose_acquire_models()
            if extra_args is None:
                return
        if step_id == 2:
            self._log_launch(
                "Phase B installs the full tier only (UI packages already present). "
                "If WinError 32 appears, close other Spock windows and re-run."
            )
        cmd = build_cli_command(step_id, self._root, extra_args)
        if not cmd:
            QMessageBox.warning(self, "Error", f"No command for step {step_id}")
            return

        # Step 14: also kill suite children we spawned
        if step_id == 14:
            self._reap_suite_children()
            self._center.append_launch(
                f"[{datetime.now().strftime('%H:%M:%S')}] Reaped suite child processes"
            )

        self._active_step_id = step_id
        self._center.mark_running(step_id)
        self._set_nav_enabled(False)
        ok = self._center.start_cli(title=step.label, command=cmd, cwd=self._root)
        if not ok:
            self._set_nav_enabled(True)
            self._center.mark_result(step_id, False)
            self._active_step_id = None

    def _choose_acquire_models(self) -> Optional[List[str]]:
        """Fit shortlist for step 3. ``None`` means the user cancelled."""
        try:
            from spock_bringup_menu.acquire_dialog import AcquireSelectDialog
            from spock_shell.paths import SHIP_COMPUTER_DB
        except Exception as e:
            self._log_launch(f"Fit shortlist unavailable ({e}); Acquire will match the recipe")
            return []
        dlg = AcquireSelectDialog(SHIP_COMPUTER_DB, self.theme, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            self._log_launch("Step 3 Acquire cancelled at model selection")
            return None
        args = dlg.cli_args()
        sel = dlg.result_selection or {}
        if dlg.recipe_updated:
            self._log_launch(dlg.recipe_updated)
        for role in ("embed", "chat"):
            pick = sel.get(role) or {}
            if pick:
                self._log_launch(
                    f"Acquire {role}: {pick.get('id')} "
                    f"{str(pick.get('fit_quant') or '').upper()} "
                    f"({pick.get('fit_level')} fit, ~{pick.get('need_gb')}GB, "
                    f"-c {pick.get('fit_n_ctx')})"
                )
        return args

    def _log_launch(self, message: str) -> None:
        if self._center is not None:
            stamp = datetime.now().strftime("%H:%M:%S")
            self._center.append_launch(f"[{stamp}] {message}")

    def _show_ask_ai(self) -> None:
        """In-app Ask AI / Deep Dive — same panel as Navigation Station step 8."""
        first_open = self._ask is None
        if first_open:
            from EngineeringDeck.ask_panel import AskAiPanel
            from WarpCore.search import hybrid_search
            from model_selector_core import merge_embedding_profile
            from spock_shell.bridge_host import make_llm_client

            self._ask = AskAiPanel(
                self.theme,
                get_llm=lambda: make_llm_client(self.config),
                hybrid_search_fn=hybrid_search,
                get_emb_url=lambda: merge_embedding_profile(
                    self.config.get("embedding_profile")
                ).get("embeddings_url", "http://localhost:8080/embeddings"),
                get_config=lambda: self.config,
            )
            self.stack.addWidget(self._ask)
        self.show_center(self._ask)
        if self._center is not None:
            self._center.mark_result(10, True)
            if first_open:
                stamp = datetime.now().strftime("%H:%M:%S")
                self._center.append_launch(
                    f"[{stamp}] OK  step 10  Ask AI / Deep Dive (in-app panel)"
                )
        self.statusBar().showMessage("Ask AI / Deep Dive", 3000)

    def _confirm_reembed(self) -> bool:
        """Two-step confirm before clearing document embeddings."""
        first = QMessageBox(self)
        first.setIcon(QMessageBox.Icon.Question)
        first.setWindowTitle("Re-embed / switch embedding model")
        first.setText("Clear existing embeddings and prepare for a new embedding GGUF?")
        first.setInformativeText(
            "This step nulls document vectors and clears kb_embedding_corpus.\n"
            "Documents, settings, and profiles are kept.\n\n"
            "Afterward you still need to:\n"
            "  • Launch the new embedding GGUF on :8080 (step 4 / Launch)\n"
            "  • Confirm Embedding Profile dim matches the model\n"
            "  • Run Wiki Scan (step 9) — re-queues every doc missing a vector\n\n"
            "Skip if you only meant to browse — this undoes prior embedding work."
        )
        skip_btn = first.addButton("Skip", QMessageBox.ButtonRole.RejectRole)
        go_btn = first.addButton("Re-embed", QMessageBox.ButtonRole.AcceptRole)
        first.setDefaultButton(skip_btn)
        first.exec()
        if first.clickedButton() is not go_btn:
            return False

        second = QMessageBox(self)
        second.setIcon(QMessageBox.Icon.Warning)
        second.setWindowTitle("Confirm: embeddings will be lost")
        second.setText("Prior embedding data will be permanently cleared.")
        second.setInformativeText(
            "All document.embedding values and the kb_embedding_corpus row "
            "will be removed from ship_computer.db.\n\n"
            "You cannot undo this without a database backup or a full Wiki Scan "
            "with the new model.\n\n"
            "Continue?"
        )
        cancel_btn = second.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        wipe_btn = second.addButton(
            "Yes, clear embeddings", QMessageBox.ButtonRole.DestructiveRole
        )
        second.setDefaultButton(cancel_btn)
        second.exec()
        return second.clickedButton() is wipe_btn

    def _on_cli_finished(self, code: int) -> None:
        sid = self._active_step_id
        self._active_step_id = None
        self._set_nav_enabled(True)
        if sid is None:
            return
        ok = code == 0
        self._center.mark_result(sid, ok) if self._center else None
        if sid == 4 and ok:
            self._ai_helper_unlocked = True
            self.statusBar().showMessage("AI Helper unlocked (servers up)", 5000)
        if sid == 5 and ok:
            ready = self._root / "spock_ready_last.json"
            if ready.is_file():
                self._center.append_launch(f"Wrote {ready}") if self._center else None
            if _servers_ready_from_json(self._root):
                self._ai_helper_unlocked = True

    def _spawn_step(self, step_id: int) -> None:
        step = step_by_id(step_id)
        cmd = build_spawn_command(step_id, self._root)
        if not step or not cmd:
            QMessageBox.warning(self, "Error", f"No spawn command for step {step_id}")
            return
        script_hint = Path(cmd[-1]).name if cmd else "?"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._root) + os.pathsep + env.get("PYTHONPATH", "")
        env["SPOCK_PROFILE_SESSION_LOADED"] = "1"
        try:
            proc = subprocess.Popen(cmd, cwd=str(self._root), env=env)
        except OSError as e:
            QMessageBox.warning(self, "Launch failed", str(e))
            if self._center:
                self._center.mark_result(step_id, False)
                self._center.append_launch(f"FAIL {script_hint} — {e}")
            return
        self._suite_procs.append(proc)
        if self._center:
            self._center.mark_result(step_id, True)
            stamp = datetime.now().strftime("%H:%M:%S")
            self._center.append_launch(
                f"[{stamp}] OK  step {step_id}  pid={proc.pid}  {' '.join(cmd[:3])}…"
            )

    def _reap_suite_children(self) -> None:
        still: List[subprocess.Popen] = []
        for proc in self._suite_procs:
            if proc.poll() is not None:
                continue
            _terminate_process_tree(proc.pid)
            if proc.poll() is None:
                still.append(proc)
        self._suite_procs = still
