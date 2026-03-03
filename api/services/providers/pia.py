"""PIA (Private Internet Access) provider — token-based auth + port forwarding.

PIA uses a different model than Mullvad/IVPN:
- No static WireGuard public keys in the server list
- Authenticate with username/password to get a token
- Exchange token + our generated pubkey with the server to get its pubkey + our IP
- Port forwarding available on select servers (requires periodic keep-alive)

Endpoints used:
- https://serverlist.piaservers.net/vpninfo/servers/v6 — server list with regions
- https://www.privateinternetaccess.com/api/client/v2/token — auth token
- https://<server-ip>:1337/addKey — WireGuard key exchange
- https://<gateway>:19999/getSignature — port forwarding signature
- https://<gateway>:19999/bindPort — port forwarding bind (every 15 min)
"""

import os
import ssl
from datetime import datetime, timezone

import httpx

from api.services.providers.base import (
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
)

# PIA uses self-signed certs on their gateway endpoints
_no_verify = ssl.create_default_context()
_no_verify.check_hostname = False
_no_verify.verify_mode = ssl.CERT_NONE


class PIAProvider(VPNProvider):
    """PIA provider with token auth, key negotiation, and port forwarding."""

    SERVERS_URL = "https://serverlist.piaservers.net/vpninfo/servers/v6"
    TOKEN_URL = "https://www.privateinternetaccess.com/api/client/v2/token"
    WG_PORT = 1337

    def __init__(self):
        self._server_cache: list[ServerInfo] | None = None
        self._cache_time: datetime | None = None
        self._token: str | None = None
        self._token_time: datetime | None = None

    @property
    def name(self) -> str:
        return "pia"

    async def check_connection(self) -> ConnectionCheck:
        """Generic IP check — PIA has no branded check endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://ipwho.is/")
                resp.raise_for_status()
                data = resp.json()

            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                is_vpn_ip=None,  # Can't determine from generic check
                organization=data.get("connection", {}).get("org", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def get_server_info(self, endpoint_ip: str) -> ServerInfo | None:
        """Match endpoint IP to PIA server metadata."""
        servers = await self.list_servers()
        for server in servers:
            if hasattr(server, "_ipv4") and server._ipv4 == endpoint_ip:
                return server
        return None

    async def list_servers(self, country: str | None = None, city: str | None = None) -> list[ServerInfo]:
        """Fetch PIA server list with WireGuard endpoints and port-forward flags."""
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
            for region in data.get("regions", []):
                region_name = region.get("name", "")
                country_name = region.get("country", region_name)
                port_forward = region.get("port_forward", False)

                for wg_server in region.get("servers", {}).get("wg", []):
                    server = ServerInfo(
                        hostname=wg_server.get("cn", ""),
                        country=country_name,
                        country_code=region.get("id", "")[:2].upper(),
                        city=region_name,
                        server_type="wireguard",
                    )
                    server._ipv4 = wg_server.get("ip", "")
                    server._port_forward = port_forward
                    server._region_id = region.get("id", "")
                    servers.append(server)

            self._server_cache = servers
            self._cache_time = now
            return self._filter_servers(servers, country, city)

        except Exception:
            return self._server_cache or []

    async def get_token(self) -> str | None:
        """Authenticate with PIA and get a connection token."""
        # Cache token for 12 hours
        now = datetime.now(timezone.utc)
        if self._token and self._token_time:
            age = (now - self._token_time).total_seconds()
            if age < 43200:
                return self._token

        username = os.getenv("PIA_USER", "")
        password = os.getenv("PIA_PASS", "")
        if not username or not password:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.TOKEN_URL,
                    data={"username": username, "password": password},
                )
                resp.raise_for_status()
                data = resp.json()

            self._token = data.get("token")
            self._token_time = now
            return self._token
        except Exception:
            return None

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
