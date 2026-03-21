#!/bin/bash
# Container entrypoint.
#
# Starts the full display stack, then runs Isaac Lab.
#
# SIM_MODE environment variable controls rendering:
#   train  — headless (no GUI overhead, fastest for RL training)
#   watch  — renders to Xvfb display; viewable via noVNC in browser
#
# Access via SSH tunnel:
#   ssh -L 6080:localhost:6080 -N ubuntu@<instance-ip>
#   then open: http://localhost:6080/vnc.html

set -e

DISPLAY_NUM=":1"
RESOLUTION="1920x1080"
VNC_PORT=5900
NOVNC_PORT=6080
MODE="${SIM_MODE:-watch}"
export PYTHONUNBUFFERED=1

echo "======================================================="
echo "  Isaac Sim Container — Mode: ${MODE}"
echo "  Virtual display: ${DISPLAY_NUM} @ ${RESOLUTION}"
echo "  noVNC: http://localhost:${NOVNC_PORT}/vnc.html"
echo "  (SSH tunnel required — see infra/scripts/connect_vnc.sh)"
echo "======================================================="
echo ""

# ── Step 1: Virtual display ────────────────────────────────────────────────────
echo "[1/4] Starting Xvfb virtual display ${DISPLAY_NUM}..."
Xvfb "${DISPLAY_NUM}" \
    -screen 0 "${RESOLUTION}x24" \
    +extension GLX \
    +render \
    -noreset &
XVFB_PID=$!
export DISPLAY="${DISPLAY_NUM}"
sleep 2
echo "      Xvfb ready (PID: ${XVFB_PID})"

# ── Step 2: Window manager ─────────────────────────────────────────────────────
echo "[2/4] Starting Openbox window manager..."
DISPLAY="${DISPLAY_NUM}" openbox &
sleep 1

# ── Step 3: VNC server ─────────────────────────────────────────────────────────
echo "[3/4] Starting x11vnc on port ${VNC_PORT}..."
x11vnc \
    -display "${DISPLAY_NUM}" \
    -nopw \
    -forever \
    -shared \
    -bg \
    -rfbport "${VNC_PORT}" \
    -o /tmp/x11vnc.log
sleep 1

# ── Step 4: noVNC web proxy ────────────────────────────────────────────────────
echo "[4/4] Starting noVNC web proxy on port ${NOVNC_PORT}..."
/opt/noVNC/utils/websockify/run \
    --web /opt/noVNC \
    "${NOVNC_PORT}" \
    "localhost:${VNC_PORT}" &
sleep 1

echo ""
echo "======================================================="
echo "  Display stack ready!"
echo "  1. Run locally: ./infra/scripts/connect_vnc.sh"
echo "  2. Open browser: http://localhost:6080/vnc.html"
echo "======================================================="
echo ""

# ── Install project requirements ──────────────────────────────────────────────
if [ -f /workspace/project/requirements.txt ]; then
    echo "Installing project requirements (best-effort)..."
    /workspace/isaaclab/_isaac_sim/python.sh -m pip install --quiet -r /workspace/project/requirements.txt 2>&1 || \
        echo "  WARNING: Some requirements failed to install (non-critical for simulation)."
    echo ""
fi

# GPU check
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
echo ""

# ── Isaac Lab ─────────────────────────────────────────────────────────────────
ISAAC_PYTHON="/workspace/isaaclab/_isaac_sim/python.sh"
TRAIN_SCRIPT="/workspace/isaaclab/scripts/reinforcement_learning/rsl_rl/train.py"
PLAY_SCRIPT="/workspace/isaaclab/scripts/reinforcement_learning/rsl_rl/play.py"

# SIM_SCRIPT overrides the default script (e.g. for standalone URDF loading)
SCRIPT="${SIM_SCRIPT:-}"

if [ -n "${SCRIPT}" ]; then
    echo "Starting custom script: ${SCRIPT} $*"
    exec ${ISAAC_PYTHON} "${SCRIPT}" "$@"
elif [ "${MODE}" = "train" ]; then
    echo "Starting Isaac Lab training: $*"
    exec ${ISAAC_PYTHON} ${TRAIN_SCRIPT} \
        --headless \
        "$@"
else
    echo "Starting Isaac Lab watch mode: $*"
    exec ${ISAAC_PYTHON} ${TRAIN_SCRIPT} \
        "$@"
fi
