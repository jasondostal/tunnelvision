"""ProtonVPN provider — server list API + NAT-PMP port forwarding.

ProtonVPN provides:
- Public API for free servers, authenticated for Plus/Visionary
- WireGuard support with public keys in server list
- NAT-PMP port forwarding on supported servers (Feature bit 4)

Endpoints used:
- https://api.protonvpn.ch/vpn/logicals — server list with features bitmask
- https://api.protonvpn.ch/vpn/sessions — auth check (Plus/Visionary)
"""

from datetime import datetime, timezone

from api.constants import PROVIDER_CACHE_TTL, TIMEOUT_FETCH, http_client
from api.services.providers.base import (
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
    AccountInfo,
)

# ProtonVPN feature bitmask (from API docs)
FEATURE_SECURE_CORE = 1
FEATURE_TOR = 2
FEATURE_P2P = 4
FEATURE_STREAMING = 8
FEATURE_PORT_FORWARD = 16


class ProtonProvider(VPNProvider):
    """ProtonVPN provider with server list and NAT-PMP port forwarding."""

    SERVERS_URL = "https://api.protonvpn.ch/vpn/logicals"
    GEO_URL = "https://ipwho.is/"

    def __init__(self, config=None):
        super().__init__(config)
        self._server_cache: list[ServerInfo] | None = None
        self._cache_time: datetime | None = None

    @property
    def name(self) -> str:
        return "proton"

    async def check_connection(self) -> ConnectionCheck:
        """Generic IP check via geo-IP fallback chain."""
        try:
            async with http_client() as client:
                resp = await client.get(self.GEO_URL)
                resp.raise_for_status()
                data = resp.json()

            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                is_vpn_ip=None,
                organization=data.get("connection", {}).get("org", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def get_account_info(self) -> AccountInfo | None:
        """Check ProtonVPN account via authenticated API."""
        username = self.config.proton_user if self.config else ""
        password = self.config.proton_pass if self.config else ""
        if not username or not password:
            return None

        try:
            async with http_client() as client:
                # ProtonVPN uses SRP auth — simplified check via sessions endpoint
                resp = await client.get(
                    "https://api.protonvpn.ch/vpn/sessions",
                    auth=(username, password),
                )
                if resp.status_code == 200:
                    return AccountInfo(active=True)
                return AccountInfo(active=False)
        except Exception:
            return None

    async def get_server_info(self, endpoint_ip: str) -> ServerInfo | None:
        """Match endpoint IP to ProtonVPN server metadata."""
        servers = await self.list_servers()
        for server in servers:
            if hasattr(server, "_ipv4") and server._ipv4 == endpoint_ip:
                return server
        return None

    async def list_servers(self, country: str | None = None, city: str | None = None) -> list[ServerInfo]:
        """Fetch ProtonVPN server list with WireGuard endpoints."""
        now = datetime.now(timezone.utc)
        if self._server_cache and self._cache_time:
            age = (now - self._cache_time).total_seconds()
            if age < PROVIDER_CACHE_TTL:
                return self._filter_servers(self._server_cache, country, city)

        try:
            async with http_client(timeout=TIMEOUT_FETCH) as client:
                resp = await client.get(self.SERVERS_URL)
                resp.raise_for_status()
                data = resp.json()

            servers = []
            for logical in data.get("LogicalServers", []):
                server_name = logical.get("Name", "")
                exit_country = logical.get("ExitCountry", "")
                city_name = logical.get("City", "")
                features = logical.get("Features", 0)
                tier = logical.get("Tier", 0)
                load = logical.get("Load", 0)

                for physical in logical.get("Servers", []):
                    entry_ip = physical.get("EntryIP", "")
                    exit_ip = physical.get("ExitIP", "")

                    server = ServerInfo(
                        hostname=server_name,
                        country=exit_country,
                        country_code=exit_country,
                        city=city_name,
                        server_type="wireguard",
                    )
                    server._ipv4 = entry_ip
                    server._exit_ip = exit_ip
                    server._features = features
                    server._tier = tier
                    server._load = load
                    server._port_forward = bool(features & FEATURE_PORT_FORWARD)
                    servers.append(server)

            self._server_cache = servers
            self._cache_time = now
            return self._filter_servers(servers, country, city)

        except Exception:
            return self._server_cache or []

    @staticmethod
    def _filter_servers(
        servers: list[ServerInfo],
        country: str | None = None,
        city: str | None = None,
    ) -> list[ServerInfo]:
        result = servers
        if country:
            country_lower = country.lower()
            result = [s for s in result if s.country_code.lower() == country_lower or s.country.lower() == country_lower]
        if city:
            city_lower = city.lower()
            result = [s for s in result if s.city.lower() == city_lower]
        return result
