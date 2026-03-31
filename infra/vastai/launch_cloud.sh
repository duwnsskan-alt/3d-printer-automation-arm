#!/bin/bash
# =============================================================================
# launch_cloud.sh — Deploy training to Vast.ai
# =============================================================================
#
# Searches for a GPU instance, creates it, and waits for training to start.
# Designed for Step 2 scale-up: 10k+ envs on multi-GPU instances.
#
# Usage:
#   ./infra/vastai/launch_cloud.sh                        # defaults
#   ./infra/vastai/launch_cloud.sh --task pick_print      # specific task
#   ./infra/vastai/launch_cloud.sh --gpus 4 --budget 2.00 # 4x GPU, $2/hr max
#   ./infra/vastai/launch_cloud.sh --dry-run              # search only, don't create
#
# Prerequisites:
#   pip install vastai
#   vastai set api-key <your-api-key>
#
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ─── Defaults ─────────────────────────────────────────────────────────────────
TASK="open_door"
NUM_GPUS=1
MAX_BUDGET="0.80"  # $/hr
DISK_GB=200
NUM_ENVS=256
MAX_ITER=5000
DRY_RUN=false
WATCH=false
GPU_TYPE=""         # a10g, a100, h100 — empty=any
EXPORT_EPISODES=0   # 0=skip export, >0=export N episodes after training

# ─── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --task)      TASK="$2"; shift 2 ;;
        --gpus)      NUM_GPUS="$2"; shift 2 ;;
        --budget)    MAX_BUDGET="$2"; shift 2 ;;
        --num-envs)  NUM_ENVS="$2"; shift 2 ;;
        --max-iter)  MAX_ITER="$2"; shift 2 ;;
        --disk)      DISK_GB="$2"; shift 2 ;;
        --watch)     WATCH=true; shift ;;
        --dry-run)   DRY_RUN=true; shift ;;
        --gpu-type)  GPU_TYPE="$2"; shift 2 ;;
        --export)    EXPORT_EPISODES="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--task open_door|pick_print] [--gpus N] [--budget X.XX]"
            echo "       [--num-envs N] [--max-iter N] [--disk GB] [--watch] [--dry-run]"
            echo "       [--gpu-type a10g|a100|h100] [--export NUM_EPISODES]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Resolve task
case "${TASK}" in
    open_door)   GYM_ID="PrinterArm-OpenDoor-v0"; AGENT_CFG="sim.isaac_lab.agents.rsl_rl_cfg:OpenDoorPPOCfg" ;;
    pick_print)  GYM_ID="PrinterArm-PickPrint-v0"; AGENT_CFG="sim.isaac_lab.agents.rsl_rl_cfg:PickPrintPPOCfg" ;;
    *)           echo "ERROR: Unknown task '${TASK}'"; exit 1 ;;
esac

# NUM_ENVS is the total count — Isaac Lab distributes across GPUs automatically
TOTAL_ENVS=${NUM_ENVS}

# ─── Check vastai CLI ────────────────────────────────────────────────────────
if ! command -v vastai &>/dev/null; then
    echo "Installing vastai CLI..."
    pip install --quiet vastai
fi

# Verify API key is set
if ! vastai show user &>/dev/null 2>&1; then
    echo "ERROR: Vast.ai API key not set."
    echo "  Run: vastai set api-key <your-api-key>"
    echo "  Get key from: https://cloud.vast.ai/account/"
    exit 1
fi

# ─── Search for instances ────────────────────────────────────────────────────
echo "==================================================================="
echo "  Vast.ai Cloud Training Launcher"
echo "==================================================================="
echo "  Task:       ${TASK} (${GYM_ID})"
echo "  GPUs:       ${NUM_GPUS} (${GPU_TYPE:-any})"
echo "  Envs:       ${TOTAL_ENVS} (distributed across ${NUM_GPUS} GPUs)"
echo "  Max iter:   ${MAX_ITER}"
echo "  Budget:     \$${MAX_BUDGET}/hr"
echo "  Disk:       ${DISK_GB} GB"
if [ "${EXPORT_EPISODES}" -gt 0 ]; then
echo "  Export:     ${EXPORT_EPISODES} episodes → LeRobot format"
fi
echo "==================================================================="
echo ""

# Build search query based on GPU count and type
MIN_VRAM=20  # GB, default
GPU_NAME_FILTER=""

case "${GPU_TYPE}" in
    a10g|A10G)   GPU_NAME_FILTER="gpu_name=A10G"; MIN_VRAM=20 ;;
    a100|A100)   GPU_NAME_FILTER="gpu_name=A100"; MIN_VRAM=40 ;;
    h100|H100)   GPU_NAME_FILTER="gpu_name=H100"; MIN_VRAM=40 ;;
    "")          # Auto: require higher VRAM for 4+ GPUs without explicit type
                 [ "${NUM_GPUS}" -ge 4 ] && MIN_VRAM=20 ;;
    *)           echo "ERROR: Unknown GPU type '${GPU_TYPE}'. Use: a10g, a100, h100"; exit 1 ;;
esac

GPU_QUERY="num_gpus>=${NUM_GPUS} gpu_ram>=${MIN_VRAM} rentable=True verified=True dph<${MAX_BUDGET} disk_space>${DISK_GB}"
[ -n "${GPU_NAME_FILTER}" ] && GPU_QUERY="${GPU_NAME_FILTER} ${GPU_QUERY}"

GPU_LABEL="${GPU_TYPE:-any}"
echo "Searching for ${NUM_GPUS}x GPU (${GPU_LABEL}, >=${MIN_VRAM}GB VRAM) under \$${MAX_BUDGET}/hr..."

echo ""
vastai search offers "${GPU_QUERY}" --order "dph asc" --limit 10
echo ""

if [ "${DRY_RUN}" = true ]; then
    echo "(Dry run — not creating instance)"
    echo ""
    echo "To launch manually:"
    echo "  vastai create instance <ID> \\"
    echo "    --image nvcr.io/nvidia/isaac-lab:2.3.2 \\"
    echo "    --disk ${DISK_GB} \\"
    echo "    --onstart-cmd \"\$(cat ${SCRIPT_DIR}/onstart.sh)\""
    exit 0
fi

# ─── Select best instance ────────────────────────────────────────────────────
echo "Selecting cheapest available instance..."
OFFER_ID=$(vastai search offers "${GPU_QUERY}" --order "dph asc" --limit 1 --raw 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data:
    print(data[0]['id'])
else:
    sys.exit(1)
" 2>/dev/null)

if [ -z "${OFFER_ID}" ]; then
    echo "ERROR: No instances found matching criteria."
    echo "  Try increasing --budget or reducing --gpus."
    exit 1
fi

echo "  Selected offer ID: ${OFFER_ID}"
echo ""

# ─── Build onstart command ───────────────────────────────────────────────────
# The onstart script sets up the environment, then delegates to train_and_export.sh.
# Task-specific parameters are passed via environment variables.
EXPORT_FLAG=""
[ "${EXPORT_EPISODES}" -gt 0 ] && EXPORT_FLAG="--episodes ${EXPORT_EPISODES}"

ONSTART_CMD=$(cat <<ONSTART_EOF
#!/bin/bash
set -e
exec >> /var/log/onstart.log 2>&1
echo "=== onstart started: \$(date) ==="

# VNC / display tools
apt-get update -qq
apt-get install -y --no-install-recommends xvfb x11vnc openbox xterm

# noVNC
git clone --depth=1 https://github.com/novnc/noVNC.git /opt/noVNC
git clone --depth=1 https://github.com/novnc/websockify.git /opt/noVNC/utils/websockify

# Project
git clone https://github.com/duwnsskan-alt/3d-printer-automation-arm.git /workspace/project

mkdir -p /workspace/output/{checkpoints,logs,episodes,lerobot_dataset}
chmod +x /workspace/project/infra/scripts/*.sh
chmod +x /workspace/project/infra/vastai/*.sh

# Set environment
export PROJECT_DIR=/workspace/project
export OUTPUT_DIR=/workspace/output
export PYTHONPATH=/workspace/project

# Install dependencies
cd /workspace/project
if [ -f requirements.txt ]; then
    pip install -q -r requirements.txt
fi

echo "=== onstart complete: \$(date) ==="
touch /opt/ready

# Launch train + export pipeline
/workspace/project/infra/scripts/train_and_export.sh \\
    --task ${TASK} \\
    --num-envs ${TOTAL_ENVS} \\
    --max-iter ${MAX_ITER} \\
    ${EXPORT_FLAG} \\
    >> /var/log/training.log 2>&1 &

echo "Pipeline started (PID: \$!)"
ONSTART_EOF
)

# ─── Create instance ─────────────────────────────────────────────────────────
echo "Creating instance..."
INSTANCE_ID=$(vastai create instance "${OFFER_ID}" \
    --image nvcr.io/nvidia/isaac-lab:2.3.2 \
    --disk "${DISK_GB}" \
    --onstart-cmd "${ONSTART_CMD}" \
    --raw 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('new_contract', ''))
" 2>/dev/null)

if [ -z "${INSTANCE_ID}" ]; then
    echo "ERROR: Failed to create instance. Check vastai CLI output."
    exit 1
fi

echo ""
echo "==================================================================="
echo "  Instance created!"
echo "==================================================================="
echo "  Instance ID:  ${INSTANCE_ID}"
echo "  Offer ID:     ${OFFER_ID}"
echo "  Task:         ${TASK}"
echo "  Envs:         ${TOTAL_ENVS}"
echo ""
echo "  Monitor:"
echo "    vastai show instance ${INSTANCE_ID}"
echo "    vastai logs ${INSTANCE_ID}"
echo ""
echo "  SSH + VNC:"
echo "    vastai ssh-url ${INSTANCE_ID}"
echo "    ./infra/scripts/connect_vnc.sh <host> <port>"
echo ""
echo "  Stop:"
echo "    vastai destroy instance ${INSTANCE_ID}"
echo ""
echo "  Download checkpoints:"
echo "    vastai copy ${INSTANCE_ID}:/workspace/output/ ./output/"
echo "==================================================================="
