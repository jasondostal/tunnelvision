#!/bin/bash
# ============================================================================
# TunnelVision — nftables Killswitch
# Blocks all traffic that doesn't go through the VPN tunnel.
# Works with both WireGuard (wg0) and OpenVPN (tun0).
# ============================================================================
set -e

VPN_ENABLED=${VPN_ENABLED:-true}
KILLSWITCH_ENABLED=${KILLSWITCH_ENABLED:-true}
QBT_ENABLED=${QBT_ENABLED:-true}
WEBUI_PORT=${WEBUI_PORT:-8080}
API_PORT=${API_PORT:-8081}
WEBUI_ALLOWED_NETWORKS=${WEBUI_ALLOWED_NETWORKS:-"192.168.0.0/16,172.16.0.0/12,10.0.0.0/8"}
# Phase 2: Firewall granularity
FIREWALL_VPN_INPUT_PORTS=${FIREWALL_VPN_INPUT_PORTS:-""}
FIREWALL_OUTBOUND_SUBNETS=${FIREWALL_OUTBOUND_SUBNETS:-""}
FIREWALL_CUSTOM_RULES_FILE=${FIREWALL_CUSTOM_RULES_FILE:-""}
# Phase 3/5/6: Service ports
DNS_ENABLED=${DNS_ENABLED:-false}
HTTP_PROXY_ENABLED=${HTTP_PROXY_ENABLED:-false}
HTTP_PROXY_PORT=${HTTP_PROXY_PORT:-8888}
SOCKS_PROXY_ENABLED=${SOCKS_PROXY_ENABLED:-false}
SOCKS_PROXY_PORT=${SOCKS_PROXY_PORT:-1080}

# Skip in setup mode
SETUP_REQUIRED=$(cat /var/run/tunnelvision/setup_required 2>/dev/null || echo "false")
if [ "$SETUP_REQUIRED" = "true" ]; then
    echo "[tunnelvision] Setup mode — skipping killswitch"
    echo "disabled" > /var/run/tunnelvision/killswitch_state
    exit 0
fi

if [ "$VPN_ENABLED" != "true" ] || [ "$KILLSWITCH_ENABLED" != "true" ]; then
    echo "[tunnelvision] Killswitch disabled — skipping firewall rules"
    echo "disabled" > /var/run/tunnelvision/killswitch_state
    exit 0
fi

echo "[tunnelvision] Applying killswitch firewall rules..."

# --- Detect VPN interface and type ---
VPN_IF=$(cat /var/run/tunnelvision/vpn_interface 2>/dev/null || echo "wg0")
VPN_TYPE_DETECTED=$(cat /var/run/tunnelvision/vpn_type 2>/dev/null || echo "wireguard")

echo "[tunnelvision] VPN interface: $VPN_IF ($VPN_TYPE_DETECTED)"

# --- Get endpoint info based on VPN type ---
if [ "$VPN_TYPE_DETECTED" = "wireguard" ]; then
    VPN_ENDPOINT_IP=$(wg show wg0 endpoints | awk '{print $2}' | cut -d: -f1 | head -1)
    VPN_ENDPOINT_PORT=$(wg show wg0 endpoints | awk '{print $2}' | cut -d: -f2 | head -1)
    VPN_PROTO="udp"
    VPN_DNS="${VPN_DNS:-$(grep -i 'DNS' /etc/wireguard/wg0.conf 2>/dev/null | head -1 | sed 's/.*=\s*//' | tr -d ' ' | cut -d',' -f1)}"
elif [ "$VPN_TYPE_DETECTED" = "openvpn" ]; then
    # Parse endpoint from OpenVPN config or log
    VPN_ENDPOINT_IP=$(grep -i '^remote ' /config/openvpn/*.ovpn /config/openvpn/*.conf 2>/dev/null | head -1 | awk '{print $2}')
    VPN_ENDPOINT_PORT=$(grep -i '^remote ' /config/openvpn/*.ovpn /config/openvpn/*.conf 2>/dev/null | head -1 | awk '{print $3}')
    VPN_ENDPOINT_PORT=${VPN_ENDPOINT_PORT:-1194}
    # OpenVPN can use TCP or UDP
    if grep -qi "proto tcp" /config/openvpn/*.ovpn /config/openvpn/*.conf 2>/dev/null; then
        VPN_PROTO="tcp"
    else
        VPN_PROTO="udp"
    fi
    VPN_DNS=$(grep -i 'dhcp-option DNS' /config/openvpn/*.ovpn /config/openvpn/*.conf 2>/dev/null | head -1 | awk '{print $NF}')
fi

VPN_DNS=${VPN_DNS:-"10.64.0.1"}

echo "[tunnelvision] VPN endpoint: ${VPN_ENDPOINT_IP}:${VPN_ENDPOINT_PORT} (${VPN_PROTO})"
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

# --- Route allowed networks through host network (not VPN) ---
# wg-quick's fwmark routing sends ALL responses through wg0.
# We need LAN traffic to go back through eth0 so Docker port mapping works.
DEFAULT_GW=$(cat /var/run/tunnelvision/default_gateway 2>/dev/null)
DEFAULT_IF=$(cat /var/run/tunnelvision/default_interface 2>/dev/null)
if [ -n "$DEFAULT_GW" ] && [ -n "$DEFAULT_IF" ]; then
    for net in "${NETS[@]}"; do
        net=$(echo "$net" | tr -d ' ')
        ip route add "$net" via "$DEFAULT_GW" dev "$DEFAULT_IF" 2>/dev/null || true
        echo "[tunnelvision] Route: $net via $DEFAULT_GW ($DEFAULT_IF)"
    done
fi

# --- Build conditional WebUI rules ---
if [ "$QBT_ENABLED" = "true" ]; then
    WEBUI_INPUT_RULE="ip saddr @allowed_networks tcp dport ${WEBUI_PORT} accept"
    WEBUI_OUTPUT_RULE="ip daddr @allowed_networks tcp sport ${WEBUI_PORT} accept"
else
    WEBUI_INPUT_RULE=""
    WEBUI_OUTPUT_RULE=""
fi

# --- Phase 2: VPN-side input ports ---
VPN_INPUT_PORT_RULES=""
if [ -n "$FIREWALL_VPN_INPUT_PORTS" ]; then
    IFS=',' read -ra VPN_PORTS <<< "$FIREWALL_VPN_INPUT_PORTS"
    for port in "${VPN_PORTS[@]}"; do
        port=$(echo "$port" | tr -d ' ')
        if [ -n "$port" ]; then
            VPN_INPUT_PORT_RULES="${VPN_INPUT_PORT_RULES}
        iifname \"${VPN_IF}\" tcp dport ${port} accept
        iifname \"${VPN_IF}\" udp dport ${port} accept"
            echo "[tunnelvision] Firewall: allowing VPN input port ${port}"
        fi
    done
fi

# --- Phase 2: Outbound subnets that bypass VPN ---
OUTBOUND_SUBNET_RULES=""
if [ -n "$FIREWALL_OUTBOUND_SUBNETS" ]; then
    IFS=',' read -ra SUBNETS <<< "$FIREWALL_OUTBOUND_SUBNETS"
    for subnet in "${SUBNETS[@]}"; do
        subnet=$(echo "$subnet" | tr -d ' ')
        if [ -n "$subnet" ]; then
            OUTBOUND_SUBNET_RULES="${OUTBOUND_SUBNET_RULES}
        ip daddr ${subnet} accept"
            # Route through host gateway (not VPN)
            if [ -n "$DEFAULT_GW" ] && [ -n "$DEFAULT_IF" ]; then
                ip route add "$subnet" via "$DEFAULT_GW" dev "$DEFAULT_IF" 2>/dev/null || true
                echo "[tunnelvision] Firewall: outbound subnet ${subnet} via ${DEFAULT_GW}"
            fi
        fi
    done
fi

# --- Phase 3/5/6: Service port rules ---
DNS_INPUT_RULE=""
DNS_OUTPUT_RULE=""
if [ "$DNS_ENABLED" = "true" ]; then
    DNS_INPUT_RULE="ip saddr @allowed_networks udp dport 53 accept
        ip saddr @allowed_networks tcp dport 53 accept"
    DNS_OUTPUT_RULE="ip daddr @allowed_networks udp sport 53 accept
        ip daddr @allowed_networks tcp sport 53 accept"
    echo "[tunnelvision] Firewall: allowing DNS port 53 from allowed networks"
fi

HTTP_PROXY_INPUT_RULE=""
HTTP_PROXY_OUTPUT_RULE=""
if [ "$HTTP_PROXY_ENABLED" = "true" ]; then
    HTTP_PROXY_INPUT_RULE="ip saddr @allowed_networks tcp dport ${HTTP_PROXY_PORT} accept"
    HTTP_PROXY_OUTPUT_RULE="ip daddr @allowed_networks tcp sport ${HTTP_PROXY_PORT} accept"
    echo "[tunnelvision] Firewall: allowing HTTP proxy port ${HTTP_PROXY_PORT}"
fi

SOCKS_PROXY_INPUT_RULE=""
SOCKS_PROXY_OUTPUT_RULE=""
if [ "$SOCKS_PROXY_ENABLED" = "true" ]; then
    SOCKS_PROXY_INPUT_RULE="ip saddr @allowed_networks tcp dport ${SOCKS_PROXY_PORT} accept"
    SOCKS_PROXY_OUTPUT_RULE="ip daddr @allowed_networks tcp sport ${SOCKS_PROXY_PORT} accept"
    echo "[tunnelvision] Firewall: allowing SOCKS proxy port ${SOCKS_PROXY_PORT}"
fi

# --- Apply nftables rules ---
# NOTE: Do NOT 'flush ruleset' — wg-quick adds nft rules for fwmark routing
# that we need to keep. Only delete/recreate our own tables.
nft delete table ip6 block_ipv6 2>/dev/null || true
nft delete table ip tunnelvision 2>/dev/null || true

nft -f - <<EOF

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

        iif lo accept
        ct state established,related accept

        # VPN tunnel traffic (wg0 or tun0)
        iifname "${VPN_IF}" accept

        # VPN handshake responses
        ip saddr ${VPN_ENDPOINT_IP} ${VPN_PROTO} sport ${VPN_ENDPOINT_PORT} accept

        # VPN-side input ports (Phase 2)
        ${VPN_INPUT_PORT_RULES}

        # WebUI (qBittorrent) from allowed networks — only if qBt enabled
        ${WEBUI_INPUT_RULE}
        # API from allowed networks
        ip saddr @allowed_networks tcp dport ${API_PORT} accept
        # DNS from allowed networks (Phase 3)
        ${DNS_INPUT_RULE}
        # HTTP Proxy from allowed networks (Phase 5)
        ${HTTP_PROXY_INPUT_RULE}
        # SOCKS Proxy from allowed networks (Phase 6)
        ${SOCKS_PROXY_INPUT_RULE}

        icmp type { destination-unreachable, time-exceeded, echo-request } accept
    }

    chain forward {
        type filter hook forward priority 0; policy drop;

        oifname "${VPN_IF}" accept
        iifname "${VPN_IF}" ct state established,related accept
    }

    chain output {
        type filter hook postrouting priority 0; policy drop;

        # Loopback (internal service-to-service: API, healthcheck)
        oifname "lo" accept

        # All traffic through VPN tunnel (DNS included — resolv.conf controls server)
        oifname "${VPN_IF}" accept

        # VPN handshake to endpoint (must exit on host interface, not tunnel)
        ip daddr ${VPN_ENDPOINT_IP} ${VPN_PROTO} dport ${VPN_ENDPOINT_PORT} accept

        # Outbound subnets that bypass VPN (Phase 2)
        ${OUTBOUND_SUBNET_RULES}

        # WebUI (qBittorrent) responses — only if qBt enabled
        ${WEBUI_OUTPUT_RULE}
        # API responses to allowed networks
        ip daddr @allowed_networks tcp sport ${API_PORT} accept
        # DNS responses (Phase 3)
        ${DNS_OUTPUT_RULE}
        # HTTP Proxy responses (Phase 5)
        ${HTTP_PROXY_OUTPUT_RULE}
        # SOCKS Proxy responses (Phase 6)
        ${SOCKS_PROXY_OUTPUT_RULE}

        icmp type { destination-unreachable, time-exceeded, echo-reply } accept
    }
}
EOF

# --- Phase 2: Load custom nftables rules file (after base rules) ---
if [ -n "$FIREWALL_CUSTOM_RULES_FILE" ] && [ -f "$FIREWALL_CUSTOM_RULES_FILE" ]; then
    echo "[tunnelvision] Loading custom firewall rules from ${FIREWALL_CUSTOM_RULES_FILE}"
    nft -f "$FIREWALL_CUSTOM_RULES_FILE" || echo "[tunnelvision] WARNING: Custom rules file failed to load"
fi

echo "active" > /var/run/tunnelvision/killswitch_state
echo "[tunnelvision] Killswitch active — all non-VPN traffic blocked"
