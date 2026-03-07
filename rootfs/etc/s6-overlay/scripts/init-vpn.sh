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

    # Create a cleaned copy — strip PostUp/PostDown that might conflict
    mkdir -p /etc/wireguard
    sed '/PostUp\|PostDown/d' "$WG_CONF" > /etc/wireguard/wg0.conf
    chmod 600 /etc/wireguard/wg0.conf

    # wg-quick's built-in fwmark routing tries sysctl which is read-only
    # in containers. Docker --sysctl already sets it. Wrap sysctl to
    # succeed silently on read-only errors (standard container pattern).
    if [ ! -f /usr/local/bin/sysctl.real ]; then
        mv /sbin/sysctl /usr/local/bin/sysctl.real 2>/dev/null || true
        cat > /sbin/sysctl << 'WRAPPER'
#!/bin/sh
/usr/local/bin/sysctl.real "$@" 2>/dev/null || true
WRAPPER
        chmod +x /sbin/sysctl
    fi

    # --- Determine WireGuard implementation ---
    WG_USERSPACE=${WG_USERSPACE:-auto}
    WG_IMPL="kernel"

    if [ "$WG_USERSPACE" = "userspace" ]; then
        export WG_QUICK_USERSPACE_IMPLEMENTATION=wireguard-go
        WG_IMPL="userspace"
        echo "[tunnelvision] WireGuard: userspace mode (wireguard-go)"
    elif [ "$WG_USERSPACE" = "kernel" ]; then
        echo "[tunnelvision] WireGuard: kernel mode (required)"
    else
        # auto: probe for kernel module availability
        if ip link add wg-probe type wireguard 2>/dev/null; then
            ip link del wg-probe 2>/dev/null || true
            echo "[tunnelvision] WireGuard: kernel module detected"
        else
            export WG_QUICK_USERSPACE_IMPLEMENTATION=wireguard-go
            WG_IMPL="userspace"
            echo "[tunnelvision] WireGuard: kernel module unavailable, falling back to wireguard-go"
        fi
    fi

    echo "$WG_IMPL" > /var/run/tunnelvision/wg_implementation

    wg-quick up wg0

    if ! ip link show wg0 &>/dev/null; then
        echo "[tunnelvision] ERROR: WireGuard interface wg0 failed"
        echo "error" > /var/run/tunnelvision/vpn_state
        exit 1
    fi

    WG_IP=$(ip -4 addr show wg0 | awk '/inet / {print $2}' | cut -d/ -f1)
    WG_ENDPOINT=$(wg show wg0 endpoints | awk '{print $2}' | head -1)
    VPN_INTERFACE="wg0"

    # Set DNS — built-in DNS server overrides everything when enabled
    DNS_ENABLED=${DNS_ENABLED:-false}
    if [ "$DNS_ENABLED" = "true" ]; then
        echo "nameserver 127.0.0.1" > /etc/resolv.conf
        echo "[tunnelvision] DNS set to 127.0.0.1 (built-in DNS server)"
    else
        RESOLVED_DNS="${VPN_DNS:-}"
        if [ -z "$RESOLVED_DNS" ]; then
            RESOLVED_DNS=$(grep -i '^\s*DNS' "$WG_CONF" 2>/dev/null | sed 's/.*=\s*//' | tr -d ' ' | cut -d',' -f1)
        fi
        RESOLVED_DNS="${RESOLVED_DNS:-10.64.0.1}"
        echo "nameserver $RESOLVED_DNS" > /etc/resolv.conf
        echo "[tunnelvision] DNS set to $RESOLVED_DNS"
    fi

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
        --script-security 1 \
        "$AUTH_FILE"

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

    TUN_IP=$(ip -4 addr show tun0 | awk '/inet / {print $2}' | cut -d/ -f1)
    VPN_INTERFACE="tun0"

    # Set DNS — built-in DNS server overrides everything when enabled
    DNS_ENABLED=${DNS_ENABLED:-false}
    if [ "$DNS_ENABLED" = "true" ]; then
        echo "nameserver 127.0.0.1" > /etc/resolv.conf
        echo "[tunnelvision] DNS set to 127.0.0.1 (built-in DNS server)"
    else
        RESOLVED_DNS="${VPN_DNS:-}"
        if [ -z "$RESOLVED_DNS" ]; then
            RESOLVED_DNS=$(grep -i 'dhcp-option DNS' "$OVPN_CONF" 2>/dev/null | head -1 | awk '{print $NF}')
        fi
        if [ -n "$RESOLVED_DNS" ]; then
            echo "nameserver $RESOLVED_DNS" > /etc/resolv.conf
            echo "[tunnelvision] DNS set to $RESOLVED_DNS"
        fi
    fi

    echo "up" > /var/run/tunnelvision/vpn_state
    echo "$TUN_IP" > /var/run/tunnelvision/vpn_ip
    echo "$VPN_INTERFACE" > /var/run/tunnelvision/vpn_interface
    date -u +%Y-%m-%dT%H:%M:%SZ > /var/run/tunnelvision/vpn_started_at

    echo "[tunnelvision] OpenVPN up — IP: $TUN_IP"
fi
