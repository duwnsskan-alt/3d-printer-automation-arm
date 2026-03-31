#!/bin/bash
# =============================================================================
# Vast.ai onstart script.
# =============================================================================
#
# Paste into "On-start script" field on vast.ai web UI, OR use launch_cloud.sh
# which inlines an extended version with task-specific parameters.
#
# Runs automatically inside the isaac-lab:2.3.2 container at startup.
# After setup, starts train_and_export.sh if TASK env var is set.
#
# Environment variables (set by launch_cloud.sh or manually):
#   TASK            — open_door | pick_print (default: open_door)
#   NUM_ENVS        — parallel environments (default: 256)
#   MAX_ITER        — training iterations (default: 5000)
#   EXPORT_EPISODES — episodes to export after training (default: 0 = skip)
#
# =============================================================================

set -e
exec >> /var/log/onstart.log 2>&1

echo "=== onstart started: $(date) ==="

# ── VNC / display tools ────────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y --no-install-recommends xvfb x11vnc openbox xterm

# noVNC
git clone --depth=1 https://github.com/novnc/noVNC.git /opt/noVNC
git clone --depth=1 https://github.com/novnc/websockify.git /opt/noVNC/utils/websockify

# ── Project ───────────────────────────────────────────────────────────────────
git clone https://github.com/duwnsskan-alt/3d-printer-automation-arm.git /workspace/project

mkdir -p /workspace/output/{checkpoints,logs,episodes,lerobot_dataset}

chmod +x /workspace/project/infra/scripts/*.sh
chmod +x /workspace/project/infra/vastai/*.sh

# Install Python dependencies
cd /workspace/project
if [ -f requirements.txt ]; then
    pip install -q -r requirements.txt
fi

echo "=== onstart complete: $(date) ==="
touch /opt/ready

# ── Auto-start pipeline if TASK is set ───────────────────────────────────────
TASK="${TASK:-}"
if [ -n "${TASK}" ]; then
    EXPORT_FLAG=""
    EXPORT_EPISODES="${EXPORT_EPISODES:-0}"
    [ "${EXPORT_EPISODES}" -gt 0 ] && EXPORT_FLAG="--episodes ${EXPORT_EPISODES}"

    echo "=== Starting train_and_export pipeline: ${TASK} ==="
    /workspace/project/infra/scripts/train_and_export.sh \
        --task "${TASK}" \
        --num-envs "${NUM_ENVS:-256}" \
        --max-iter "${MAX_ITER:-5000}" \
        ${EXPORT_FLAG} \
        >> /var/log/training.log 2>&1 &
    echo "Pipeline PID: $!"
fi
