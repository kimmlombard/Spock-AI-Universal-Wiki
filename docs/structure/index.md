# Code Structure

Machine-generated pages describing the *internal construct* of the codebase: module dependencies, call relationships, function/class inventory, entry points, and the live database schema. Generated from `ast` parsing and SQLite introspection — nothing in this section executes application code.

## Pages

- [Module Map](module-map.md) — internal import graph
- [Entry Points](entrypoints.md) — launch scripts and `__main__` guards
- [Root Scripts](root-scripts.md) — inventory of top-level scripts
- [Database Schema](database-schema.md) — live tables, columns, foreign keys
- [Logic Deep Dives](logic/index.md) — per-module walkthroughs

## Packages

[Orchestrator](Orchestrator/index.md) - [NavigationStation](NavigationStation/index.md) - [EngineeringDeck](EngineeringDeck/index.md) - [LongRangeSensors](LongRangeSensors/index.md) - [ScienceStation](ScienceStation/index.md) - [WarpCore](WarpCore/index.md) - [spock_onboarding](spock_onboarding/index.md) - [spock_bringup](spock_bringup/index.md) - [spock_bringup_menu](spock_bringup_menu/index.md) - [spock_shell](spock_shell/index.md) - [spock_rag_adapter](spock_rag_adapter/index.md) - [spock_mcp_adapter](spock_mcp_adapter/index.md) - [spock_wiki_adapter](spock_wiki_adapter/index.md) - [spock_live_monitor](spock_live_monitor/index.md) - [spock_status](spock_status/index.md) - [spock_probe](spock_probe/index.md) - [spock_progress_log](spock_progress_log/index.md) - [model_selector](model_selector/index.md) - [bootstrap_wizard](bootstrap_wizard/index.md)

## Totals

- **Indexed files:** 173
- **Classes:** 107
- **Functions:** 829
- **Methods:** 968
- **Lines inspected:** 49,555