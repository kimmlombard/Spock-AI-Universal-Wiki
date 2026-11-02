# Module Map

Import relationships between every indexed module. Edges point from the importing module to the module it imports. Only **project-internal** edges are shown; stdlib / third-party imports are skipped.

**Indexed:** 173 files · **Internal imports:** 0

 title: "Project module imports"

```mermaid
flowchart LR
   
    m0["EngineeringDeck/__main__.py"]
    m1["EngineeringDeck/maintenance_app.py"]
    m2["LongRangeSensors/uieg_maintenance.py"]
    m3["db_maintenance.py"]
    m4["helper_main.py"]
    m5["main.py"]
    m6["spock_bringup/__main__.py"]
    m7["spock_bringup_menu/__main__.py"]
    m8["spock_live_monitor/__main__.py"]
    m9["spock_maintenance.py"]
    m10["spock_mcp_adapter/__main__.py"]
    m11["spock_probe/__main__.py"]
    m12["spock_progress_log/__main__.py"]
    m13["spock_rag_adapter/__main__.py"]
    m14["spock_shell/__main__.py"]
    m15["spock_status/__main__.py"]
    m16["spock_wiki_adapter/__main__.py"]
    m17["wiki_maintenance.py"]
```

## Import Details (text)

| Module                                      | Imports (project-internal) |
| ------------------------------------------- | -------------------------- |
| `EngineeringDeck/__init__.py`               | _none_                     |
| `EngineeringDeck/__main__.py`               | _none_                     |
| `EngineeringDeck/app.py`                    | _none_                     |
| `EngineeringDeck/ask_panel.py`              | _none_                     |
| `EngineeringDeck/maintenance_app.py`        | _none_                     |
| `EngineeringDeck/ship_computer_health.py`   | _none_                     |
| `LongRangeSensors/__init__.py`              | _none_                     |
| `LongRangeSensors/app.py`                   | _none_                     |
| `LongRangeSensors/external_search_panel.py` | _none_                     |
| `LongRangeSensors/uieg_capture_panel.py`    | _none_                     |
| `LongRangeSensors/uieg_crawler.py`          | _none_                     |
| `LongRangeSensors/uieg_database.py`         | _none_                     |
| `LongRangeSensors/uieg_import.py`           | _none_                     |
| `LongRangeSensors/uieg_maintenance.py`      | _none_                     |
| `LongRangeSensors/uieg_paths.py`            | _none_                     |
| `LongRangeSensors/uieg_preview.py`          | _none_                     |
| `LongRangeSensors/uieg_promote.py`          | _none_                     |
| `LongRangeSensors/uieg_repo_fetch.py`       | _none_                     |
| `LongRangeSensors/uieg_status.py`           | _none_                     |
| `LongRangeSensors/web_search_clients.py`    | _none_                     |
| `NavigationStation/__init__.py`             | _none_                     |
| `NavigationStation/app.py`                  | _none_                     |
| `NavigationStation/steps/__init__.py`       | _none_                     |
| `NavigationStation/steps/configure.py`      | _none_                     |
| `NavigationStation/steps/hardware.py`       | _none_                     |
| `NavigationStation/steps/launch.py`         | _none_                     |
| `NavigationStation/steps/status.py`         | _none_                     |
| `Orchestrator/__init__.py`                  | _none_                     |
| `Orchestrator/app.py`                       | _none_                     |
| `ScienceStation/__init__.py`                | _none_                     |
| `ScienceStation/app.py`                     | _none_                     |
| `ScienceStation/ships_logs.py`              | _none_                     |
| `ScienceStation/wiki_run.py`                | _none_                     |
| `Spock-UIE-Wiki-KB.py`                      | _none_                     |
| `SpockBootstrapWizard.py`                   | _none_                     |
| `WarpCore/__init__.py`                      | _none_                     |
| `WarpCore/ask_timing_store.py`              | _none_                     |
| `WarpCore/config_defaults.py`               | _none_                     |
| `WarpCore/db.py`                            | _none_                     |
| `WarpCore/deps.py`                          | _none_                     |
| `WarpCore/host_recipe.py`                   | _none_                     |
| `WarpCore/preview.py`                       | _none_                     |
| `WarpCore/profile_store.py`                 | _none_                     |
| `WarpCore/search.py`                        | _none_                     |
| `WarpCore/secrets.py`                       | _none_                     |
| `WarpCore/service_endpoints.py`             | _none_                     |
| `WarpCore/settings_store.py`                | _none_                     |
| `WarpCore/ship_schema.py`                   | _none_                     |
| `WarpCore/skills.py`                        | _none_                     |
| `WarpCore/theme.py`                         | _none_                     |
| `_start_rag_api.py`                         | _none_                     |
| `bootstrap_wizard/__init__.py`              | _none_                     |
| `bootstrap_wizard/panel.py`                 | _none_                     |
| `bootstrap_wizard/steps.py`                 | _none_                     |
| `bootstrap_wizard/window.py`                | _none_                     |
| `bootstrap_wizard/worker.py`                | _none_                     |
| `chat_ai_helper.py`                         | _none_                     |
| `db_browser.py`                             | _none_                     |
| `db_maintenance.py`                         | _none_                     |
| `deep_dive.py`                              | _none_                     |
| `docs_server.py`                            | _none_                     |
| `enhance_docs.py`                           | _none_                     |
| `gemini_openai_models.py`                   | _none_                     |
| `helper_main.py`                            | _none_                     |
| `llama_server_manager.py`                   | _none_                     |
| `llm_client.py`                             | _none_                     |
| `lm_studio_api.py`                          | _none_                     |
| `main.py`                                   | _none_                     |
| `mcp_panel.py`                              | _none_                     |
| `model_pick_policy.py`                      | _none_                     |
| `model_selector/__init__.py`                | _none_                     |
| `model_selector/embedding_panel.py`         | _none_                     |
| `model_selector/hardware_panel.py`          | _none_                     |
| `model_selector/launch_panel.py`            | _none_                     |
| `model_selector/model_card.py`              | _none_                     |
| `model_selector/models_panel.py`            | _none_                     |
| `model_selector/state.py`                   | _none_                     |
| `model_selector/status_window.py`           | _none_                     |
| `model_selector/widgets.py`                 | _none_                     |
| `model_selector/workers.py`                 | _none_                     |
| `model_selector_core.py`                    | _none_                     |
| `model_selector_panels.py`                  | _none_                     |
| `rag_api_server.py`                         | _none_                     |
| `reset.py`                                  | _none_                     |
| `reset_ship_computer.py`                    | _none_                     |
| `reset_uieg.py`                             | _none_                     |
| `spock_UIEG_KnowledgeBase.py`               | _none_                     |
| `spock_bringup/__init__.py`                 | _none_                     |
| `spock_bringup/__main__.py`                 | _none_                     |
| `spock_bringup_menu/__init__.py`            | _none_                     |
| `spock_bringup_menu/__main__.py`            | _none_                     |
| `spock_bringup_menu/acquire_dialog.py`      | _none_                     |
| `spock_bringup_menu/app.py`                 | _none_                     |
| `spock_bringup_menu/center_log.py`          | _none_                     |
| `spock_bringup_menu/steps.py`               | _none_                     |
| `spock_health_report.py`                    | _none_                     |
| `spock_live_monitor.py`                     | _none_                     |
| `spock_live_monitor/__init__.py`            | _none_                     |
| `spock_live_monitor/__main__.py`            | _none_                     |
| `spock_maintenance.py`                      | _none_                     |
| `spock_mcp_adapter/__init__.py`             | _none_                     |
| `spock_mcp_adapter/__main__.py`             | _none_                     |
| `spock_mcp_adapter/mcp_host.py`             | _none_                     |
| `spock_mcp_adapter/mcp_panel.py`            | _none_                     |
| `spock_mcp_adapter/paths.py`                | _none_                     |
| `spock_mcp_adapter/proc_guard.py`           | _none_                     |
| `spock_navigation.py`                       | _none_                     |
| `spock_onboarding/__init__.py`              | _none_                     |
| `spock_onboarding/fit_select.py`            | _none_                     |
| `spock_onboarding/health.py`                | _none_                     |
| `spock_onboarding/live_snapshot.py`         | _none_                     |
| `spock_onboarding/llama_process.py`         | _none_                     |
| `spock_onboarding/llmfit_bridge.py`         | _none_                     |
| `spock_onboarding/pick.py`                  | _none_                     |
| `spock_onboarding/readiness.py`             | _none_                     |
| `spock_onboarding/runtime.py`               | _none_                     |
| `spock_onboarding/spock_status.py`          | _none_                     |
| `spock_onboarding/state.py`                 | _none_                     |
| `spock_probe/__init__.py`                   | _none_                     |
| `spock_probe/__main__.py`                   | _none_                     |
| `spock_profile_store.py`                    | _none_                     |
| `spock_progress_log/__init__.py`            | _none_                     |
| `spock_progress_log/__main__.py`            | _none_                     |
| `spock_progress_log/panel.py`               | _none_                     |
| `spock_rag_adapter/__init__.py`             | _none_                     |
| `spock_rag_adapter/__main__.py`             | _none_                     |
| `spock_rag_adapter/bridge_host.py`          | _none_                     |
| `spock_rag_adapter/embedding_corpus.py`     | _none_                     |
| `spock_rag_adapter/embedding_panel.py`      | _none_                     |
| `spock_rag_adapter/embedding_utils.py`      | _none_                     |
| `spock_rag_adapter/paths.py`                | _none_                     |
| `spock_rag_adapter/rag_host.py`             | _none_                     |
| `spock_rag_adapter/reembed.py`              | _none_                     |
| `spock_scanner_core.py`                     | _none_                     |
| `spock_shell/__init__.py`                   | _none_                     |
| `spock_shell/__main__.py`                   | _none_                     |
| `spock_shell/about.py`                      | _none_                     |
| `spock_shell/ai_helper.py`                  | _none_                     |
| `spock_shell/ask_path_handoff.py`           | _none_                     |
| `spock_shell/brave_search.py`               | _none_                     |
| `spock_shell/bridge_host.py`                | _none_                     |
| `spock_shell/busy_ui.py`                    | _none_                     |
| `spock_shell/config.py`                     | _none_                     |
| `spock_shell/configure_ai.py`               | _none_                     |
| `spock_shell/embedding_corpus.py`           | _none_                     |
| `spock_shell/good_results_coach.py`         | _none_                     |
| `spock_shell/llmfit_bridge.py`              | _none_                     |
| `spock_shell/markdown_home.py`              | _none_                     |
| `spock_shell/mcp_host.py`                   | _none_                     |
| `spock_shell/mcp_tunnel.py`                 | _none_                     |
| `spock_shell/paths.py`                      | _none_                     |
| `spock_shell/proc_guard.py`                 | _none_                     |
| `spock_shell/process_tree.py`               | _none_                     |
| `spock_shell/profiles.py`                   | _none_                     |
| `spock_shell/qt_app.py`                     | _none_                     |
| `spock_shell/rag_host.py`                   | _none_                     |
| `spock_shell/status_panel.py`               | _none_                     |
| `spock_shell/theme.py`                      | _none_                     |
| `spock_shell/widgets.py`                    | _none_                     |
| `spock_shell/win_job.py`                    | _none_                     |
| `spock_shell/window.py`                     | _none_                     |
| `spock_status/__init__.py`                  | _none_                     |
| `spock_status/__main__.py`                  | _none_                     |
| `spock_uieg.py`                             | _none_                     |
| `spock_wiki_adapter/__init__.py`            | _none_                     |
| `spock_wiki_adapter/__main__.py`            | _none_                     |
| `spock_wiki_adapter/paths.py`               | _none_                     |
| `spock_wiki_adapter/scan_roots.py`          | _none_                     |
| `spock_wiki_adapter/wiki_run.py`            | _none_                     |
| `starfleet_universal_extractor.py`          | _none_                     |
| `wiki_agent.py`                             | _none_                     |
| `wiki_agent_status.py`                      | _none_                     |
| `wiki_maintenance.py`                       | _none_                     |
