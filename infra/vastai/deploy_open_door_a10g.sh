#!/bin/bash
# =============================================================================
# deploy_open_door_a10g.sh — One-click: 4xA10G OpenDoor 500-episode pipeline
# =============================================================================
#
# Deploys to Vast.ai:
#   - 4x NVIDIA A10G GPUs
#   - 256 parallel environments
#   - OpenDoor task training (5000 iterations)
#   - Auto-exports 500 episodes to LeRobot format
#
# Usage:
#   ./infra/vastai/deploy_open_door_a10g.sh              # launch training
#   ./infra/vastai/deploy_open_door_a10g.sh --dry-run    # search only
#   ./infra/vastai/deploy_open_door_a10g.sh --push       # also push to HF Hub
#
# Prerequisites:
#   pip install vastai
#   vastai set api-key <your-api-key>
#
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Configuration for this deployment ───────────────────────────────────────
NUM_GPUS=4
GPU_TYPE="a10g"
NUM_ENVS=256
MAX_ITER=5000
EXPORT_EPISODES=500
TASK="open_door"
MAX_BUDGET="2.50"       # 4x A10G typical: ~$1.20-2.00/hr
DISK_GB=250             # extra space for episodes + LeRobot dataset
PUSH_TO_HUB=false

# Parse minimal overrides
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)   DRY_RUN="--dry-run"; shift ;;
        --push)      PUSH_TO_HUB=true; shift ;;
        --budget)    MAX_BUDGET="$2"; shift 2 ;;
        --max-iter)  MAX_ITER="$2"; shift 2 ;;
        --episodes)  EXPORT_EPISODES="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--push] [--budget X.XX] [--max-iter N] [--episodes N]"
            exit 0 ;;
        *)           echo "Unknown: $1"; exit 1 ;;
    esac
done

echo "============================================================"
echo "  OpenDoor Training — 4x A10G Deployment"
echo "============================================================"
echo ""
echo "  Config:"
echo "    GPU:          4x NVIDIA A10G (24GB each)"
echo "    Environments: ${NUM_ENVS} parallel"
echo "    Training:     ${MAX_ITER} PPO iterations"
echo "    Export:       ${EXPORT_EPISODES} episodes → LeRobot"
echo "    Budget:       ≤\$${MAX_BUDGET}/hr"
echo "    Push to Hub:  ${PUSH_TO_HUB}"
echo ""
echo "  Estimated cost:"
echo "    ~\$1.50/hr × ~2-3hr training = ~\$3-5 total"
echo "    + ~30min export = ~\$0.75"
echo "    Total estimate: ~\$4-6"
echo ""

# ─── Deploy via launch_cloud.sh ─────────────────────────────────────────────
exec "${SCRIPT_DIR}/launch_cloud.sh" \
    --task "${TASK}" \
    --gpus "${NUM_GPUS}" \
    --gpu-type "${GPU_TYPE}" \
    --num-envs "${NUM_ENVS}" \
    --max-iter "${MAX_ITER}" \
    --budget "${MAX_BUDGET}" \
    --disk "${DISK_GB}" \
    --export "${EXPORT_EPISODES}" \
    ${DRY_RUN:-}
