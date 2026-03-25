#!/bin/bash
# =============================================================================
# sim/local/run_local.sh — Local Isaac Lab launcher (no Docker)
# =============================================================================
#
# Prerequisites:
#   conda activate env_isaaclab
#
# Usage:
#   ./sim/local/run_local.sh train open_door              # Train OpenDoor (GUI)
#   ./sim/local/run_local.sh train open_door --headless    # Headless training
#   ./sim/local/run_local.sh view open_door                # View scene only
#   ./sim/local/run_local.sh train pick_print              # Train PickPrint
#
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Check conda env ─────────────────────────────────────────────────────────
if [[ "${CONDA_DEFAULT_ENV}" != "env_isaaclab" ]]; then
    echo "[ERROR] conda env 'env_isaaclab' not active."
    echo "  Run: conda activate env_isaaclab"
    exit 1
fi

# ── Parse args ──────────────────────────────────────────────────────────────
MODE="${1:-train}"
TASK="${2:-open_door}"
shift 2 2>/dev/null || true
EXTRA_ARGS="$@"

# Map task to script
case "${MODE}" in
    view)
        SCRIPT="${SCRIPT_DIR}/view_scene.py"
        TASK_ARG="--task ${TASK}"
        ;;
    train)
        case "${TASK}" in
            open_door)    SCRIPT="${SCRIPT_DIR}/train_open_door.py" ;;
            pick_print)   SCRIPT="${SCRIPT_DIR}/train_pick_print.py" ;;
            place_print)  SCRIPT="${SCRIPT_DIR}/train_place_print.py" ;;
            close_door)   SCRIPT="${SCRIPT_DIR}/train_close_door.py" ;;
            *)
                echo "[ERROR] Unknown task: ${TASK}"
                echo "Available: open_door, pick_print, place_print, close_door"
                exit 1
                ;;
        esac
        TASK_ARG=""
        ;;
    *)
        echo "[ERROR] Unknown mode: ${MODE}"
        echo "Usage: $0 {train|view} {open_door|pick_print} [extra args]"
        exit 1
        ;;
esac

# ── Launch ──────────────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Mode:    ${MODE}"
echo "  Task:    ${TASK}"
echo "  Project: ${PROJECT_ROOT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "${SCRIPT_DIR}"
python "${SCRIPT}" ${TASK_ARG} ${EXTRA_ARGS}
