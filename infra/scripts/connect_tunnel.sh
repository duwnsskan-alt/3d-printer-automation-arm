#!/bin/bash
# Runs on the REMOTE (cloud) instance.
# Starts the nginx CORS proxy + Cloudflare Tunnel for sim dashboard access.
#
# Prerequisites:
#   - cloudflared installed and authenticated on the instance
#   - Tunnel created: cloudflared tunnel create isaac-sim
#   - DNS route added: cloudflared tunnel route dns isaac-sim sim.yourdomain.com
#   - infra/docker/cloudflared.yml updated with your tunnel ID and hostname
#
# Usage:
#   ./infra/scripts/connect_tunnel.sh [tunnel-config-path]
#
# This is an alternative to connect_vnc.sh (SSH tunnel).
# Use this when you want a stable public URL instead of local port forwarding.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TUNNEL_CONFIG="${1:-${PROJECT_ROOT}/infra/docker/cloudflared.yml}"
NGINX_CONF="${PROJECT_ROOT}/infra/docker/nginx-cors-proxy.conf"

# ── Preflight checks ────────────────────────────────────────────────────────
if ! command -v cloudflared &>/dev/null; then
    echo "ERROR: cloudflared not found. Install from:"
    echo "  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
fi

if ! command -v nginx &>/dev/null; then
    echo "Installing nginx..."
    apt-get update -qq && apt-get install -y -qq nginx >/dev/null 2>&1
fi

if grep -q "TUNNEL_ID_HERE" "${TUNNEL_CONFIG}"; then
    echo "ERROR: Update ${TUNNEL_CONFIG} with your tunnel ID first."
    echo ""
    echo "  1. cloudflared tunnel login"
    echo "  2. cloudflared tunnel create isaac-sim"
    echo "  3. Replace TUNNEL_ID_HERE with the tunnel ID"
    echo "  4. Update the hostname"
    exit 1
fi

# ── Start nginx CORS proxy ──────────────────────────────────────────────────
echo "[1/2] Starting nginx CORS proxy on port 6090..."

# Check that noVNC (port 6080) is running
if ! curl -s -o /dev/null http://localhost:6080; then
    echo "WARNING: noVNC not responding on port 6080."
    echo "         Make sure the sim container is running first."
fi

# Copy config and start
cp "${NGINX_CONF}" /etc/nginx/sites-available/novnc-cors.conf
ln -sf /etc/nginx/sites-available/novnc-cors.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t && nginx -s reload 2>/dev/null || nginx
echo "      nginx CORS proxy ready on :6090"

# ── Start Cloudflare Tunnel ─────────────────────────────────────────────────
echo "[2/2] Starting Cloudflare Tunnel..."
echo ""

HOSTNAME=$(grep "hostname:" "${TUNNEL_CONFIG}" | head -1 | awk '{print $NF}')
echo "================================================="
echo "  Sim dashboard will be at: https://${HOSTNAME}"
echo "  Ctrl+C to disconnect tunnel"
echo "================================================="
echo ""

exec cloudflared tunnel --config "${TUNNEL_CONFIG}" run
