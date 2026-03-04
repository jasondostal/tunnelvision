"""Mullvad VPN provider — full API integration.

Endpoints used:
- https://am.i.mullvad.net/json — connection verification, IP, location, blacklist
- https://api.mullvad.net/www/relays/wireguard/ — server list with metadata
- https://api.mullvad.net/public/accounts/v1/{account}/ — account expiry
"""

from datetime import datetime, timezone

import httpx

from api.services.providers.base import (
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
    AccountInfo,
)


class MullvadProvider(VPNProvider):
    """Mullvad VPN provider with rich API integration."""

    CHECK_URL = "https://am.i.mullvad.net/json"
    RELAYS_URL = "https://api.mullvad.net/www/relays/wireguard/"
    ACCOUNT_URL = "https://api.mullvad.net/public/accounts/v1/{account}/"

    def __init__(self):
        self._server_cache: list[ServerInfo] | None = None
        self._cache_time: datetime | None = None

    @property
    def name(self) -> str:
        return "mullvad"

    async def check_connection(self) -> ConnectionCheck:
        """Verify VPN via am.i.mullvad.net — IP, location, blacklist status."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.CHECK_URL)
                resp.raise_for_status()
                data = resp.json()

            blacklist_data = data.get("blacklisted", {})

            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                is_vpn_ip=data.get("mullvad_exit_ip", False),
                blacklisted=blacklist_data.get("blacklisted", False) if blacklist_data else None,
                blacklist_results=blacklist_data.get("results", []) if blacklist_data else [],
                organization=data.get("organization", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def get_server_info(self, endpoint_ip: str) -> ServerInfo | None:
        """Match endpoint IP to Mullvad server metadata."""
        servers = await self.list_servers()
        for server in servers:
            # Check if endpoint_ip matches any server's IPv4
            if hasattr(server, "_ipv4") and server._ipv4 == endpoint_ip:
                return server
        return None

    async def get_account_info(self) -> AccountInfo | None:
        """Check Mullvad account expiry."""
        account = self.config.mullvad_account if self.config else ""
        if not account:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.ACCOUNT_URL.format(account=account))
                resp.raise_for_status()
                data = resp.json()

            expiry_str = data.get("expiry", "")
            if expiry_str:
                expires_at = datetime.fromisoformat(expiry_str)
                now = datetime.now(timezone.utc)
                days_remaining = (expires_at - now).days

                return AccountInfo(
                    expires_at=expires_at,
                    days_remaining=days_remaining,
                    active=days_remaining > 0,
                )
        except Exception:
            pass

        return None

    async def list_servers(self, country: str | None = None, city: str | None = None) -> list[ServerInfo]:
        """Fetch Mullvad WireGuard server list with full metadata."""
        # Cache for 1 hour
        now = datetime.now(timezone.utc)
        if self._server_cache and self._cache_time:
            age = (now - self._cache_time).total_seconds()
            if age < 3600:
                return self._filter_servers(self._server_cache, country, city)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.RELAYS_URL)
                resp.raise_for_status()
                data = resp.json()

            servers = []
            for relay in data:
                if not relay.get("active", False):
                    continue

                server = ServerInfo(
                    hostname=relay.get("hostname", ""),
                    country=relay.get("country_name", ""),
                    country_code=relay.get("country_code", ""),
                    city=relay.get("city_name", ""),
                    city_code=relay.get("city_code", ""),
                    provider=relay.get("provider", ""),
                    owned=relay.get("owned"),
                    speed_gbps=relay.get("network_port_speed"),
                    server_type=relay.get("type", "wireguard"),
                    fqdn=relay.get("fqdn", ""),
                )
                # Store IPv4 for endpoint matching (not in the dataclass, just an attr)
                server._ipv4 = relay.get("ipv4_addr_in", "")
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
            result = [s for s in result if s.country_code == country_lower or s.country.lower() == country_lower]
        if city:
            city_lower = city.lower()
            result = [s for s in result if s.city_code == city_lower or s.city.lower() == city_lower]
        return result
