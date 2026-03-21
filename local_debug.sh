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
#   - Starts the simulation container in watch mode.
#   - Opens a VNC stream on http://localhost:6080/vnc.html
#   - Very low resource usage compared to training.
#
# =============================================================================

set -e

TASK="${1:-open_door}"

echo "==================================================================="
echo "  Local Debug Mode (Single Env)"
echo "==================================================================="
echo "  Task:      ${TASK}"
echo "  GPU:       Local (RTX 2070 Target)"
echo "  View:      http://localhost:6080/vnc.html"
echo "==================================================================="
echo ""

# Execute the existing run_sim.sh with override parameters
# --watch: Enables VNC
# --num-envs 1: Single environment for maximum performance/clarity
# --profile local: Uses local defaults as base

./run_sim.sh \
    --profile local \
    --task "${TASK}" \
    --watch \
    --num-envs 1
