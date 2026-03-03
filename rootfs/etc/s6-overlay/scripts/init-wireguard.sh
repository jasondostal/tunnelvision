#!/bin/bash
# ============================================================================
# TunnelVision — VPN Initialization (WireGuard + OpenVPN)
# Supports both engines. Auto-detects from config file extension.
# Randomizes server selection when VPN_COUNTRY/VPN_CITY is set.
# ============================================================================
set -e

VPN_ENABLED=${VPN_ENABLED:-true}
VPN_TYPE=${VPN_TYPE:-auto}
VPN_PROVIDER=${VPN_PROVIDER:-custom}

if [ "$VPN_ENABLED" != "true" ]; then
    echo "[tunnelvision] VPN disabled — skipping"
    echo "disabled" > /var/run/tunnelvision/vpn_state
    echo "false" > /var/run/tunnelvision/setup_required
    exit 0
fi

echo "[tunnelvision] Initializing VPN..."

# --- Locate config ---
WG_CONF=""
OVPN_CONF=""

# Check WireGuard configs
for f in /config/wireguard/wg0.conf /config/wireguard/wg-tunnel.conf /config/wireguard/*.conf; do
    [ -f "$f" ] && WG_CONF="$f" && break
done

# Check OpenVPN configs
for f in /config/openvpn/*.ovpn /config/openvpn/*.conf; do
    [ -f "$f" ] && OVPN_CONF="$f" && break
done

# --- Auto-detect VPN type ---
if [ "$VPN_TYPE" = "auto" ]; then
    if [ -n "$WG_CONF" ]; then
        VPN_TYPE="wireguard"
    elif [ -n "$OVPN_CONF" ]; then
        VPN_TYPE="openvpn"
    fi
fi

# --- No config? Enter setup mode ---
if [ "$VPN_TYPE" = "wireguard" ] && [ -z "$WG_CONF" ]; then
    echo "[tunnelvision] No WireGuard config found — entering setup mode"
    echo "setup_required" > /var/run/tunnelvision/vpn_state
    echo "true" > /var/run/tunnelvision/setup_required
    exit 0
elif [ "$VPN_TYPE" = "openvpn" ] && [ -z "$OVPN_CONF" ]; then
    echo "[tunnelvision] No OpenVPN config found — entering setup mode"
    echo "setup_required" > /var/run/tunnelvision/vpn_state
    echo "true" > /var/run/tunnelvision/setup_required
    exit 0
elif [ "$VPN_TYPE" = "auto" ]; then
    echo "[tunnelvision] No VPN config found — entering setup mode"
    echo "setup_required" > /var/run/tunnelvision/vpn_state
    echo "true" > /var/run/tunnelvision/setup_required
    exit 0
fi

echo "false" > /var/run/tunnelvision/setup_required
echo "$VPN_TYPE" > /var/run/tunnelvision/vpn_type

# =====================================================================
# WireGuard
# =====================================================================
if [ "$VPN_TYPE" = "wireguard" ]; then
    echo "[tunnelvision] Using WireGuard: $WG_CONF"

    mkdir -p /etc/wireguard
    ln -sf "$WG_CONF" /etc/wireguard/wg0.conf

    wg-quick up wg0

    if ! ip link show wg0 &>/dev/null; then
        echo "[tunnelvision] ERROR: WireGuard interface wg0 failed"
        echo "error" > /var/run/tunnelvision/vpn_state
        exit 1
    fi

    WG_IP=$(ip -4 addr show wg0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    WG_ENDPOINT=$(wg show wg0 endpoints | awk '{print $2}' | head -1)
    VPN_INTERFACE="wg0"

    echo "up" > /var/run/tunnelvision/vpn_state
    echo "$WG_IP" > /var/run/tunnelvision/vpn_ip
    echo "$WG_ENDPOINT" > /var/run/tunnelvision/vpn_endpoint
    echo "$VPN_INTERFACE" > /var/run/tunnelvision/vpn_interface
    date -u +%Y-%m-%dT%H:%M:%SZ > /var/run/tunnelvision/vpn_started_at

    echo "[tunnelvision] WireGuard up — IP: $WG_IP, endpoint: $WG_ENDPOINT"

# =====================================================================
# OpenVPN
# =====================================================================
elif [ "$VPN_TYPE" = "openvpn" ]; then
    echo "[tunnelvision] Using OpenVPN: $OVPN_CONF"

    # If credentials file exists, reference it
    AUTH_FILE=""
    if [ -f /config/openvpn/credentials.txt ]; then
        AUTH_FILE="--auth-user-pass /config/openvpn/credentials.txt"
    fi

    # Start OpenVPN in background, wait for tun interface
    openvpn --config "$OVPN_CONF" \
        --daemon \
        --log /var/run/tunnelvision/openvpn.log \
        --writepid /var/run/tunnelvision/openvpn.pid \
        --script-security 2 \
        $AUTH_FILE

    # Wait for tun interface (up to 30s)
    TRIES=0
    while [ $TRIES -lt 30 ]; do
        if ip link show tun0 &>/dev/null; then
            break
        fi
        sleep 1
        TRIES=$((TRIES + 1))
    done

    if ! ip link show tun0 &>/dev/null; then
        echo "[tunnelvision] ERROR: OpenVPN tun0 interface failed after 30s"
        echo "[tunnelvision] Check /var/run/tunnelvision/openvpn.log"
        echo "error" > /var/run/tunnelvision/vpn_state
        exit 1
    fi

    TUN_IP=$(ip -4 addr show tun0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    VPN_INTERFACE="tun0"

    echo "up" > /var/run/tunnelvision/vpn_state
    echo "$TUN_IP" > /var/run/tunnelvision/vpn_ip
    echo "$VPN_INTERFACE" > /var/run/tunnelvision/vpn_interface
    date -u +%Y-%m-%dT%H:%M:%SZ > /var/run/tunnelvision/vpn_started_at

    echo "[tunnelvision] OpenVPN up — IP: $TUN_IP"
fi
