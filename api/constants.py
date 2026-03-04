"""TunnelVision constants — single source of truth.

Every magic number, path, port default, timeout, and state string lives here.
Import from this module. Do not hardcode values elsewhere.
"""

from enum import Enum
from pathlib import Path

import httpx


# =============================================================================
# Paths
# =============================================================================

CONFIG_DIR = Path("/config")
WIREGUARD_DIR = CONFIG_DIR / "wireguard"
OPENVPN_DIR = CONFIG_DIR / "openvpn"
WG_CONF_PATH = WIREGUARD_DIR / "wg0.conf"
SETTINGS_PATH = CONFIG_DIR / "tunnelvision.yml"
STATE_DIR = Path("/var/run/tunnelvision")
HISTORY_PATH = CONFIG_DIR / "connection-history.json"


# =============================================================================
# Default ports
# =============================================================================

WEBUI_PORT = 8080
API_PORT = 8081
HTTP_PROXY_PORT = 8888
SOCKS_PROXY_PORT = 1080
MQTT_PORT = 1883
GLUETUN_PORT = 8000


# =============================================================================
# URLs
# =============================================================================

GLUETUN_DEFAULT_URL = f"http://gluetun:{GLUETUN_PORT}"


# =============================================================================
# Timeouts (seconds) — httpx / network
# =============================================================================

TIMEOUT_QUICK = 5.0       # Fast probes (gluetun sidecar, system commands)
TIMEOUT_DEFAULT = 10.0    # Standard API calls (provider checks, notifications)
TIMEOUT_FETCH = 15.0      # Larger downloads (server lists, blocklists)
TIMEOUT_DOWNLOAD = 30.0   # Heavy downloads (speedtest, SSE keepalive)


# =============================================================================
# Timeouts (seconds) — subprocess
# =============================================================================

SUBPROCESS_TIMEOUT_QUICK = 5
SUBPROCESS_TIMEOUT_DEFAULT = 10
SUBPROCESS_TIMEOUT_LONG = 15
SUBPROCESS_TIMEOUT_VPN = 30


# =============================================================================
# Cache TTLs (seconds)
# =============================================================================

PROVIDER_CACHE_TTL = 3600       # 1 hour — server lists
PIA_TOKEN_CACHE_TTL = 43200     # 12 hours — PIA auth tokens


# =============================================================================
# Intervals (seconds) — configurable via settings, these are defaults
# =============================================================================

HEALTH_CHECK_INTERVAL = 30
PORT_FORWARD_INTERVAL = 900         # PIA/Proton port keep-alive (15 min)
DNS_BLOCKLIST_REFRESH = 86400       # Blocklist re-download (24 hours)
DNS_STATS_INTERVAL = 60             # Write DNS stats to state files
DNS_CACHE_SIZE = 4096               # Max cached DNS responses

SSE_KEEPALIVE_INTERVAL = 30         # SSE connection heartbeat


# =============================================================================
# Watchdog
# =============================================================================

HANDSHAKE_STALE_SECONDS = 180       # WG handshake age → stale
RECONNECT_THRESHOLD = 3             # Consecutive failures → reconnect
COOLDOWN_SECONDS = 300              # All configs exhausted → wait 5 min


# =============================================================================
# NAT-PMP (RFC 6886)
# =============================================================================

NATPMP_PORT = 5351
NATPMP_LIFETIME = 60                # Mapping lifetime in seconds
NATPMP_REFRESH_INTERVAL = 45        # Refresh before lifetime expires


# =============================================================================
# State enums — use these instead of raw strings
# =============================================================================

class VpnState(str, Enum):
    """VPN tunnel state."""
    UP = "up"
    DOWN = "down"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class KillswitchState(str, Enum):
    """Killswitch state."""
    ACTIVE = "active"
    DISABLED = "disabled"


class ServiceState(str, Enum):
    """Generic service state (DNS, proxies, etc.)."""
    RUNNING = "running"
    DISABLED = "disabled"
    ERROR = "error"


class WatchdogState(str, Enum):
    """Watchdog state machine states."""
    IDLE = "idle"
    MONITORING = "monitoring"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    FAILING_OVER = "failing_over"
    COOLDOWN = "cooldown"


class HealthState(str, Enum):
    """Boolean-ish health state stored as strings."""
    TRUE = "true"
    FALSE = "false"


# =============================================================================
# Helpers
# =============================================================================

def activate_wg_config(config_path: Path) -> None:
    """Symlink a WireGuard config to wg0.conf.

    This is the single place this logic lives. Previously duplicated in
    connect.py, setup.py, and watchdog.py.
    """
    WG_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    WG_CONF_PATH.unlink(missing_ok=True)
    WG_CONF_PATH.symlink_to(config_path)


def http_client(
    timeout: float = TIMEOUT_DEFAULT,
    verify: bool = True,
    **kwargs,
) -> httpx.AsyncClient:
    """Create a preconfigured httpx.AsyncClient.

    Centralizes timeout and TLS defaults. Use instead of raw
    ``httpx.AsyncClient(timeout=...)`` everywhere.
    """
    return httpx.AsyncClient(timeout=timeout, verify=verify, **kwargs)
