#!/bin/bash
# Runs on LOCAL machine.
# Finds cheapest available GPU instances on Vast.ai.
#
# Usage:
#   ./find_gpu.sh                    # Single GPU, <$0.50/hr
#   ./find_gpu.sh --budget 2.00      # Single GPU, <$2.00/hr
#   ./find_gpu.sh --gpus 4           # 4x GPU for 10k+ env scale-up
#   ./find_gpu.sh --gpus 4 --a10g    # 4x A10G for 256-env training
#   ./find_gpu.sh --gpus 8 --a100    # 8x A100 for maximum throughput
#
# Setup (one-time):
#   pip install vastai
#   vastai set api-key <your-api-key>   # from vast.ai → Account → API Key
#
# For automated launch, use: ./infra/vastai/launch_cloud.sh

set -euo pipefail

MAX_PRICE="${1:-0.50}"
NUM_GPUS=1
GPU_FILTER=""

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --budget) MAX_PRICE="$2"; shift 2 ;;
        --gpus)   NUM_GPUS="$2"; shift 2 ;;
        --a10g)   GPU_FILTER="gpu_name=A10G"; shift ;;
        --a100)   GPU_FILTER="gpu_name=A100"; shift ;;
        --h100)   GPU_FILTER="gpu_name=H100"; shift ;;
        *)        MAX_PRICE="${1}"; shift ;;
    esac
done

command -v vastai &>/dev/null || pip install --quiet vastai

# Build query
QUERY="num_gpus>=${NUM_GPUS} gpu_ram>=20 rentable=True verified=True dph<${MAX_PRICE} disk_space>150"
[ -n "${GPU_FILTER}" ] && QUERY="${GPU_FILTER} ${QUERY}"

echo "=== Vast.ai GPU Search ==="
echo "  GPUs: >= ${NUM_GPUS}"
echo "  Budget: < \$${MAX_PRICE}/hr"
[ -n "${GPU_FILTER}" ] && echo "  Filter: ${GPU_FILTER}"
echo ""

vastai search offers "${QUERY}" --order "dph asc" --limit 15

echo ""
echo "─── Quick launch ───────────────────────────────────────────"
echo "  Manual:     vastai create instance <ID> --image nvcr.io/nvidia/isaac-lab:2.3.2 --disk 200"
echo "  Automated:  ./infra/vastai/launch_cloud.sh --gpus ${NUM_GPUS} --budget ${MAX_PRICE}"
echo ""
echo "─── Scale reference ──────────────────────────────────────"
echo "  Local test:     16 envs    → 1x GPU  (A10G/RTX 4070+)"
echo "  Standard train: 256 envs   → 1x GPU  (A100 40GB)"
echo "  Scale-up:       2048 envs  → 4x GPU  (A100 80GB)"
echo "  Full batch:     10240 envs → 8x GPU  (H100 80GB)"
