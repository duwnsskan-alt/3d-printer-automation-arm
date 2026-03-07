#!/bin/bash
# Runs ON the Vast.ai instance (inside isaac-lab:2.3.2 container).
# Starts display stack then runs Isaac Lab with rendering enabled.
#
# Workflow:
#   1. SSH into instance and run this script
#   2. On local machine: ./infra/scripts/connect_vnc.sh <host> <port>
#   3. Open browser: http://localhost:6080/vnc.html
#
# Usage:
#   ./infra/scripts/watch_sim.sh [task] [num_envs]

set -e

TASK="${1:-PrinterArm-OpenDoor-v0}"
NUM_ENVS="${2:-4}"   # Keep small — rendering N envs is GPU-heavy
PROJECT_DIR="${PROJECT_DIR:-/workspace/project}"

if [ ! -f /opt/ready ]; then
    echo "Waiting for onstart setup..."
    while [ ! -f /opt/ready ]; do sleep 5; done
fi

echo "==================================================="
echo "  Isaac Lab Watch Mode (with rendering)"
echo "  Task:     ${TASK}"
echo "  Num envs: ${NUM_ENVS}"
echo ""
echo "  FROM LOCAL: ./infra/scripts/connect_vnc.sh <host> <port>"
echo "  BROWSER:    http://localhost:6080/vnc.html"
echo "==================================================="

# ── Start display stack ────────────────────────────────────────────────────────
echo "Starting Xvfb..."
Xvfb :1 -screen 0 1920x1080x24 +extension GLX +render -noreset &
export DISPLAY=:1
sleep 2

echo "Starting window manager..."
openbox &
sleep 1

echo "Starting VNC server (port 5900)..."
x11vnc -display :1 -nopw -forever -shared -bg -rfbport 5900
sleep 1

echo "Starting noVNC (port 6080)..."
python3 /opt/noVNC/utils/websockify/run --web /opt/noVNC 6080 localhost:5900 &
sleep 1

# ── Run Isaac Lab ──────────────────────────────────────────────────────────────
cd "${PROJECT_DIR}" && git pull --quiet

python -m isaaclab.app.run \
    --task "${TASK}" \
    --num_envs "${NUM_ENVS}"
