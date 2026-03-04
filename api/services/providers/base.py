"""Base VPN provider — the interface all providers implement."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ServerInfo:
    """Metadata about the VPN server we're connected to."""

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


class VPNProvider(ABC):
    """Abstract VPN provider interface.

    Every provider must implement ip_check(). The rest are optional —
    providers that don't have APIs for server lists or account checks
    just inherit the default no-op implementations.
    """

    def __init__(self, config=None):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'mullvad', 'custom')."""
        ...

    @abstractmethod
    async def check_connection(self) -> ConnectionCheck:
        """Verify VPN connection and get public IP info."""
        ...

    async def get_server_info(self, endpoint_ip: str) -> ServerInfo | None:
        """Look up metadata for the server we're connected to.

        Args:
            endpoint_ip: The WireGuard endpoint IP from `wg show`.

        Returns:
            ServerInfo if the provider can identify the server, None otherwise.
        """
        return None

    async def get_account_info(self) -> AccountInfo | None:
        """Check account status (expiry, etc.).

        Returns:
            AccountInfo if the provider supports account checks, None otherwise.
        """
        return None

    async def list_servers(self, country: str | None = None, city: str | None = None) -> list[ServerInfo]:
        """List available servers, optionally filtered.

        Returns:
            List of available servers. Empty list if provider doesn't support listing.
        """
        return []
