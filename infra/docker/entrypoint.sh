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
python3 /opt/noVNC/utils/websockify/run \
    --web /opt/noVNC \
    "${NOVNC_PORT}" \
    "localhost:${VNC_PORT}" &
sleep 1

# ── Step 5 (optional): Nginx CORS proxy for Cloudflare Tunnel ────────────────
if [ "${ENABLE_TUNNEL:-0}" = "1" ]; then
    echo "[5/5] Starting nginx CORS proxy on port 6090..."
    nginx
    echo "      nginx ready — Cloudflare Tunnel can connect to :6090"
fi

echo ""
echo "======================================================="
echo "  Display stack ready!"
if [ "${ENABLE_TUNNEL:-0}" = "1" ]; then
    echo "  Tunnel mode: nginx CORS proxy on :6090"
    echo "  Run cloudflared to expose via tunnel"
else
    echo "  1. Run locally: ./infra/scripts/connect_vnc.sh"
    echo "  2. Open browser: http://localhost:6080/vnc.html"
fi
echo "======================================================="
echo ""

# ── Install project requirements ──────────────────────────────────────────────
if [ -f /workspace/project/requirements.txt ]; then
    echo "Installing project requirements..."
    pip install --quiet -r /workspace/project/requirements.txt
    echo "  Requirements installed."
    echo ""
fi

# GPU check
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
echo ""

# ── Isaac Lab ─────────────────────────────────────────────────────────────────
echo "Starting Isaac Lab: mode=${MODE}, args: $*"

if [ "${MODE}" = "train" ]; then
    # Headless training — no rendering overhead, maximum environment throughput
    exec python -m isaaclab.app.run \
        --headless \
        "$@"
else
    # Watch mode — renders to Xvfb; visible in noVNC browser tab
    # Uses fewer environments by default (set --num_envs on the command line)
    exec python -m isaaclab.app.run \
        "$@"
fi
