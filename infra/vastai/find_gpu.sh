#!/bin/bash
# Runs on LOCAL machine.
# Finds cheapest available A10G instances on Vast.ai.
#
# Setup (one-time):
#   pip install vastai
#   vastai set api-key <your-api-key>   # from vast.ai → Account → API Key

MAX_PRICE="${1:-0.50}"

command -v vastai &>/dev/null || pip install --quiet vastai

echo "Searching A10G instances under \$${MAX_PRICE}/hr..."
echo ""

vastai search offers \
    "gpu_name=A10G num_gpus=1 rentable=True verified=True dph<${MAX_PRICE} disk_space>150" \
    --order "dph asc" \
    --limit 10

echo ""
echo "Launch with:"
echo "  vastai create instance <ID> \\"
echo "    --image nvcr.io/nvidia/isaac-lab:2.3.2 \\"
echo "    --disk 150 \\"
echo "    --onstart-cmd \"\$(cat infra/vastai/onstart.sh)\""
