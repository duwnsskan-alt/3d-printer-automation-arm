#!/bin/bash
# Runs on LOCAL machine.
# Downloads checkpoints from Vast.ai instance via scp.
#
# Usage:
#   ./infra/scripts/sync_output.sh <host> <port> [path/to/key]
#
# Example:
#   ./infra/scripts/sync_output.sh ssh4.vast.ai 44929 ~/.ssh/id_rsa

set -e

HOST="${1}"
PORT="${2}"
KEY_FILE="${3:-${HOME}/.ssh/id_rsa}"

if [ -z "${HOST}" ] || [ -z "${PORT}" ]; then
    echo "Usage: $0 <vast-host> <ssh-port> [path/to/key]"
    exit 1
fi

LOCAL_DIR="$(cd "$(dirname "$0")/../.." && pwd)/models"
mkdir -p "${LOCAL_DIR}/checkpoints" "${LOCAL_DIR}/logs"

SCP_OPTS="-P ${PORT} -i ${KEY_FILE} -o StrictHostKeyChecking=no -r"

echo "Downloading from ${HOST}:${PORT} -> ${LOCAL_DIR}/"

# Checkpoints and logs (always)
scp ${SCP_OPTS} root@"${HOST}":/workspace/output/checkpoints "${LOCAL_DIR}/"
scp ${SCP_OPTS} root@"${HOST}":/workspace/output/logs "${LOCAL_DIR}/"

# Episodes and LeRobot dataset (if they exist)
echo "Checking for exported episodes and LeRobot dataset..."
ssh -p "${PORT}" -i "${KEY_FILE}" -o StrictHostKeyChecking=no root@"${HOST}" \
    "ls /workspace/output/episodes/ 2>/dev/null" && {
    mkdir -p "${LOCAL_DIR}/episodes"
    scp ${SCP_OPTS} root@"${HOST}":/workspace/output/episodes "${LOCAL_DIR}/"
    echo "  Episodes downloaded."
} || echo "  No episodes found (export may not have run)."

ssh -p "${PORT}" -i "${KEY_FILE}" -o StrictHostKeyChecking=no root@"${HOST}" \
    "ls /workspace/output/lerobot_dataset/ 2>/dev/null" && {
    mkdir -p "${LOCAL_DIR}/lerobot_dataset"
    scp ${SCP_OPTS} root@"${HOST}":/workspace/output/lerobot_dataset "${LOCAL_DIR}/"
    echo "  LeRobot dataset downloaded."
} || echo "  No LeRobot dataset found (conversion may not have run)."

echo ""
echo "Done. $(du -sh "${LOCAL_DIR}" | cut -f1) downloaded to ${LOCAL_DIR}/"
echo ""
echo "Checkpoint files:"
find "${LOCAL_DIR}/checkpoints" -name "*.pt" 2>/dev/null | sort | tail -5
echo ""
echo "LeRobot dataset:"
find "${LOCAL_DIR}/lerobot_dataset" -name "info.json" 2>/dev/null | head -3
