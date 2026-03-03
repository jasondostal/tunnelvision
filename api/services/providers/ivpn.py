"""IVPN provider — public API integration.

Endpoints used:
- https://api.ivpn.net/v5/servers.json — server list with WireGuard pubkeys
- https://api.ivpn.net/v4/geo-lookup — connection verification, IP, location
"""

from datetime import datetime, timezone

import httpx

from api.services.providers.base import (
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
)


class IVPNProvider(VPNProvider):
    """IVPN provider with server list and connection check."""

    SERVERS_URL = "https://api.ivpn.net/v5/servers.json"
    GEO_URL = "https://api.ivpn.net/v4/geo-lookup"

    def __init__(self):
        self._server_cache: list[ServerInfo] | None = None
        self._cache_time: datetime | None = None

    @property
    def name(self) -> str:
        return "ivpn"

    async def check_connection(self) -> ConnectionCheck:
        """Verify VPN via IVPN geo-lookup — IP, location, isIvpnServer."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.GEO_URL)
                resp.raise_for_status()
                data = resp.json()

            return ConnectionCheck(
                ip=data.get("ip_address", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                is_vpn_ip=data.get("isIvpnServer", False),
                organization=data.get("organization", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def get_server_info(self, endpoint_ip: str) -> ServerInfo | None:
        """Match endpoint IP to IVPN server metadata."""
        servers = await self.list_servers()
        for server in servers:
            if hasattr(server, "_ipv4") and server._ipv4 == endpoint_ip:
                return server
        return None

    async def list_servers(self, country: str | None = None, city: str | None = None) -> list[ServerInfo]:
        """Fetch IVPN WireGuard server list with pubkeys."""
        now = datetime.now(timezone.utc)
        if self._server_cache and self._cache_time:
            age = (now - self._cache_time).total_seconds()
            if age < 3600:
                return self._filter_servers(self._server_cache, country, city)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.SERVERS_URL)
                resp.raise_for_status()
                data = resp.json()

            servers = []
            for gateway in data.get("wireguard", []):
                for host in gateway.get("hosts", []):
                    server = ServerInfo(
                        hostname=host.get("hostname", ""),
                        country=gateway.get("country", ""),
                        country_code=gateway.get("country_code", ""),
                        city=gateway.get("city", ""),
                        provider=host.get("isp", gateway.get("isp", "")),
                        server_type="wireguard",
                        fqdn=host.get("dns_name", ""),
                    )
                    server._ipv4 = host.get("host", "")
                    server._pubkey = host.get("public_key", "")
                    server._port = host.get("multihop_port", 2049)
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
