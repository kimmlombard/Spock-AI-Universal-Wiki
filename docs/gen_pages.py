"""Auto-generate API reference pages for the Spock-Onboarding packages."""

from pathlib import Path

import mkdocs_gen_files

PACKAGES = [
    "Orchestrator",
    "NavigationStation",
    "EngineeringDeck",
    "LongRangeSensors",
    "ScienceStation",
    "WarpCore",
    "spock_onboarding",
    "spock_bringup",
    "spock_shell",
    "spock_rag_adapter",
    "spock_mcp_adapter",
]

if __name__ in ("__main__", "<run_path>"):  # direct run, or mkdocs-gen-files runpy
    for package in PACKAGES:
        path = Path(f"reference/{package}/index.md")
        with mkdocs_gen_files.open(path, "w") as fd:
            fd.write(f"# {package}\n\n")
            fd.write(f"::: {package}\n")
        mkdocs_gen_files.set_edit_path(path, Path(f"../{package}/__init__.py"))