#!/bin/bash
# ============================================================================
# TunnelVision — One-liner Install Script
# Usage: curl -fsSL https://raw.githubusercontent.com/jasondostal/tunnelvision/main/scripts/install.sh | bash
# ============================================================================

set -e

INSTALL_DIR="${INSTALL_DIR:-./tunnelvision}"

echo ""
echo "  ╔═══════════════════════════════╗"
echo "  ║       TunnelVision Setup      ║"
echo "  ╚═══════════════════════════════╝"
echo ""

# Check prerequisites
for cmd in docker; do
    if ! command -v $cmd &>/dev/null; then
        echo "Error: $cmd is required but not installed."
        exit 1
    fi
done

if ! docker compose version &>/dev/null; then
    echo "Error: docker compose (v2) is required."
    exit 1
fi

# Create directory structure
echo "Creating $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/wireguard"

# Download docker-compose.yml
echo "Downloading docker-compose.yml..."
curl -fsSL -o "$INSTALL_DIR/docker-compose.yml" \
    "https://raw.githubusercontent.com/jasondostal/tunnelvision/main/docker-compose.yml"

# Check for WireGuard config
echo ""
if [ -z "$(ls "$INSTALL_DIR/wireguard/"*.conf 2>/dev/null)" ]; then
    echo "Next steps:"
    echo ""
    echo "  1. Copy your WireGuard config:"
    echo "     cp /path/to/wg0.conf $INSTALL_DIR/wireguard/"
    echo ""
    echo "  2. Start TunnelVision:"
    echo "     cd $INSTALL_DIR && docker compose up -d"
    echo ""
    echo "  3. Open the dashboard:"
    echo "     http://localhost:8081"
    echo ""
    echo "  Or skip the config and use the setup wizard in the browser."
else
    echo "WireGuard config found. Starting TunnelVision..."
    cd "$INSTALL_DIR"
    docker compose up -d
    echo ""
    echo "TunnelVision is running!"
    echo "  Dashboard: http://localhost:8081"
    echo "  qBit WebUI: http://localhost:8080"
    echo "  API Docs:   http://localhost:8081/api/docs"
fi
echo ""
