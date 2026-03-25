#!/bin/bash
# Container entrypoint.
#
# Starts the full display stack, then runs Isaac Lab.
#
# SIM_MODE environment variable controls rendering:
#   train    — headless (no GUI overhead, fastest for RL training)
#   watch    — renders to Xvfb display; viewable via noVNC in browser
#   display  — renders directly on host monitor (X11 passthrough, local only)
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

if [ "${MODE}" = "display" ]; then
    # ── Direct display mode: use host X11, skip virtual display stack ────────
    echo "======================================================="
    echo "  Isaac Sim Container — Mode: display (X11 passthrough)"
    echo "  Rendering on host display: ${DISPLAY}"
    echo "======================================================="
    echo ""
else
    echo "======================================================="
    echo "  Isaac Sim Container — Mode: ${MODE}"
    echo "  Virtual display: ${DISPLAY_NUM} @ ${RESOLUTION}"
    echo "  noVNC: http://localhost:${NOVNC_PORT}/vnc.html"
    echo "  (SSH tunnel required — see infra/scripts/connect_vnc.sh)"
    echo "======================================================="
    echo ""

    # ── Step 1: Virtual display ──────────────────────────────────────────────
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

    # ── Step 2: Window manager ───────────────────────────────────────────────
    echo "[2/4] Starting Openbox window manager..."
    DISPLAY="${DISPLAY_NUM}" openbox &
    sleep 1

    # ── Step 3: VNC server ───────────────────────────────────────────────────
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

    # ── Step 4: noVNC web proxy ──────────────────────────────────────────────
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
fi

# ── Install simulation-only requirements ─────────────────────────────────────
# NOTE: Only install requirements_sim.txt (not requirements.txt) to avoid
# overwriting Isaac Sim's bundled PyTorch and breaking the simulation.
if [ -f /workspace/project/requirements_sim.txt ]; then
    echo "Installing simulation requirements..."
    /workspace/isaaclab/_isaac_sim/python.sh -m pip install --quiet -r /workspace/project/requirements_sim.txt 2>&1 || \
        echo "  WARNING: Some requirements failed to install (non-critical for simulation)."
    echo ""
fi

# ── Install printer_arm_tasks package (registers gym environments) ───────────
# Project is mounted read-only, so copy to a temp dir for pip install.
if [ -f /workspace/project/sim/isaac_lab/setup.py ]; then
    echo "Installing printer_arm_tasks package..."
    cp -r /workspace/project/sim/isaac_lab /tmp/_printer_arm_build
    /workspace/isaaclab/_isaac_sim/python.sh -m pip install --quiet --no-deps /tmp/_printer_arm_build 2>&1 || \
        echo "  WARNING: printer_arm_tasks installation failed."
    rm -rf /tmp/_printer_arm_build
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

# Patch isaaclab_tasks to also import printer_arm_tasks (registers custom gym envs).
# We append to __init__.py so it runs in the same process after SimulationApp starts.
ISAACLAB_TASKS_INIT="/workspace/isaaclab/source/isaaclab_tasks/isaaclab_tasks/__init__.py"
if ! grep -q "printer_arm_tasks" "${ISAACLAB_TASKS_INIT}" 2>/dev/null; then
    echo "Patching isaaclab_tasks to register printer_arm_tasks environments..."
    cat >> "${ISAACLAB_TASKS_INIT}" << 'PYEOF'

# Auto-import printer_arm_tasks to register custom gym environments
try:
    import printer_arm_tasks
except ImportError:
    pass
PYEOF
fi

if [ -n "${SCRIPT}" ]; then
    echo "Starting custom script: ${SCRIPT} $*"
    exec ${ISAAC_PYTHON} "${SCRIPT}" "$@"
elif [ "${MODE}" = "train" ]; then
    echo "Starting Isaac Lab training: $*"
    exec ${ISAAC_PYTHON} ${TRAIN_SCRIPT} \
        --headless \
        "$@"
elif [ "${MODE}" = "display" ]; then
    echo "Starting Isaac Lab (direct display): $*"
    exec ${ISAAC_PYTHON} ${TRAIN_SCRIPT} \
        "$@"
else
    echo "Starting Isaac Lab watch mode: $*"
    exec ${ISAAC_PYTHON} ${TRAIN_SCRIPT} \
        "$@"
fi
