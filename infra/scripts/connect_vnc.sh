#!/bin/bash
# Runs on LOCAL machine.
# Creates SSH tunnel to Vast.ai instance and opens noVNC in browser.
#
# Vast.ai uses non-standard SSH ports (e.g. ssh4.vast.ai:44929).
# Copy the SSH host and port from the Vast.ai web UI instance detail page.
#
# Usage:
#   ./infra/scripts/connect_vnc.sh <host> <port> [path/to/key]
#
# Example:
#   ./infra/scripts/connect_vnc.sh ssh4.vast.ai 44929 ~/.ssh/id_rsa

set -e

HOST="${1}"
PORT="${2}"
KEY_FILE="${3:-${HOME}/.ssh/id_rsa}"
LOCAL_PORT=6080

if [ -z "${HOST}" ] || [ -z "${PORT}" ]; then
    echo "Usage: $0 <vast-host> <ssh-port> [path/to/key]"
    echo ""
    echo "Find host/port on Vast.ai web UI:"
    echo "  Instances → your instance → Connect button"
    echo "  Example: ssh -p 44929 root@ssh4.vast.ai"
    exit 1
fi

echo "================================================="
echo "  Tunnel: localhost:${LOCAL_PORT} -> ${HOST}:6080"
echo "  Key:    ${KEY_FILE}"
echo "================================================="
echo ""
echo "Opening browser in 3 seconds..."
echo "Ctrl+C to disconnect."
echo ""

(
    sleep 3
    open "http://localhost:${LOCAL_PORT}/vnc.html" 2>/dev/null \
        || xdg-open "http://localhost:${LOCAL_PORT}/vnc.html" 2>/dev/null \
        || echo "Open manually: http://localhost:${LOCAL_PORT}/vnc.html"
) &

ssh \
    -i "${KEY_FILE}" \
    -p "${PORT}" \
    -L "${LOCAL_PORT}:localhost:6080" \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -N \
    root@"${HOST}"
