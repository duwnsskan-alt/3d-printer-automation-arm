#!/bin/bash
# Vast.ai onstart script.
# Paste the contents of this file into the "On-start script" field
# when creating an instance on vast.ai web UI.
#
# Runs automatically inside the isaac-lab:2.3.2 container at startup.

set -e
exec >> /var/log/onstart.log 2>&1

echo "=== onstart started: $(date) ==="

# ── VNC / display tools ────────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y --no-install-recommends xvfb x11vnc openbox xterm

# noVNC
git clone --depth=1 https://github.com/novnc/noVNC.git /opt/noVNC
git clone --depth=1 https://github.com/novnc/websockify.git /opt/noVNC/utils/websockify

# ── Project ───────────────────────────────────────────────────────────────────
# Replace with your actual repo URL
git clone https://github.com/duwnsskan-alt/3d-printer-automation-arm.git /workspace/project

mkdir -p /workspace/output/{checkpoints,logs}

chmod +x /workspace/project/infra/scripts/*.sh

echo "=== onstart complete: $(date) ==="
touch /opt/ready
