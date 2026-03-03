#!/bin/bash
# ============================================================================
# TunnelVision — Environment Initialization
# Sets up user/group, directories, permissions, and container environment.
# ============================================================================
set -e

echo "[tunnelvision] Initializing environment..."

# --- PUID/PGID Setup ---
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Modify tunnelvision user to match requested PUID/PGID
if [ "$(id -u tunnelvision 2>/dev/null)" != "$PUID" ]; then
    usermod -u "$PUID" tunnelvision 2>/dev/null || true
fi
if [ "$(id -g tunnelvision 2>/dev/null)" != "$PGID" ]; then
    groupmod -g "$PGID" tunnelvision 2>/dev/null || true
fi

echo "[tunnelvision] Running as UID=$PUID GID=$PGID"

# --- Directory Setup ---
mkdir -p \
    /config/qBittorrent/config \
    /config/qBittorrent/data \
    /config/wireguard \
    /downloads \
    /var/run/tunnelvision

# --- Default Config ---
if [ ! -f /config/qBittorrent/config/qBittorrent.conf ]; then
    echo "[tunnelvision] First run — copying default qBittorrent config"
    cp /defaults/qBittorrent.conf /config/qBittorrent/config/qBittorrent.conf
fi

# --- Apply WebUI port to config ---
WEBUI_PORT=${WEBUI_PORT:-8080}
if grep -q "WebUI\\\\Port=" /config/qBittorrent/config/qBittorrent.conf; then
    sed -i "s/WebUI\\\\Port=.*/WebUI\\\\Port=${WEBUI_PORT}/" /config/qBittorrent/config/qBittorrent.conf
fi

# --- Permissions ---
chown -R "$PUID:$PGID" /config /downloads 2>/dev/null || true
chown -R "$PUID:$PGID" /var/run/tunnelvision 2>/dev/null || true

# --- Timezone ---
if [ -n "$TZ" ] && [ -f "/usr/share/zoneinfo/$TZ" ]; then
    ln -sf "/usr/share/zoneinfo/$TZ" /etc/localtime
    echo "$TZ" > /etc/timezone
fi

# --- Write runtime state for other services ---
echo "$PUID" > /var/run/tunnelvision/puid
echo "$PGID" > /var/run/tunnelvision/pgid

# --- Detect default gateway and interface ---
DEFAULT_GW=$(ip route show default | awk '/default/ {print $3}' | head -1)
DEFAULT_IF=$(ip route show default | awk '/default/ {print $5}' | head -1)
echo "$DEFAULT_GW" > /var/run/tunnelvision/default_gateway
echo "$DEFAULT_IF" > /var/run/tunnelvision/default_interface

echo "[tunnelvision] Default gateway: ${DEFAULT_GW:-none} via ${DEFAULT_IF:-none}"
echo "[tunnelvision] Environment initialized"
