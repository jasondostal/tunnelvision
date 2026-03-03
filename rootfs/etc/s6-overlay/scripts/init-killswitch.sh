#!/bin/bash
# ============================================================================
# TunnelVision — nftables Killswitch
# Blocks all traffic that doesn't go through the VPN tunnel.
# ============================================================================
set -e

VPN_ENABLED=${VPN_ENABLED:-true}
KILLSWITCH_ENABLED=${KILLSWITCH_ENABLED:-true}
WEBUI_PORT=${WEBUI_PORT:-8080}
API_PORT=${API_PORT:-8081}
WEBUI_ALLOWED_NETWORKS=${WEBUI_ALLOWED_NETWORKS:-"192.168.0.0/16,172.16.0.0/12,10.0.0.0/8"}

if [ "$VPN_ENABLED" != "true" ] || [ "$KILLSWITCH_ENABLED" != "true" ]; then
    echo "[tunnelvision] Killswitch disabled — skipping firewall rules"
    echo "disabled" > /var/run/tunnelvision/killswitch_state
    exit 0
fi

echo "[tunnelvision] Applying killswitch firewall rules..."

# --- Read VPN endpoint from WireGuard config ---
VPN_ENDPOINT_IP=$(wg show wg0 endpoints | awk '{print $2}' | cut -d: -f1 | head -1)
VPN_ENDPOINT_PORT=$(wg show wg0 endpoints | awk '{print $2}' | cut -d: -f2 | head -1)
VPN_DNS=$(grep -i "DNS" /etc/wireguard/wg0.conf | head -1 | sed 's/.*=\s*//' | tr -d ' ' | cut -d',' -f1)

# Default DNS to common VPN DNS if not set
VPN_DNS=${VPN_DNS:-"10.64.0.1"}

echo "[tunnelvision] VPN endpoint: ${VPN_ENDPOINT_IP}:${VPN_ENDPOINT_PORT}"
echo "[tunnelvision] VPN DNS: ${VPN_DNS}"

# --- Build allowed networks set elements ---
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

# --- Apply nftables rules ---
nft -f - <<EOF
flush ruleset

# Block ALL IPv6 (leak prevention)
table ip6 block_ipv6 {
    chain input  { type filter hook input   priority -1; policy drop; }
    chain output { type filter hook output  priority -1; policy drop; }
    chain forward { type filter hook forward priority -1; policy drop; }
}

# IPv4 killswitch
table ip tunnelvision {

    set allowed_networks {
        type ipv4_addr
        flags interval
        elements = { ${ALLOWED_NETS} }
    }

    chain input {
        type filter hook input priority 0; policy drop;

        # Loopback
        iif lo accept

        # Established/related connections
        ct state established,related accept

        # VPN tunnel traffic
        iifname "wg0" accept

        # WireGuard handshake responses
        ip saddr ${VPN_ENDPOINT_IP} udp sport ${VPN_ENDPOINT_PORT} accept

        # WebUI + API from allowed networks
        ip saddr @allowed_networks tcp dport ${WEBUI_PORT} accept
        ip saddr @allowed_networks tcp dport ${API_PORT} accept

        # ICMP essentials
        icmp type { destination-unreachable, time-exceeded, echo-request } accept
    }

    chain forward {
        type filter hook forward priority 0; policy drop;

        # For containers using network_mode: service:tunnelvision
        oifname "wg0" accept
        iifname "wg0" ct state established,related accept
    }

    chain output {
        type filter hook output priority 0; policy drop;

        # Loopback
        oif lo accept

        # Established/related
        ct state established,related accept

        # DNS: ONLY to VPN DNS, ONLY through tunnel
        oifname "wg0" udp dport 53 ip daddr ${VPN_DNS} accept
        oifname "wg0" tcp dport 53 ip daddr ${VPN_DNS} accept
        udp dport 53 reject
        tcp dport 53 reject with tcp reset

        # All traffic through VPN tunnel
        oifname "wg0" accept

        # WireGuard handshake to endpoint
        ip daddr ${VPN_ENDPOINT_IP} udp dport ${VPN_ENDPOINT_PORT} accept

        # WebUI + API responses to allowed networks
        ip daddr @allowed_networks tcp sport ${WEBUI_PORT} accept
        ip daddr @allowed_networks tcp sport ${API_PORT} accept

        # ICMP essentials
        icmp type { destination-unreachable, time-exceeded, echo-reply } accept
    }
}
EOF

echo "active" > /var/run/tunnelvision/killswitch_state
echo "[tunnelvision] Killswitch active — all non-VPN traffic blocked"
