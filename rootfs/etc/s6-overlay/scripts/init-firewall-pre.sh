#!/bin/bash
# ============================================================================
# TunnelVision — Pre-VPN Firewall (Firewall-First Boot)
# Applies a strict lockdown BEFORE WireGuard/OpenVPN starts.
# Prevents traffic leaks during VPN initialization and on VPN failure.
# init-killswitch upgrades these rules after the tunnel is confirmed up.
# ============================================================================
set -e

VPN_ENABLED=${VPN_ENABLED:-true}
KILLSWITCH_ENABLED=${KILLSWITCH_ENABLED:-true}
API_PORT=${API_PORT:-8081}
WEBUI_ALLOWED_NETWORKS=${WEBUI_ALLOWED_NETWORKS:-"192.168.0.0/16,172.16.0.0/12,10.0.0.0/8"}

if [ "$VPN_ENABLED" != "true" ] || [ "$KILLSWITCH_ENABLED" != "true" ]; then
    echo "[tunnelvision] Pre-VPN firewall: killswitch disabled — skipping"
    exit 0
fi

echo "[tunnelvision] Applying pre-VPN firewall (lockdown before tunnel up)..."

# --- Detect VPN config (mirrors init-wireguard logic) ---
WG_CONF=""
OVPN_CONF=""

for f in /config/wireguard/wg0.conf /config/wireguard/wg-tunnel.conf /config/wireguard/*.conf; do
    [ -f "$f" ] && WG_CONF="$f" && break
done

for f in /config/openvpn/*.ovpn /config/openvpn/*.conf; do
    [ -f "$f" ] && OVPN_CONF="$f" && break
done

# --- No config: setup mode, nothing to lock down yet ---
if [ -z "$WG_CONF" ] && [ -z "$OVPN_CONF" ]; then
    echo "[tunnelvision] Pre-VPN firewall: no config found — setup mode, skipping"
    exit 0
fi

# --- Parse VPN endpoint ---
VPN_ENDPOINT_IP=""
VPN_ENDPOINT_PORT=""
VPN_PROTO="udp"

if [ -n "$WG_CONF" ]; then
    RAW_ENDPOINT=$(grep -i '^\s*Endpoint\s*=' "$WG_CONF" | head -1 | sed 's/.*=\s*//' | tr -d ' ')
    if [ -n "$RAW_ENDPOINT" ]; then
        ENDPOINT_HOST=$(echo "$RAW_ENDPOINT" | sed 's/:\([0-9]*\)$//' | tr -d '[]')
        VPN_ENDPOINT_PORT=$(echo "$RAW_ENDPOINT" | grep -oE ':[0-9]+$' | tr -d ':')
        VPN_ENDPOINT_PORT=${VPN_ENDPOINT_PORT:-51820}
        VPN_PROTO="udp"

        if echo "$ENDPOINT_HOST" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
            VPN_ENDPOINT_IP="$ENDPOINT_HOST"
        else
            echo "[tunnelvision] Pre-VPN firewall: resolving $ENDPOINT_HOST..."
            VPN_ENDPOINT_IP=$(getent hosts "$ENDPOINT_HOST" 2>/dev/null | awk '{print $1}' | head -1 || true)
        fi
    fi
elif [ -n "$OVPN_CONF" ]; then
    REMOTE_LINE=$(grep -i '^remote ' "$OVPN_CONF" 2>/dev/null | head -1 || true)
    ENDPOINT_HOST=$(echo "$REMOTE_LINE" | awk '{print $2}')
    VPN_ENDPOINT_PORT=$(echo "$REMOTE_LINE" | awk '{print $3}')
    VPN_ENDPOINT_PORT=${VPN_ENDPOINT_PORT:-1194}
    if grep -qi "proto tcp" "$OVPN_CONF" 2>/dev/null; then
        VPN_PROTO="tcp"
    fi

    if echo "$ENDPOINT_HOST" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
        VPN_ENDPOINT_IP="$ENDPOINT_HOST"
    elif [ -n "$ENDPOINT_HOST" ]; then
        echo "[tunnelvision] Pre-VPN firewall: resolving $ENDPOINT_HOST..."
        VPN_ENDPOINT_IP=$(getent hosts "$ENDPOINT_HOST" 2>/dev/null | awk '{print $1}' | head -1 || true)
    fi
fi

# --- Build nft set elements for allowed networks ---
ALLOWED_NETS=""
IFS=',' read -ra NETS <<< "$WEBUI_ALLOWED_NETWORKS"
for net in "${NETS[@]}"; do
    net=$(echo "$net" | tr -d ' ')
    if [ -n "$ALLOWED_NETS" ]; then
        ALLOWED_NETS="${ALLOWED_NETS}, ${net}"
    else
        ALLOWED_NETS="${net}"
    fi
done

# --- Build VPN endpoint rules ---
if [ -n "$VPN_ENDPOINT_IP" ] && [ -n "$VPN_ENDPOINT_PORT" ]; then
    VPN_OUT_RULE="ip daddr ${VPN_ENDPOINT_IP} ${VPN_PROTO} dport ${VPN_ENDPOINT_PORT} accept"
    VPN_IN_RULE="ip saddr ${VPN_ENDPOINT_IP} ${VPN_PROTO} sport ${VPN_ENDPOINT_PORT} accept"
    echo "[tunnelvision] Pre-VPN firewall: locked to ${VPN_ENDPOINT_IP}:${VPN_ENDPOINT_PORT}/${VPN_PROTO}"
else
    # Could not determine endpoint — allow DNS out so WireGuard can resolve it at startup
    VPN_OUT_RULE="udp dport 53 accept"
    VPN_IN_RULE="udp sport 53 accept"
    echo "[tunnelvision] Pre-VPN firewall: WARNING — endpoint unresolvable, allowing DNS egress only"
fi

# --- Apply pre-VPN nftables rules ---
nft delete table ip6 block_ipv6 2>/dev/null || true
nft delete table ip tunnelvision 2>/dev/null || true

nft -f - <<EOF

# Block ALL IPv6 — leak prevention
table ip6 block_ipv6 {
    chain input  { type filter hook input   priority -1; policy drop; }
    chain output { type filter hook output  priority -1; policy drop; }
    chain forward { type filter hook forward priority -1; policy drop; }
}

# Pre-VPN lockdown: only VPN endpoint handshake + API access
table ip tunnelvision {

    set allowed_networks {
        type ipv4_addr
        flags interval
        elements = { ${ALLOWED_NETS} }
    }

    chain input {
        type filter hook input priority 0; policy drop;

        iif lo accept
        ct state established,related accept

        # VPN handshake response (before tunnel is up)
        ${VPN_IN_RULE}

        # API remains accessible during VPN bring-up
        ip saddr @allowed_networks tcp dport ${API_PORT} accept

        icmp type { destination-unreachable, time-exceeded, echo-request } accept
    }

    chain forward {
        type filter hook forward priority 0; policy drop;
    }

    chain output {
        type filter hook output priority 0; policy drop;

        oifname "lo" accept

        # VPN handshake to endpoint
        ${VPN_OUT_RULE}

        # API responses to LAN
        ip daddr @allowed_networks tcp sport ${API_PORT} accept

        icmp type { destination-unreachable, time-exceeded, echo-reply } accept
    }
}
EOF

echo "[tunnelvision] Pre-VPN firewall active — all traffic locked to VPN endpoint"
