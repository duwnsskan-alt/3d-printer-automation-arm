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
        -h|--help)
            echo "Usage: $0 [--task open_door|pick_print] [--gpus N] [--budget X.XX]"
            echo "       [--num-envs N] [--max-iter N] [--disk GB] [--watch] [--dry-run]"
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

# Scale envs with GPU count for multi-GPU runs
TOTAL_ENVS=$((NUM_ENVS * NUM_GPUS))

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
echo "  GPUs:       ${NUM_GPUS}"
echo "  Envs:       ${TOTAL_ENVS} (${NUM_ENVS} per GPU x ${NUM_GPUS})"
echo "  Max iter:   ${MAX_ITER}"
echo "  Budget:     \$${MAX_BUDGET}/hr"
echo "  Disk:       ${DISK_GB} GB"
echo "==================================================================="
echo ""

# Build search query based on GPU count
if [ "${NUM_GPUS}" -ge 4 ]; then
    # Multi-GPU: look for A100 or H100
    GPU_QUERY="num_gpus>=${NUM_GPUS} gpu_ram>=40 rentable=True verified=True dph<${MAX_BUDGET} disk_space>${DISK_GB}"
    echo "Searching for ${NUM_GPUS}+ GPU instances (A100/H100) under \$${MAX_BUDGET}/hr..."
elif [ "${NUM_GPUS}" -ge 2 ]; then
    GPU_QUERY="num_gpus>=${NUM_GPUS} gpu_ram>=20 rentable=True verified=True dph<${MAX_BUDGET} disk_space>${DISK_GB}"
    echo "Searching for ${NUM_GPUS}+ GPU instances under \$${MAX_BUDGET}/hr..."
else
    GPU_QUERY="num_gpus=1 gpu_ram>=20 rentable=True verified=True dph<${MAX_BUDGET} disk_space>${DISK_GB}"
    echo "Searching for single GPU instances under \$${MAX_BUDGET}/hr..."
fi

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
# The onstart script runs inside the container at startup.
# We inline it here with task-specific parameters.
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

mkdir -p /workspace/output/{checkpoints,logs}
chmod +x /workspace/project/infra/scripts/*.sh

# Set environment
export PROJECT_ROOT=/workspace/project
export OUTPUT_DIR=/workspace/output
export PYTHONPATH=/workspace/project

echo "=== onstart complete: \$(date) ==="
touch /opt/ready

# Auto-start training
cd /workspace/project
python -m isaaclab.app.run \\
    --headless \\
    --task ${GYM_ID} \\
    --num_envs ${TOTAL_ENVS} \\
    --max_iterations ${MAX_ITER} \\
    --log_dir /workspace/output/logs \\
    --checkpoint_dir /workspace/output/checkpoints \\
    --agent_cfg ${AGENT_CFG} \\
    >> /var/log/training.log 2>&1 &
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
