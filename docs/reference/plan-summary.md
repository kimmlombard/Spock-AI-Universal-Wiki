# Plan Summary

## Current Status

Spock-Onboarding is in active development. Console bring-up, PyQt6 station UIs, RAG, MCP, and wiki indexing are complete on Windows; Linux support is in place. Apple Metal llama-server Acquire (macOS arm64/x64) is supported.

## Completed

- [x] Phase A bootstrap (`bootstrap.ps1`)
- [x] Python venv setup and dependency management
- [x] `spock_bringup` CLI (acquire/up/status/down)
- [x] `spock_probe` health verification
- [x] Readiness contract (`spock_ready_last.json`)
- [x] Ship's computer SQLite schema
- [x] `spock_shell` PyQt6 GUI skeleton
- [x] Full PyQt6 station UIs
- [x] RAG pipeline integration
- [x] MCP adapter tool registration
- [x] Wiki agent indexing
- [x] Linux

## Planned

- [ ] Multi-workstation profile sync
- [ ] Automated model selection
- [ ] Knowledge-base versioning
- [ ] Cloud backup integration
- [ ] Apple Metal
