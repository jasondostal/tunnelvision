"""Surfshark VPN provider — server list + connection check.

Endpoints used:
- https://api.surfshark.com/v3/server/clusters — server list with WireGuard
  hostname and country metadata
- https://ipwho.is/ — connection check

WireGuard setup:
  Go to my.surfshark.com → VPN → Manual Setup → WireGuard.
  Generate a key pair, download the config for the server you want,
  and place it in /config/wireguard/wg0.conf.
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


class SurfsharkProvider(VPNProvider):
    """Surfshark VPN provider — server browsing with BYO WireGuard config."""

    SERVERS_URL = "https://api.surfshark.com/v3/server/clusters"
    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "surfshark"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="surfshark",
            display_name="Surfshark",
            description=(
                "Go to my.surfshark.com → VPN → Manual Setup → WireGuard. "
                "Generate a WireGuard key pair and download the config for the server you want."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=True,
            credentials=[],
            default_dns="100.64.0.4",
            filter_capabilities=["country", "city"],
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
        """Fetch Surfshark server cluster list."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.SERVERS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for cluster in data:
            hostname = cluster.get("connectionName", cluster.get("hostname", ""))
            country_name = cluster.get("country", "")
            country_code = cluster.get("countryCode", cluster.get("country_code", ""))
            city_name = cluster.get("location", cluster.get("city", ""))
            ipv4 = cluster.get("ip", "")
            load = cluster.get("load", 0)

            if not hostname:
                continue

            servers.append(ServerInfo(
                hostname=hostname,
                country=country_name,
                country_code=country_code,
                city=city_name,
                server_type="wireguard",
                ipv4=ipv4,
                load=load,
            ))

        return servers
