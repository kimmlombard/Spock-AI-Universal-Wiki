#!/usr/bin/env bash
# spock_menu.sh — console launcher for Spock on Linux / WSL / macOS
# Peer of spock_menu.ps1 (Bringup Menu steps 1–16).

set -uo pipefail

# Qt sizing: native Ubuntu defaults (1.0 / 96). Early WSL smoke tests used
# 1.25 / 144 — override only when WSLg/HiDPI text is still too small, e.g.:
#   QT_SCALE_FACTOR=1.25 QT_FONT_DPI=144 ./spock_menu.sh
# Scale: 1.0=100%, 1.25, 1.5, 2.  DPI: 96=100%, 120≈125%, 144=150%, 192=200%.
export QT_SCALE_FACTOR="${QT_SCALE_FACTOR:-1.0}"
export QT_FONT_DPI="${QT_FONT_DPI:-96}"
# WSLg: gio/xdg-open often fails for http:// — prefer Firefox (or set BROWSER=…)
if [[ "$(uname -s)" != "Darwin" ]]; then
  export BROWSER="${BROWSER:-firefox}"
fi

ROOT=""
if [[ $# -gt 0 && -n "${1:-}" && "${1:0:1}" != "-" ]]; then
  ROOT="$1"
  shift
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$ROOT" ]]; then
  ROOT="$SCRIPT_DIR"
fi
ROOT="$(cd "$ROOT" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

BOOTSTRAP="$ROOT/bootstrap.sh"
VENV_PY="$ROOT/.venv/bin/python"

c_cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_gray()  { printf '\033[90m%s\033[0m\n' "$*"; }

venv_python() {
  if [[ -x "$VENV_PY" ]]; then
    echo "$VENV_PY"
    return 0
  fi
  return 1
}

pyqt6_ready() {
  local py
  py="$(venv_python)" || return 1
  "$py" -c 'import PyQt6' >/dev/null 2>&1
}

show_header() {
  echo ""
  if [[ "$(uname -s)" == "Darwin" ]]; then
    c_cyan "=== Spock Onboarding Menu (console / macOS) ==="
  else
    c_cyan "=== Spock Onboarding Menu (console / Linux-WSL) ==="
  fi
  echo "Root: $ROOT"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "Tip: after Phase A, GUI apps use native Cocoa (./Spock-Menu.sh)."
  else
    echo "Tip: after Phase A, GUI apps use WSLg when DISPLAY is set."
  fi
  local py
  if py="$(venv_python)"; then
    c_green "venv: $py"
    if pyqt6_ready; then
      c_green "log UI: PyQt6 progress modal available"
    else
      c_yellow "log UI: console only (PyQt6 not importable yet)"
    fi
  else
    c_yellow "venv: (missing — run Phase A)"
  fi
  echo ""
}

show_menu() {
  cat <<'EOF'
1) Phase A - Python / venv / PyQt6 deps
2) Phase B - full deps (ingest / extractors / WebEngine)
3) Acquire runtime + models (llama-server + GGUFs)
4) Bring up servers (:8080 embed + :8081 chat)
5) Status / probe (write spock_ready_last.json)
6) MCP Adapter (stdio + HTTP tools for Cursor / llama.cpp)
7) Embedding Profile / RAG API
8) Open Live Monitor (Ship Status GUI)
9) Run Wiki Scan (wiki_agent.py + live log)
10) Ask AI / Deep Dive (Engineering Deck)
11) Spock Navigation Station (full left-nav GUI)
12) Spock Engineering Maintenance (wiki / DB console)
13) Spock UIEG KnowledgeBase (external capture)
14) Stop servers / kill all processes
15) Re-embed / switch embedding model (clear vectors, keep docs)
16) Exit

EOF
}

invoke_phase_a() {
  c_cyan "Running Phase A..."
  if [[ ! -f "$BOOTSTRAP" ]]; then
    c_red "Missing $BOOTSTRAP"
    return 1
  fi
  bash "$BOOTSTRAP" --phase-a --install-root "$ROOT"
  echo "Phase A exit: $?"
}

invoke_phase_b() {
  c_cyan "Running Phase B..."
  if [[ ! -f "$BOOTSTRAP" ]]; then
    c_red "Missing $BOOTSTRAP"
    return 1
  fi
  local py
  if py="$(venv_python)" && pyqt6_ready; then
    "$py" -m spock_progress_log --title "Phase B - full deps" --root "$ROOT" -- \
      bash "$BOOTSTRAP" --phase-b --install-root "$ROOT" || true
    echo "Phase B exit: $?"
    return 0
  fi
  bash "$BOOTSTRAP" --phase-b --install-root "$ROOT"
  echo "Phase B exit: $?"
}

invoke_python_module() {
  local title="$1"
  shift
  local py
  if ! py="$(venv_python)"; then
    c_red "No .venv — run Phase A first."
    return 2
  fi
  export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  if [[ -n "$title" ]] && pyqt6_ready; then
    c_cyan "Opening progress log: $title"
    "$py" -m spock_progress_log --title "$title" --root "$ROOT" -- \
      "$py" -u -m "$@"
    return $?
  fi
  c_gray "---- $title ----"
  "$py" -u -m "$@"
  local code=$?
  c_gray "---- exit: $code ----"
  return "$code"
}

invoke_suite_script() {
  local title="$1"
  shift
  local py
  if ! py="$(venv_python)"; then
    c_red "No .venv — run Phase A first."
    return 2
  fi
  if ! pyqt6_ready; then
    c_red "PyQt6 required — run Phase A first."
    return 2
  fi
  c_cyan "Opening $title (close the window to return here)..."
  export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  "$py" "$@"
  echo "$title exit: $?"
}

show_header
quit=0
while [[ "$quit" -eq 0 ]]; do
  show_menu
  read -r -p "Select: " choice || true
  choice="$(echo "${choice:-}" | tr -d '[:space:]')"
  case "$choice" in
    1) invoke_phase_a ;;
    2) invoke_phase_b ;;
    3)
      invoke_python_module "Acquire runtime + models" \
        spock_bringup --root "$ROOT" acquire || true
      ;;
    4)
      invoke_python_module "Bring up servers" \
        spock_bringup --root "$ROOT" up || true
      ;;
    5)
      invoke_python_module "Status / probe" \
        spock_bringup --root "$ROOT" status || true
      if [[ -f "$ROOT/spock_ready_last.json" ]]; then
        c_green "Wrote $ROOT/spock_ready_last.json"
      fi
      ;;
    6)
      invoke_suite_script "MCP Adapter" -m spock_mcp_adapter --root "$ROOT" || true
      ;;
    7)
      invoke_suite_script "Embedding / RAG" -m spock_rag_adapter --root "$ROOT" || true
      ;;
    8)
      invoke_suite_script "Live Monitor" -m spock_live_monitor --root "$ROOT" || true
      ;;
    9)
      invoke_suite_script "Wiki Scan" -m spock_wiki_adapter --root "$ROOT" || true
      ;;
    10)
      invoke_suite_script "Ask AI / Deep Dive" -m EngineeringDeck || true
      ;;
    11)
      invoke_suite_script "Navigation Station" "$ROOT/spock_navigation.py" || true
      ;;
    12)
      invoke_suite_script "Engineering Maintenance" "$ROOT/spock_maintenance.py" || true
      ;;
    13)
      invoke_suite_script "UIEG KnowledgeBase" "$ROOT/spock_UIEG_KnowledgeBase.py" || true
      ;;
    14)
      invoke_python_module "Stop servers" \
        spock_bringup --root "$ROOT" down || true
      ;;
    15)
      echo ""
      c_yellow "Re-embed clears document vectors and kb_embedding_corpus."
      c_yellow "Documents/settings are kept; prior embeddings will be lost."
      read -r -p "Type Re-embed to continue, or Skip: " c1 || true
      c1="$(echo "${c1:-}" | tr -d '[:space:]')"
      if [[ "$c1" != "Re-embed" && "$c1" != "re-embed" && "$c1" != "RE-EMBED" ]]; then
        c_gray "Skipped."
      else
        read -r -p "Confirm: prior embedding data will be lost. Type YES: " c2 || true
        c2="$(echo "${c2:-}" | tr -d '[:space:]')"
        if [[ "$c2" != "YES" ]]; then
          c_gray "Cancelled."
        else
          invoke_python_module "Re-embed / clear embeddings" \
            spock_bringup --root "$ROOT" reembed --yes || true
        fi
      fi
      ;;
    16|q|Q)
      quit=1
      ;;
    *)
      c_yellow "Unknown choice."
      ;;
  esac
  if [[ "$quit" -eq 0 ]]; then
    echo ""
  fi
done

echo "Bye."
