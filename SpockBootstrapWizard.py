from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import _warpcore_path

_warpcore_path.ensure()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spock Bootstrap Control Wizard")
    parser.add_argument(
        "--install-root",
        default=str(_HERE),
        help="Install / repo root (default: this script's directory)",
    )
    parser.add_argument(
        "--show-result",
        default="",
        help="Path to bootstrap_phase_b_result.txt to show after a detached Phase B job",
    )
    args = parser.parse_args(argv)

    from PyQt6.QtWidgets import QMessageBox

    from bootstrap_wizard.window import BootstrapWizardWindow
    from spock_shell.qt_app import create_app

    app = create_app(sys.argv)
    app.setApplicationName("Spock Bootstrap Control")
    win = BootstrapWizardWindow(Path(args.install_root))
    win.show()

    result_path = (args.show_result or "").strip()
    if result_path:
        p = Path(result_path)
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                text = f"Could not read result file:\n{e}"
            panel = getattr(win, "_panel", None)
            if panel is not None and hasattr(panel, "_append_log"):
                panel._append_log("INFO", "==== Phase B job result ====")
                for line in text.splitlines()[-80:]:
                    panel._append_log("INFO", line)
                health = Path(args.install_root) / "bootstrap_health_last.txt"
                if health.is_file():
                    panel._append_log("INFO", f"==== Health report ({health}) ====")
                    try:
                        for line in health.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()[:60]:
                            panel._append_log("INFO", line)
                    except OSError:
                        pass
            summary = text[-2500:] if len(text) > 2500 else text
            ok = "PHASE_B_OK" in text
            if ok and panel is not None and hasattr(panel, "mark_full_deps_ok"):
                # HeavyDeps job succeeded — record for Science Station gates
                if "HeavyDeps=True" in text or "-HeavyDeps" in text:
                    panel.mark_full_deps_ok(source="phase_b_job")
                elif panel._probe_torch_installed():
                    panel.mark_full_deps_ok(source="phase_b_job_torch_probe")
            QMessageBox.information(
                win,
                "Phase B finished" if ok else "Phase B finished (see warnings)",
                (
                    "Full requirements / health job completed.\n"
                    "This window was reopened so you can review the summary.\n\n"
                    if ok
                    else "Phase B finished with warnings — check the log.\n\n"
                )
                + f"{summary[-1200:]}",
            )

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
