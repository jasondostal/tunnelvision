"""Windscribe VPN provider — server list + connection check.

Endpoints used:
- https://assets.windscribe.com/desktop/v2/serverlist/en/1 — public server list
  with country, city, hostname, and P2P flag
- https://ipwho.is/ — connection check (no Windscribe-specific endpoint)

WireGuard setup:
  Download your WireGuard config from windscribe.com → My Account →
  WireGuard Config Generator. Place it in /config/wireguard/wg0.conf.
  Use this server list to find the location you want, then download
  the matching config from the Windscribe site.
"""

from datetime import datetime, timezone

from api.constants import TIMEOUT_FETCH, http_client
from api.services.providers.base import (
    ProviderMeta,
    SetupType,
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
)


class WindscribeProvider(VPNProvider):
    """Windscribe VPN provider — server browsing with BYO WireGuard config."""

    SERVERS_URL = "https://assets.windscribe.com/desktop/v2/serverlist/en/1"
    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "windscribe"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="windscribe",
            display_name="Windscribe",
            description=(
                "Download your WireGuard config from windscribe.com → My Account → "
                "WireGuard Config Generator. Paste or upload it here."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=True,
            credentials=[],
            default_dns="10.255.255.1",
            filter_capabilities=["country", "city", "p2p"],
        )

    async def check_connection(self) -> ConnectionCheck:
        """Verify VPN via generic geo-IP."""
        try:
            async with http_client() as client:
                resp = await client.get(self.GEO_URL)
                resp.raise_for_status()
                data = resp.json()
            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                organization=data.get("connection", {}).get("org", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def _fetch_servers(self) -> list[ServerInfo]:
        """Fetch Windscribe public server list with country, city, P2P flags."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.SERVERS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for region in data.get("data", {}).get("info", []):
            country_name = region.get("name", "")
            country_code = region.get("country_code", "")
            p2p = bool(region.get("p2p", 0))

            for node in region.get("nodes", []):
                hostname = node.get("hostname", "")
                if not hostname:
                    continue
                servers.append(ServerInfo(
                    hostname=hostname,
                    country=country_name,
                    country_code=country_code,
                    server_type="wireguard",
                    p2p=p2p,
                ))

        return servers
