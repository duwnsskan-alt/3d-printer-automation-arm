#!/bin/bash
# =============================================================================
# train_and_export.sh — End-to-end: Train → Export episodes → LeRobot format
# =============================================================================
#
# Runs ON the Vast.ai cloud instance (inside isaac-lab container).
# 1. Trains RL policy with Isaac Lab
# 2. Exports rollout episodes using trained checkpoint
# 3. Converts to LeRobot HuggingFace dataset format
#
# Usage:
#   ./infra/scripts/train_and_export.sh                               # defaults
#   ./infra/scripts/train_and_export.sh --task open_door --episodes 500
#   ./infra/scripts/train_and_export.sh --task pick_print --episodes 1000 --push
#
# Environment:
#   PROJECT_DIR   — project root (default: /workspace/project)
#   OUTPUT_DIR    — output root (default: /workspace/output)
#   HF_TOKEN      — HuggingFace token (required for --push)
#
# =============================================================================

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/workspace/project}"
OUTPUT_DIR="${OUTPUT_DIR:-/workspace/output}"

# ─── Defaults ────────────────────────────────────────────────────────────────
TASK="open_door"
NUM_ENVS=256
MAX_ITER=5000
EXPORT_EPISODES=500
PUSH_TO_HUB=false
HF_REPO="duwnsskan-alt/3d-printer-arm-dataset"

# ─── Parse arguments ────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --task)       TASK="$2"; shift 2 ;;
        --num-envs)   NUM_ENVS="$2"; shift 2 ;;
        --max-iter)   MAX_ITER="$2"; shift 2 ;;
        --episodes)   EXPORT_EPISODES="$2"; shift 2 ;;
        --push)       PUSH_TO_HUB=true; shift ;;
        --hf-repo)    HF_REPO="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--task open_door|pick_print] [--num-envs N] [--max-iter N]"
            echo "       [--episodes N] [--push] [--hf-repo REPO_ID]"
            exit 0 ;;
        *)            echo "Unknown: $1"; exit 1 ;;
    esac
done

# ─── Resolve task ────────────────────────────────────────────────────────────
case "${TASK}" in
    open_door)   GYM_ID="PrinterArm-OpenDoor-v0"; AGENT_CFG="sim.isaac_lab.agents.rsl_rl_cfg:OpenDoorPPOCfg" ;;
    pick_print)  GYM_ID="PrinterArm-PickPrint-v0"; AGENT_CFG="sim.isaac_lab.agents.rsl_rl_cfg:PickPrintPPOCfg" ;;
    *)           echo "ERROR: Unknown task '${TASK}'"; exit 1 ;;
esac

CKPT_DIR="${OUTPUT_DIR}/checkpoints/${TASK}"
LOG_DIR="${OUTPUT_DIR}/logs/${TASK}"
EPISODES_DIR="${OUTPUT_DIR}/episodes/${TASK}"
LEROBOT_DIR="${OUTPUT_DIR}/lerobot_dataset/${TASK}"

mkdir -p "${CKPT_DIR}" "${LOG_DIR}" "${EPISODES_DIR}" "${LEROBOT_DIR}"

echo "==================================================================="
echo "  Train & Export Pipeline"
echo "==================================================================="
echo "  Task:         ${TASK} (${GYM_ID})"
echo "  Num envs:     ${NUM_ENVS}"
echo "  Max iter:     ${MAX_ITER}"
echo "  Export:       ${EXPORT_EPISODES} episodes"
echo "  LeRobot dir:  ${LEROBOT_DIR}"
echo "  Push to Hub:  ${PUSH_TO_HUB} (${HF_REPO})"
echo "==================================================================="
echo ""

# ─── Wait for setup ─────────────────────────────────────────────────────────
if [ ! -f /opt/ready ]; then
    echo "[1/4] Waiting for onstart setup..."
    while [ ! -f /opt/ready ]; do sleep 5; done
fi

cd "${PROJECT_DIR}"
git pull --quiet 2>/dev/null || true

if [ -f requirements.txt ]; then
    pip install -q -r requirements.txt
fi

# ─── Step 1: Train ───────────────────────────────────────────────────────────
echo ""
echo "[1/4] Training: ${GYM_ID} with ${NUM_ENVS} envs, ${MAX_ITER} iterations..."
echo "  Start: $(date)"

python -m isaaclab.app.run \
    --headless \
    --task "${GYM_ID}" \
    --num_envs "${NUM_ENVS}" \
    --max_iterations "${MAX_ITER}" \
    --log_dir "${LOG_DIR}" \
    --checkpoint_dir "${CKPT_DIR}" \
    --agent_cfg "${AGENT_CFG}" \
    2>&1 | tee "${LOG_DIR}/train_stdout.log"

echo "  Done: $(date)"

# ─── Step 2: Find best checkpoint ───────────────────────────────────────────
echo ""
echo "[2/4] Locating latest checkpoint..."

LATEST_CKPT=$(ls -t "${CKPT_DIR}"/*.pt 2>/dev/null | head -1)
if [ -z "${LATEST_CKPT}" ]; then
    echo "ERROR: No checkpoint found in ${CKPT_DIR}"
    echo "Training may have failed. Check ${LOG_DIR}/train_stdout.log"
    exit 1
fi
echo "  Checkpoint: ${LATEST_CKPT}"

# ─── Step 3: Export episodes ─────────────────────────────────────────────────
echo ""
echo "[3/4] Exporting ${EXPORT_EPISODES} episodes from trained policy..."
echo "  Start: $(date)"

python sim/isaac_lab/export_dataset.py \
    --task "${GYM_ID}" \
    --checkpoint "${LATEST_CKPT}" \
    --num_episodes "${EXPORT_EPISODES}" \
    --output_dir "${EPISODES_DIR}" \
    2>&1 | tee "${LOG_DIR}/export_stdout.log"

echo "  Done: $(date)"
echo "  Episodes: $(ls "${EPISODES_DIR}"/episode_*.npz 2>/dev/null | wc -l) files"

# ─── Step 4: Convert to LeRobot format ───────────────────────────────────────
echo ""
echo "[4/4] Converting to LeRobot HuggingFace dataset format..."
echo "  Start: $(date)"

PUSH_FLAG=""
[ "${PUSH_TO_HUB}" = true ] && PUSH_FLAG="--push"

python -c "
import sys, json, logging
sys.path.insert(0, '${PROJECT_DIR}')
logging.basicConfig(level=logging.INFO)

from src.dataset.dataset_pipeline import DatasetPipeline

# Build config dict matching DatasetPipeline expectations
cfg = {
    'dataset': {
        'repo_id': '${HF_REPO}',
        'local_dir': '${LEROBOT_DIR}',
        'fps': 20,
        'episode_chunk_size': 100,
    }
}

pipeline = DatasetPipeline(cfg)
pipeline.merge_datasets(
    sim_dir='${EPISODES_DIR}',
    teleop_dir='${EPISODES_DIR}',   # same dir — teleop not available yet
    output_dir='${LEROBOT_DIR}',
)
print('LeRobot dataset created at ${LEROBOT_DIR}')

push = '${PUSH_TO_HUB}' == 'true'
if push:
    pipeline.push_to_hub('${LEROBOT_DIR}')
    print('Pushed to HuggingFace: ${HF_REPO}')
" 2>&1 | tee "${LOG_DIR}/convert_stdout.log"

echo "  Done: $(date)"

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "==================================================================="
echo "  Pipeline Complete!"
echo "==================================================================="
echo "  Checkpoint:    ${LATEST_CKPT}"
echo "  Episodes:      ${EPISODES_DIR}/ ($(ls "${EPISODES_DIR}"/episode_*.npz 2>/dev/null | wc -l) files)"
echo "  LeRobot data:  ${LEROBOT_DIR}/"
if [ "${PUSH_TO_HUB}" = true ]; then
echo "  HuggingFace:   https://huggingface.co/datasets/${HF_REPO}"
fi
echo ""
echo "  Download checkpoints:"
echo "    ./infra/scripts/sync_output.sh <host> <port>"
echo "==================================================================="
