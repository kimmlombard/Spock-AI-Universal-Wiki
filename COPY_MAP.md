# Copy map (HUB → Spock-Onboarding)

Source donor: `D:\Spock-UIE-Wiki-KB-HUB`

| Source | Dest | Status |
|--------|------|--------|
| `bootstrap.ps1` | `bootstrap.ps1` | Adapted (Onboarding root, PyQt6 deps, no suite acquire) |
| `bootstrap_phase_b_job.ps1` | `bootstrap_phase_b_job.ps1` | Adapted (no Bootstrap Wizard relaunch) |
| `Setup-Spock.bat` | `Spock-Menu.bat` | Replaced by menu entry |
| `spock_health_report.py` | `spock_onboarding/health.py` | Slimmed (llama probes + readiness helpers) |
| `llama_server_manager.py` | `spock_onboarding/llama_process.py` | Qt-free process core only |
| `spock_shell/llmfit_bridge.py` | `spock_onboarding/llmfit_bridge.py` | Adapted + `uvx llmfit` fallback |
| `first_models_wizard/runtime.py` | `spock_onboarding/runtime.py` | Headless detect/download llama-server |
| `first_models_wizard/pick.py` | `spock_onboarding/pick.py` | Lean catalog pick (no Qt / full hub scan deps) |
| `first_models_wizard/state.py` | `spock_onboarding/state.py` | Adapted summary → `first_models_last.json` |
| `install_spock.ps1` | — | **Dropped** (legacy) |
| `bootstrap_wizard/`, `*Wizard.py`, stations | — | **Dropped** (orphans / later UI) |
| `model_selector_panels.LlmStatusWindow` | `spock_live_monitor` | Stand-alone Live Monitor GUI |
| `spock_health_report` (Run Spock Status) | `spock_onboarding/spock_status.py` + `spock_status` CLI | Adapted headless report |
| `spock_scanner_core.get_live_monitor_snapshot` | `spock_onboarding/live_snapshot.py` | psutil + nvidia-smi |

New in this repo: `spock_bringup`, `spock_probe`, `spock_menu.ps1`, `spock_onboarding/readiness.py`, `spock_progress_log` (scrollable PyQt6 step log for menu 3–6, 8, Phase B).
