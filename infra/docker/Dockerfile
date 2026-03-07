# Extends official Isaac Lab image with:
#   - Xvfb virtual framebuffer (GPU rendering without a real monitor)
#   - x11vnc (VNC server that mirrors the virtual display)
#   - noVNC (browser-based VNC client, no install needed on your end)
#
# Isaac Lab image already includes Isaac Sim + Isaac Lab + all dependencies.
# No need to install Isaac Lab separately.
#
# Image tag: verify latest at https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-lab
FROM nvcr.io/nvidia/isaac-lab:2.3.2

# ── Display / VNC tools ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    openbox \
    xterm \
    git \
    && rm -rf /var/lib/apt/lists/*

# noVNC + websockify (browser-based VNC proxy)
RUN git clone --depth=1 https://github.com/novnc/noVNC.git /opt/noVNC \
    && git clone --depth=1 https://github.com/novnc/websockify.git /opt/noVNC/utils/websockify \
    && ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html

# ── Environment defaults ──────────────────────────────────────────────────────
ENV ACCEPT_EULA=Y
ENV PRIVACY_CONSENT=Y
ENV OMNI_KIT_ACCEPT_EULA=Y
# Suppress Isaac Sim telemetry prompts
ENV OMNI_KIT_PRIVACY_CONSENT=Y

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /workspace/project
ENTRYPOINT ["/entrypoint.sh"]
