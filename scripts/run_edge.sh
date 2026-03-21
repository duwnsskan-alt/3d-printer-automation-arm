#!/bin/bash
# ============================================================
# run_edge.sh - Run the edge automation system
# ============================================================
# Usage:
#   bash scripts/run_edge.sh                  # Full system
#   bash scripts/run_edge.sh --dry-run        # Validate only
#   bash scripts/run_edge.sh --no-robot       # Dev mode
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
VENV_DIR="${PROJECT_DIR}/.venv"

# Activate virtual environment
if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[ERROR] Virtual environment not found. Run: bash scripts/setup_edge.sh"
    exit 1
fi
source "${VENV_DIR}/bin/activate"

# Load .env if present
if [[ -f "${PROJECT_DIR}/config/.env" ]]; then
    set -a
    source "${PROJECT_DIR}/config/.env"
    set +a
fi

# Run main entry point with all passed arguments
exec python "${PROJECT_DIR}/main.py" "$@"
