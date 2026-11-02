#!/usr/bin/env bash
# Console Spock Onboarding Menu (power users / recovery). Peer of Spock-Menu-Console.bat.
# Prefer ./Spock-Menu.sh for the PyQt6 bringup UI.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/spock_menu.sh" "$@"
