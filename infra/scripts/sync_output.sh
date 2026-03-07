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

echo "Downloading from ${HOST}:${PORT} -> ${LOCAL_DIR}/"

scp -P "${PORT}" \
    -i "${KEY_FILE}" \
    -o StrictHostKeyChecking=no \
    -r \
    root@"${HOST}":/workspace/output/checkpoints \
    "${LOCAL_DIR}/"

scp -P "${PORT}" \
    -i "${KEY_FILE}" \
    -o StrictHostKeyChecking=no \
    -r \
    root@"${HOST}":/workspace/output/logs \
    "${LOCAL_DIR}/"

echo ""
echo "Done. $(du -sh "${LOCAL_DIR}" | cut -f1) downloaded to ${LOCAL_DIR}/"
echo ""
echo "Checkpoint files:"
find "${LOCAL_DIR}/checkpoints" -name "*.pt" | sort | tail -5
