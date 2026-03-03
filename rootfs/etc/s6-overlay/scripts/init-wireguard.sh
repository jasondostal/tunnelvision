#!/bin/bash
# ============================================================================
# TunnelVision — WireGuard Initialization
# Brings up the WireGuard VPN tunnel.
# If no config found, enters setup mode instead of failing.
# ============================================================================
set -e

VPN_ENABLED=${VPN_ENABLED:-true}

if [ "$VPN_ENABLED" != "true" ]; then
    echo "[tunnelvision] VPN disabled — skipping WireGuard setup"
    echo "disabled" > /var/run/tunnelvision/vpn_state
    echo "false" > /var/run/tunnelvision/setup_required
    exit 0
fi

echo "[tunnelvision] Starting WireGuard..."

# --- Locate WireGuard config ---
WG_CONF=""
if [ -f /config/wireguard/wg0.conf ]; then
    WG_CONF="/config/wireguard/wg0.conf"
elif [ -f /config/wireguard/wg-tunnel.conf ]; then
    WG_CONF="/config/wireguard/wg-tunnel.conf"
fi

# --- No config? Enter setup mode ---
if [ -z "$WG_CONF" ]; then
    echo "[tunnelvision] No WireGuard config found — entering setup mode"
    echo "[tunnelvision] Open the dashboard to configure your VPN"
    echo "setup_required" > /var/run/tunnelvision/vpn_state
    echo "true" > /var/run/tunnelvision/setup_required
    exit 0
fi

echo "false" > /var/run/tunnelvision/setup_required
echo "[tunnelvision] Using WireGuard config: $WG_CONF"

# --- Create symlink for wg-quick ---
mkdir -p /etc/wireguard
ln -sf "$WG_CONF" /etc/wireguard/wg0.conf

# --- Bring up the tunnel ---
wg-quick up wg0

# --- Verify tunnel is up ---
if ! ip link show wg0 &>/dev/null; then
    echo "[tunnelvision] ERROR: WireGuard interface wg0 failed to come up"
    echo "error" > /var/run/tunnelvision/vpn_state
    exit 1
fi

# --- Record VPN state ---
WG_IP=$(ip -4 addr show wg0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
echo "up" > /var/run/tunnelvision/vpn_state
echo "$WG_IP" > /var/run/tunnelvision/vpn_ip
date -u +%Y-%m-%dT%H:%M:%SZ > /var/run/tunnelvision/vpn_started_at

# --- Extract endpoint info ---
WG_ENDPOINT=$(wg show wg0 endpoints | awk '{print $2}' | head -1)
echo "$WG_ENDPOINT" > /var/run/tunnelvision/vpn_endpoint

echo "[tunnelvision] WireGuard up — interface IP: $WG_IP, endpoint: $WG_ENDPOINT"
