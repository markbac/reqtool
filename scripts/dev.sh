#!/usr/bin/env bash
# scripts/dev.sh
#
# Set up a local virtual environment and run reqtool without installing it
# system-wide. Idempotent -- safe to run multiple times.
#
# Usage:
#   ./scripts/dev.sh                  Start the API server (default)
#   ./scripts/dev.sh serve            Start the API server
#   ./scripts/dev.sh test             Run the full test suite
#   ./scripts/dev.sh test core        Run store + validation + CLI tests only
#   ./scripts/dev.sh test features    Run v0.3.0 feature tests only
#   ./scripts/dev.sh test api         Run API + regression tests only
#   ./scripts/dev.sh validate         Run req validate on the current directory
#   ./scripts/dev.sh verify           Run req verify on the current directory
#   ./scripts/dev.sh req <args>       Run any req subcommand
#   ./scripts/dev.sh shell            Drop into a shell with the venv active
#
# Environment variables:
#   REQTOOL_REPO    Path to the requirements repository root (default: cwd)
#   REQTOOL_PORT    Port for `serve` (default: 8765)
#   REQTOOL_HOST    Host for `serve` (default: 127.0.0.1)
#   PYTHON          Python interpreter to use (default: python3)

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve the repo root (directory containing this script's parent)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"

PYTHON="${PYTHON:-python3}"
PORT="${REQTOOL_PORT:-8765}"
HOST="${REQTOOL_HOST:-127.0.0.1}"

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
_green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
_yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
_red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
_bold()   { printf '\033[1m%s\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# Verify Python version
# ---------------------------------------------------------------------------
_check_python() {
    if ! command -v "$PYTHON" &>/dev/null; then
        _red "ERROR: '$PYTHON' not found. Install Python 3.11+ or set PYTHON=."
        exit 1
    fi
    local version
    version=$("$PYTHON" -c "import sys; print('%d.%d' % sys.version_info[:2])")
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [[ "$major" -lt 3 ]] || { [[ "$major" -eq 3 ]] && [[ "$minor" -lt 11 ]]; }; then
        _red "ERROR: Python 3.11+ required (found $version)."
        exit 1
    fi
    _green "Python $version OK"
}

# ---------------------------------------------------------------------------
# Create / update the virtual environment
# ---------------------------------------------------------------------------
_setup_venv() {
    if [[ ! -d "$VENV_DIR" ]]; then
        _yellow "Creating virtual environment at $VENV_DIR ..."
        "$PYTHON" -m venv "$VENV_DIR"
    fi

    # Activate
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    # Upgrade pip silently
    pip install --quiet --upgrade pip

    # Install the package in editable mode with test extras
    _yellow "Installing reqtool (editable) ..."
    pip install --quiet -e "$REPO_DIR[test]"

    _green "Environment ready."
}

# ---------------------------------------------------------------------------
# Ensure venv is active (create if needed)
# ---------------------------------------------------------------------------
_ensure_venv() {
    _check_python
    _setup_venv
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
cmd_install() {
    _check_python

    _bold "Step 1/3 -- Setting up Python virtual environment ..."
    _setup_venv

    _bold "Step 2/3 -- Building React UI ..."
    local ui_dir="$REPO_DIR/src/reqtool/ui"
    if ! command -v npm &>/dev/null; then
        _yellow "npm not found -- skipping UI build. Install Node.js 18+ to build the UI."
    else
        _yellow "Installing UI dependencies ..."
        npm --prefix "$ui_dir" install --legacy-peer-deps || {
            _red "npm install failed. Check Node.js version (18+ required)."
            exit 1
        }
        _yellow "Building UI ..."
        npm --prefix "$ui_dir" run build || {
            _red "npm run build failed."
            exit 1
        }
        _green "UI built: $ui_dir/dist"
    fi

    _bold "Step 3/3 -- Re-installing package (picks up new dist) ..."
    pip install --quiet -e "$REPO_DIR[test]"

    _green ""
    _green "Done. Run: ./scripts/dev.sh serve"
}

cmd_serve() {
    _ensure_venv
    _bold "Starting reqtool at http://$HOST:$PORT"
    echo "Repository: ${REQTOOL_REPO:-$(pwd)}"
    echo "Press Ctrl+C to stop."
    echo ""
    req serve \
        --host "$HOST" \
        --port "$PORT" \
        ${REQTOOL_REPO:+--repo "$REQTOOL_REPO"}
}

cmd_test() {
    _ensure_venv
    local subset="${1:-all}"
    cd "$REPO_DIR"

    case "$subset" in
        core)
            _bold "Running core tests (store, validation, CLI) ..."
            pytest tests/test_store.py tests/test_validation.py tests/test_cli.py \
                --timeout=30 -v --tb=short
            ;;
        features)
            _bold "Running v0.3.0 feature tests ..."
            pytest tests/test_features_v03.py \
                --timeout=30 -v --tb=short
            ;;
        api)
            _bold "Running API + regression tests ..."
            pytest tests/test_api.py tests/test_regression.py \
                --timeout=60 -v --tb=short
            ;;
        all|"")
            _bold "Running full test suite ..."
            pytest \
                tests/test_store.py \
                tests/test_validation.py \
                tests/test_cli.py \
                tests/test_features_v03.py \
                tests/test_api.py \
                tests/test_regression.py \
                --timeout=60 -v --tb=short
            ;;
        *)
            _red "Unknown test subset: $subset"
            _yellow "Valid subsets: core, features, api, all"
            exit 1
            ;;
    esac
}

cmd_validate() {
    _ensure_venv
    local repo="${REQTOOL_REPO:-$(pwd)}"
    _bold "Running req validate on $repo ..."
    req validate --repo "$repo"
}

cmd_verify() {
    _ensure_venv
    local repo="${REQTOOL_REPO:-$(pwd)}"
    _bold "Running req verify on $repo ..."
    req verify --repo "$repo"
}

cmd_req() {
    _ensure_venv
    req "$@"
}

cmd_shell() {
    _ensure_venv
    _green "Virtual environment activated. Type 'deactivate' to exit."
    exec bash --login
}

cmd_help() {
    cat <<EOF
$(_bold "reqtool dev script")

Usage: ./scripts/dev.sh [command] [options]

Commands:
  install           Build UI + install everything (run this first)
  serve             Start the API server (default)
  test [subset]     Run tests. Subsets: core | features | api | all (default: all)
  validate          Run req validate on the current repo
  verify            Run req verify on the current repo
  req <args>        Run any req subcommand
  shell             Drop into a shell with the venv active
  help              Show this help

Environment:
  REQTOOL_REPO      Requirements repository root (default: cwd)
  REQTOOL_PORT      Server port (default: 8765)
  REQTOOL_HOST      Server host (default: 127.0.0.1)
  PYTHON            Python interpreter (default: python3)

Examples:
  ./scripts/dev.sh
  ./scripts/dev.sh serve
  ./scripts/dev.sh test core
  ./scripts/dev.sh test features
  ./scripts/dev.sh req init agile --repo ~/my-reqs
  REQTOOL_REPO=~/my-reqs ./scripts/dev.sh serve
  REQTOOL_PORT=9000 ./scripts/dev.sh serve
EOF
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
COMMAND="${1:-serve}"
shift || true

case "$COMMAND" in
    install)   cmd_install     ;;
    serve)     cmd_serve       ;;
    test)      cmd_test "$@"   ;;
    validate)  cmd_validate    ;;
    verify)    cmd_verify      ;;
    req)       cmd_req "$@"    ;;
    shell)     cmd_shell       ;;
    help|--help|-h)  cmd_help  ;;
    *)
        _red "Unknown command: $COMMAND"
        echo ""
        cmd_help
        exit 1
        ;;
esac
