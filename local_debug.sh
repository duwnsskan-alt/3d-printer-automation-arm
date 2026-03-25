#!/bin/bash
# =============================================================================
# local_debug.sh — Single-instance viewer for RTX 2070 / Local Dev
# =============================================================================
#
# Runs a single simulated environment (num_envs=1) with VNC visualization enabled.
# Optimized for local debugging on consumer GPUs (e.g., RTX 2070).
#
# Usage:
#   ./local_debug.sh [open_door|pick_print]
#
# Default task: open_door
#
# Output:
#   - Starts the simulation container with direct display rendering.
#   - Isaac Sim window appears on your monitor (no VNC needed).
#   - Very low resource usage compared to training.
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK="${1:-open_door}"

echo "==================================================================="
echo "  Local Debug Mode (Single Env, Direct Display)"
echo "==================================================================="
echo "  Task:      ${TASK}"
echo "  GPU:       Local (RTX 2070 Target)"
echo "  View:      Direct on host monitor"
echo "==================================================================="
echo ""

# Allow Docker containers to access host X11 display
xhost +local:docker 2>/dev/null || echo "WARNING: xhost not available, X11 forwarding may fail."

# Execute the existing run_sim.sh with override parameters
# --display: Renders directly on host monitor (X11 passthrough)
# --num-envs 1: Single environment for maximum performance/clarity
# --profile local: Uses local defaults as base

./run_sim.sh \
    --profile local \
    --task "${TASK}" \
    --display \
    --num-envs 1
