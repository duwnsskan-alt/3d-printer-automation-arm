#!/bin/bash
# =============================================================================
# run_sim.sh — One-button local launcher for Isaac Lab simulation
# =============================================================================
#
# Builds the Docker image (if needed), checks GPU prerequisites, and runs
# the Isaac Lab training or watch session inside the container.
#
# Usage:
#   ./run_sim.sh                                    # defaults: local profile, open_door task
#   ./run_sim.sh --task pick_print                  # train the pick-print task
#   ./run_sim.sh --task open_door --watch            # watch mode with VNC rendering
#   ./run_sim.sh --profile cloud --task open_door    # cloud profile (256 envs)
#
# Profiles:
#   local  — 16 envs, headless, for local GPU machines (default)
#   cloud  — 256 envs, headless, for cloud GPU instances
#
# Watch mode (--watch):
#   Starts VNC display stack inside container.
#   Access via browser: http://localhost:6080/vnc.html
#
# Requirements:
#   - Docker with nvidia-container-toolkit
#   - NVIDIA GPU with driver >= 525.60 (Isaac Sim requirement)
#   - Linux host (Isaac Lab does not support macOS GPU passthrough)
#
# =============================================================================

set -euo pipefail

# ─── Script location ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="${SCRIPT_DIR}/infra/docker"

# ─── Defaults ─────────────────────────────────────────────────────────────────
PROFILE="local"
TASK="open_door"
WATCH=false
LOAD_URDF=false
LOAD_SCENE=false
MAX_ITER=""
OVERRIDE_NUM_ENVS=""
IMAGE_NAME="printer-arm-isaacsim"
IMAGE_TAG="latest"
CONTAINER_NAME="printer-arm-sim"
OUTPUT_DIR="${SCRIPT_DIR}/output"

# ─── Parse arguments ─────────────────────────────────────────────────────────
print_usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Options:
  --profile <local|cloud>   Environment profile (default: local)
  --task <open_door|pick_print>  Task to run (default: open_door)
  --watch                   Enable VNC rendering (opens browser)
  --num-envs <N>            Override number of environments
  --max-iter <N>            Override max training iterations
  --load-urdf               Load SO-100 URDF viewer (watch mode, no RL)
  --load-scene              Load full scene: P2S printer + SO-100 arm (watch mode)
  --rebuild                 Force Docker image rebuild
  -h, --help                Show this help
EOF
}

REBUILD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)   PROFILE="$2"; shift 2 ;;
        --task)      TASK="$2"; shift 2 ;;
        --watch)     WATCH=true; shift ;;
        --load-urdf) LOAD_URDF=true; WATCH=true; shift ;;
        --load-scene) LOAD_SCENE=true; WATCH=true; shift ;;
        --num-envs)  OVERRIDE_NUM_ENVS="$2"; shift 2 ;;
        --max-iter)  MAX_ITER="$2"; shift 2 ;;
        --rebuild)   REBUILD=true; shift ;;
        -h|--help)   print_usage; exit 0 ;;
        *) echo "Unknown option: $1"; print_usage; exit 1 ;;
    esac
done

# ─── Resolve task → gym ID ───────────────────────────────────────────────────
case "${TASK}" in
    open_door)   GYM_ID="PrinterArm-OpenDoor-v0" ;;
    pick_print)  GYM_ID="PrinterArm-PickPrint-v0" ;;
    *)           echo "ERROR: Unknown task '${TASK}'. Use: open_door, pick_print"; exit 1 ;;
esac

# ─── Resolve profile → num_envs ──────────────────────────────────────────────
case "${PROFILE}" in
    local)  NUM_ENVS=16 ;;
    cloud)  NUM_ENVS=256 ;;
    *)      echo "ERROR: Unknown profile '${PROFILE}'. Use: local, cloud"; exit 1 ;;
esac

# Override if specified
if [ -n "${OVERRIDE_NUM_ENVS}" ]; then
    NUM_ENVS="${OVERRIDE_NUM_ENVS}"
fi

# Default max iterations based on task if not overridden
if [ -z "${MAX_ITER}" ]; then
    case "${TASK}" in
        open_door)   MAX_ITER=5000 ;;
        pick_print)  MAX_ITER=8000 ;;
    esac
fi

# ─── Prerequisite checks ─────────────────────────────────────────────────────
echo "==================================================================="
echo "  Printer Arm Isaac Lab Simulation"
echo "==================================================================="
echo "  Profile:   ${PROFILE} (${NUM_ENVS} envs)"
echo "  Task:      ${TASK} (${GYM_ID})"
echo "  Watch:     ${WATCH}"
echo "  Max iter:  ${MAX_ITER}"
echo "  Output:    ${OUTPUT_DIR}"
echo "==================================================================="
echo ""

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is not installed."
    echo "  Install: https://docs.docker.com/engine/install/"
    exit 1
fi

# Check NVIDIA driver
if ! command -v nvidia-smi &>/dev/null; then
    echo "ERROR: nvidia-smi not found. NVIDIA GPU driver is required."
    echo "  Isaac Lab requires NVIDIA GPU with driver >= 525.60"
    echo "  Note: macOS does not support NVIDIA GPU passthrough to Docker."
    exit 1
fi

echo "[1/4] GPU check..."
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
echo ""

# Check nvidia-container-toolkit
if ! docker info 2>/dev/null | grep -qi "nvidia"; then
    # Try the runtime directly
    if ! docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi &>/dev/null 2>&1; then
        echo "WARNING: nvidia-container-toolkit may not be installed."
        echo "  Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        echo "  Continuing anyway — Docker run will fail if GPU passthrough is broken."
        echo ""
    fi
fi

# ─── Build Docker image ──────────────────────────────────────────────────────
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

if [ "${REBUILD}" = true ] || ! docker image inspect "${FULL_IMAGE}" &>/dev/null; then
    echo "[2/4] Building Docker image: ${FULL_IMAGE}..."
    echo "  (First build pulls ~20GB Isaac Lab base image — this takes a while)"
    echo ""
    docker build \
        -t "${FULL_IMAGE}" \
        -f "${DOCKER_DIR}/Dockerfile" \
        "${DOCKER_DIR}"
    echo ""
    echo "  Image built successfully."
else
    echo "[2/4] Docker image exists: ${FULL_IMAGE} (use --rebuild to force)"
fi
echo ""

# ─── Prepare output directory ────────────────────────────────────────────────
echo "[3/4] Preparing output directory..."
mkdir -p "${OUTPUT_DIR}"/{checkpoints,logs,videos}

# ─── Run container ────────────────────────────────────────────────────────────
echo "[4/4] Starting container..."
echo ""

# Build docker run command
DOCKER_ARGS=(
    docker run
    --rm
    --name "${CONTAINER_NAME}"
    --runtime=nvidia
    -e NVIDIA_VISIBLE_DEVICES=all
    -e NVIDIA_DRIVER_CAPABILITIES=all
    --ipc=host
    --ulimit memlock=-1
    --ulimit stack=67108864
    # Mount project source
    -v "${SCRIPT_DIR}:/workspace/project:ro"
    # Mount output directory (read-write for checkpoints/logs)
    -v "${OUTPUT_DIR}:/workspace/output"
    # Environment variables
    -e "PROJECT_ROOT=/workspace/project"
    -e "OUTPUT_DIR=/workspace/output"
    -e "PYTHONPATH=/workspace/project"
)

# Install requirements if present inside container
if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
   echo "[3.5/4] Found requirements.txt. It will be installed inside the container."
fi

if [ "${LOAD_URDF}" = true ]; then
    # URDF viewer mode: load robot arm with VNC
    DOCKER_ARGS+=(
        -e "SIM_MODE=watch"
        -e "SIM_SCRIPT=/workspace/project/sim/isaac_lab/load_so100_standalone.py"
        -p 6080:6080      # noVNC web port
        -p 5900:5900      # VNC port (native VNC client)
    )
    SIM_ARGS=()

    echo "  URDF viewer mode: loading SO-100 robot arm."
    echo "  VNC: vncviewer localhost:5900"
    echo "  Web: http://localhost:6080/vnc.html"
    echo ""
elif [ "${LOAD_SCENE}" = true ]; then
    # Full scene mode: P2S printer + SO-100 arm with VNC
    DOCKER_ARGS+=(
        -e "SIM_MODE=watch"
        -e "SIM_SCRIPT=/workspace/project/sim/isaac_lab/load_scene_standalone.py"
        -p 6080:6080      # noVNC web port
        -p 5900:5900      # VNC port (native VNC client)
    )
    SIM_ARGS=()

    echo "  Scene viewer: P2S printer + SO-100 robot arm."
    echo "  VNC: vncviewer localhost:5900"
    echo "  Web: http://localhost:6080/vnc.html"
    echo ""
elif [ "${WATCH}" = true ]; then
    # Watch mode: VNC rendering enabled
    DOCKER_ARGS+=(
        -e "SIM_MODE=watch"
        -p 6080:6080      # noVNC web port
        -p 5900:5900      # VNC port (native VNC client)
    )
    SIM_ARGS=(
        --task "${GYM_ID}"
        --num_envs "${NUM_ENVS}"  # Respects --num-envs override (default from profile)
    )

    echo "  VNC rendering enabled."
    echo "  VNC: vncviewer localhost:5900"
    echo "  Web: http://localhost:6080/vnc.html"
    echo ""
else
    # Training mode: headless, maximum throughput
    DOCKER_ARGS+=(
        -e "SIM_MODE=train"
    )
    SIM_ARGS=(
        --task "${GYM_ID}"
        --num_envs "${NUM_ENVS}"
        --max_iterations "${MAX_ITER}"
        --log_dir "/workspace/output/logs"
        --checkpoint_dir "/workspace/output/checkpoints"
    )
fi

echo "  Container: ${CONTAINER_NAME}"
echo "  Image:     ${FULL_IMAGE}"
echo "  Command:   rsl_rl/train.py ${SIM_ARGS[*]}"
echo ""
echo "-------------------------------------------------------------------"
echo "  Press Ctrl+C to stop the simulation."
echo "-------------------------------------------------------------------"
echo ""

# Stop any existing container with the same name
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

exec "${DOCKER_ARGS[@]}" "${FULL_IMAGE}" "${SIM_ARGS[@]}"
