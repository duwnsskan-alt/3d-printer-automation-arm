#!/bin/bash
# Runs ON the Vast.ai instance (inside isaac-lab:2.3.2 container).
# Headless training — no rendering, maximum environment throughput.
#
# Usage:
#   ./infra/scripts/launch_sim.sh [task] [num_envs] [max_iterations]

set -e

TASK="${1:-PrinterArm-OpenDoor-v0}"
NUM_ENVS="${2:-256}"
MAX_ITER="${3:-5000}"
PROJECT_DIR="${PROJECT_DIR:-/workspace/project}"
OUTPUT_DIR="${OUTPUT_DIR:-/workspace/output}"

# Wait for onstart to finish if still running
if [ ! -f /opt/ready ]; then
    echo "Waiting for onstart setup to complete..."
    while [ ! -f /opt/ready ]; do sleep 5; done
fi

echo "==================================================="
echo "  Isaac Lab Training (headless)"
echo "  Task:     ${TASK}"
echo "  Num envs: ${NUM_ENVS}"
echo "  Max iter: ${MAX_ITER}"
echo "==================================================="

mkdir -p "${OUTPUT_DIR}"/{checkpoints,logs}
cd "${PROJECT_DIR}" && git pull --quiet

python -m isaaclab.app.run \
    --headless \
    --task "${TASK}" \
    --num_envs "${NUM_ENVS}" \
    --max_iterations "${MAX_ITER}" \
    --log_dir "${OUTPUT_DIR}/logs" \
    --checkpoint_dir "${OUTPUT_DIR}/checkpoints"

echo "Training complete. Checkpoints at: ${OUTPUT_DIR}/checkpoints/"
