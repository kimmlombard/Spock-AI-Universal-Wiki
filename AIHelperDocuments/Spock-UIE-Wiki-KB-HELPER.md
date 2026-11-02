# Spock-UIE-Wiki-KB — lite orchestrator HELPER

Launch via `Spock.bat` / `spock.ps1` / `python main.py`.

## Left Navigation
- **Home** — this helper / overview
- **spock_navigation** — Navigation Station (wiki scan, configure, launch)
- **spock_uieg** — UIEG KnowledgeBase (Long Range Sensors)
- **spock_maintenance** — Engineering Maintenance (DB, settings, ship health)
- **Launch log** — processes started from this hub
- **Exit**

Onboarding wizard and First Models are intentionally omitted from this lite hub
(use `spock_menu.ps1` / bringup if you still need them).

## Profile dialogs
This hub does **not** prompt to load or save configuration profiles on open/close.
Each mini-app (Navigation, etc.) prompts for its own profile load when it starts,
same as launching it from its stand-alone `.bat`.
