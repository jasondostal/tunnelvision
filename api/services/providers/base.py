"""Base VPN provider — the interface all providers implement."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


# =============================================================================
# Provider metadata — single source of truth for what a provider is and needs
# =============================================================================

class SetupType(str, Enum):
    """How the user configures this provider."""
    ACCOUNT = "account"     # Enter credentials, browse servers
    PASTE = "paste"         # Paste a WireGuard/OpenVPN config
    SIDECAR = "sidecar"    # Connect to external VPN manager


@dataclass
class CredentialField:
    """A credential or config value the provider needs from the user.

    The setup wizard and settings UI render forms from these declarations.
    No hardcoded field lists elsewhere — this is the schema.
    """
    key: str                    # Storage key, e.g. "private_key", "username"
    label: str                  # Human label, e.g. "WireGuard Private Key"
    field_type: str = "text"    # "text", "password", "textarea"
    required: bool = True
    secret: bool = False        # Mask in API responses / logs
    hint: str = ""              # Placeholder / help text
    env_var: str = ""           # Maps to env var (e.g. "MULLVAD_ACCOUNT")


@dataclass
class ProviderMeta:
    """Everything the system needs to know about a provider.

    Declared once per provider class. The setup wizard, config system,
    settings YAML, and UI all read from this — nothing hardcoded elsewhere.
    """
    id: str                             # "mullvad", "nordvpn"
    display_name: str                   # "Mullvad VPN"
    description: str                    # For setup wizard
    setup_type: SetupType = SetupType.PASTE

    # Capabilities
    supports_server_list: bool = False
    supports_account_check: bool = False
    supports_port_forwarding: bool = False
    supports_wireguard: bool = True
    supports_openvpn: bool = False

    # Credential schema — drives setup wizard + settings dynamically
    credentials: list[CredentialField] = field(default_factory=list)

    # WireGuard defaults
    default_dns: str = ""

    # Server filter capabilities (what this provider's servers can be filtered by)
    filter_capabilities: list[str] = field(default_factory=list)
    # e.g. ["country", "city", "owned_only", "streaming", "p2p", "port_forward"]


# =============================================================================
# Server filtering
# =============================================================================

@dataclass
class ServerFilter:
    """Filter criteria for server selection.

    All fields are optional — omitted means no constraint on that dimension.
    Providers declare which filters they support via ProviderMeta.filter_capabilities.
    """
    country: str | None = None          # country name or code (case-insensitive)
    city: str | None = None             # city name or code (case-insensitive)
    owned_only: bool | None = None      # True = only servers owned by the provider
    p2p: bool | None = None             # P2P / torrenting capability
    streaming: bool | None = None       # Optimized for streaming
    port_forward: bool | None = None    # Port forwarding capable
    secure_core: bool | None = None     # Double-hop / secure core
    multihop: bool | None = None        # Multi-hop routing
    max_load: int | None = None         # Maximum server load % (0-100)


# =============================================================================
# Data models
# =============================================================================

@dataclass
class ServerInfo:
    """Metadata about a VPN server.

    All fields that providers need are typed here — no more dynamic attrs.
    """
    hostname: str = ""
    country: str = ""
    country_code: str = ""
    city: str = ""
    city_code: str = ""
    provider: str = ""          # hosting provider (e.g. "31173 Services AB")
    owned: bool | None = None   # does the VPN company own this server?
    speed_gbps: int | None = None
    server_type: str = ""       # "wireguard", "openvpn", etc.
    fqdn: str = ""

    # Connection data (was previously hacked via dynamic attributes)
    ipv4: str = ""
    ipv6: str = ""
    public_key: str = ""
    port: int = 51820

    # Capabilities
    port_forward: bool = False
    streaming: bool = False
    p2p: bool = False
    multihop: bool = False
    secure_core: bool = False

    # Metrics
    tier: int = 0               # 0 = free, 1 = basic, 2 = plus, etc.
    load: int = 0               # Server load percentage (0-100)

    # Provider-specific extras (escape hatch for rare one-off fields)
    extra: dict = field(default_factory=dict)


class ConnectError(Exception):
    """Raised during the connect pipeline when something goes wrong."""


@dataclass
class PeerConfig:
    """Everything needed to write wg0.conf and establish the tunnel.

    Returned by resolve_connect(). Providers that do key exchange (PIA)
    override resolve_connect(); static-key providers use the default.
    """
    private_key: str
    address: str
    dns: str
    public_key: str     # peer's public key
    endpoint: str       # peer's IP/hostname
    port: int = 51820
    extra: dict = field(default_factory=dict)  # provider-specific (PIA token, server_vip, etc.)


@dataclass
class ConnectionCheck:
    """Result of verifying our VPN connection."""

    ip: str = ""
    country: str = ""
    city: str = ""
    is_vpn_ip: bool | None = None   # None = can't determine
    blacklisted: bool | None = None
    blacklist_results: list[str] = field(default_factory=list)
    organization: str = ""
    checked_at: datetime | None = None


@dataclass
class AccountInfo:
    """VPN account status."""

    expires_at: datetime | None = None
    days_remaining: int | None = None
    active: bool = True


# =============================================================================
# Base provider
# =============================================================================

class VPNProvider(ABC):
    """Abstract VPN provider interface.

    Every provider must implement check_connection() and declare meta.
    The rest are optional — providers that don't have APIs for server lists
    or account checks just inherit the default no-op implementations.
    """

    def __init__(self, config=None):
        self.config = config
        self._server_cache: list[ServerInfo] | None = None
        self._cache_time: datetime | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'mullvad', 'custom')."""
        ...

    @property
    @abstractmethod
    def meta(self) -> ProviderMeta:
        """Provider metadata — capabilities, credentials, setup type."""
        ...

    @abstractmethod
    async def check_connection(self) -> ConnectionCheck:
        """Verify VPN connection and get public IP info."""
        ...

    async def get_server_info(self, endpoint_ip: str) -> ServerInfo | None:
        """Look up metadata for the server we're connected to.

        Default implementation searches the server list by ipv4 match.
        """
        servers = await self.list_servers()
        for server in servers:
            if server.ipv4 == endpoint_ip:
                return server
        return None

    async def get_account_info(self) -> AccountInfo | None:
        """Check account status (expiry, etc.)."""
        return None

    async def list_servers(
        self,
        filter: "ServerFilter | None" = None,
    ) -> list[ServerInfo]:
        """List available servers, optionally filtered.

        Providers with server lists should override _fetch_servers().
        Caching and filtering are handled here.
        """
        from api.constants import PROVIDER_CACHE_TTL

        now = datetime.now(timezone.utc)
        if self._server_cache is not None and self._cache_time:
            age = (now - self._cache_time).total_seconds()
            if age < PROVIDER_CACHE_TTL:
                return self._filter_servers(self._server_cache, filter)

        try:
            servers = await self._fetch_servers()
            self._server_cache = servers
            self._cache_time = now
            return self._filter_servers(servers, filter)
        except Exception:
            return self._filter_servers(self._server_cache or [], filter)

    # ---- Unified connect pipeline methods ----

    async def resolve_connect(self, server: ServerInfo, config) -> PeerConfig:
        """Resolve credentials and build a PeerConfig for connecting.

        Default: read static WG key from config / env / existing wg0.conf.
        Override for providers with custom key exchange (e.g. PIA).
        """
        from api.constants import WG_CONF_PATH

        private_key = config.wireguard_private_key if config else ""
        address = config.wireguard_addresses if config else ""
        default_dns = self.meta.default_dns or "10.64.0.1"
        dns = (config.wireguard_dns if config and config.wireguard_dns else "") or default_dns

        # Fall back to reading existing wg0.conf
        if (not private_key or not address) and WG_CONF_PATH.exists():
            for line in WG_CONF_PATH.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("PrivateKey") and not private_key:
                    private_key = stripped.split("=", 1)[1].strip()
                elif stripped.startswith("Address") and not address:
                    address = stripped.split("=", 1)[1].strip()
                elif stripped.startswith("DNS") and dns == default_dns:
                    dns = stripped.split("=", 1)[1].strip()

        if not private_key:
            raise ConnectError("No WireGuard private key. Set WIREGUARD_PRIVATE_KEY or configure via the setup wizard.")
        if not address:
            raise ConnectError("No WireGuard address. Set WIREGUARD_ADDRESSES or configure via the setup wizard.")

        if not server.ipv4:
            raise ConnectError(f"No IP for server {server.hostname}")

        return PeerConfig(
            private_key=private_key,
            address=address,
            dns=dns,
            public_key=server.public_key,
            endpoint=server.ipv4,
            port=server.port,
        )

    async def post_connect(self, server: ServerInfo, config, peer: PeerConfig) -> None:
        """Optional post-connect actions (port forwarding, etc.)."""

    async def _fetch_servers(self) -> list[ServerInfo]:
        """Fetch the raw server list from the provider API.

        Override this — not list_servers(). Caching and filtering
        are handled by the base class.
        """
        return []

    @staticmethod
    def _filter_servers(
        servers: list[ServerInfo],
        filter: "ServerFilter | None" = None,
    ) -> list[ServerInfo]:
        """Filter servers by all criteria in ServerFilter. Case-insensitive for strings."""
        if not filter:
            return servers

        result = servers

        if filter.country:
            c = filter.country.lower()
            result = [s for s in result if s.country_code.lower() == c or s.country.lower() == c]

        if filter.city:
            ci = filter.city.lower()
            result = [s for s in result if s.city_code.lower() == ci or s.city.lower() == ci]

        if filter.owned_only:
            result = [s for s in result if s.owned is True]

        if filter.p2p is not None:
            result = [s for s in result if s.p2p == filter.p2p]

        if filter.streaming is not None:
            result = [s for s in result if s.streaming == filter.streaming]

        if filter.port_forward is not None:
            result = [s for s in result if s.port_forward == filter.port_forward]

        if filter.secure_core is not None:
            result = [s for s in result if s.secure_core == filter.secure_core]

        if filter.multihop is not None:
            result = [s for s in result if s.multihop == filter.multihop]

        if filter.max_load is not None:
            result = [s for s in result if s.load <= filter.max_load]

        return result
