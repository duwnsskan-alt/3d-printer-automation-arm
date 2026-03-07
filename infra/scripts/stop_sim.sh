#!/bin/bash
# Runs on LOCAL machine.
# Destroys the Vast.ai instance to stop billing.
# Run sync_output.sh FIRST to save your checkpoints.
#
# Usage:
#   ./infra/scripts/stop_sim.sh <instance-id>
#
# Find instance ID:
#   vastai show instances

set -e

INSTANCE_ID="${1}"

if [ -z "${INSTANCE_ID}" ]; then
    echo "Usage: $0 <instance-id>"
    echo ""
    echo "Running instances:"
    vastai show instances 2>/dev/null || echo "  (run: pip install vastai && vastai set api-key <key>)"
    exit 1
fi

echo "================================================="
echo "  Destroying Vast.ai instance: ${INSTANCE_ID}"
echo "  Make sure you ran sync_output.sh first!"
echo "================================================="
printf "Type 'yes' to confirm: "
read -r CONFIRM

if [ "${CONFIRM}" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

vastai destroy instance "${INSTANCE_ID}"
echo "Instance ${INSTANCE_ID} destroyed."
