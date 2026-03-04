#!/bin/bash
# ============================================================================
# TunnelVision — Health Check
# Used by Docker HEALTHCHECK and the /api/v1/health endpoint.
# Exit 0 = healthy, Exit 1 = unhealthy.
# ============================================================================

VPN_ENABLED=${VPN_ENABLED:-true}
WEBUI_PORT=${WEBUI_PORT:-8080}
API_PORT=${API_PORT:-8081}
API_ENABLED=${API_ENABLED:-true}

errors=0

# --- Check VPN (if enabled) ---
if [ "$VPN_ENABLED" = "true" ]; then
    # WireGuard interface exists
    if ! ip link show wg0 &>/dev/null; then
        echo "UNHEALTHY: WireGuard interface wg0 not found"
        errors=$((errors + 1))
    fi

    # WireGuard has a handshake (connected)
    LAST_HANDSHAKE=$(wg show wg0 latest-handshakes 2>/dev/null | awk '{print $2}' | head -1)
    if [ -z "$LAST_HANDSHAKE" ] || [ "$LAST_HANDSHAKE" = "0" ]; then
        echo "UNHEALTHY: No WireGuard handshake"
        errors=$((errors + 1))
    fi

    # Killswitch rules loaded (if enabled)
    KILLSWITCH_STATE=$(cat /var/run/tunnelvision/killswitch_state 2>/dev/null)
    if [ "$KILLSWITCH_STATE" = "active" ]; then
        if ! nft list table ip tunnelvision &>/dev/null; then
            echo "UNHEALTHY: Killswitch rules not loaded"
            errors=$((errors + 1))
        fi
    fi
fi

# --- Check qBittorrent WebUI (if enabled) ---
QBT_ENABLED=${QBT_ENABLED:-true}
if [ "$QBT_ENABLED" = "true" ]; then
    if ! curl -sf -o /dev/null --max-time 5 "http://localhost:${WEBUI_PORT}"; then
        echo "UNHEALTHY: qBittorrent WebUI not responding on port ${WEBUI_PORT}"
        errors=$((errors + 1))
    fi
fi

# --- Check DNS (if enabled) ---
DNS_ENABLED=${DNS_ENABLED:-false}
if [ "$DNS_ENABLED" = "true" ]; then
    if ! dig @127.0.0.1 example.com +short +time=3 +tries=1 &>/dev/null; then
        echo "UNHEALTHY: DNS server not responding"
        errors=$((errors + 1))
    fi
fi

# --- Check API (if enabled) ---
if [ "$API_ENABLED" = "true" ]; then
    if ! curl -sf -o /dev/null --max-time 5 "http://localhost:${API_PORT}/api/v1/health"; then
        echo "UNHEALTHY: API not responding on port ${API_PORT}"
        errors=$((errors + 1))
    fi
fi

if [ $errors -gt 0 ]; then
    exit 1
fi

echo "HEALTHY"
exit 0
