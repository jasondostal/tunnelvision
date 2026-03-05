"""IPVanish provider — server browser + connection check.

Endpoints used:
- https://www.ipvanish.com/api/servers.geojson — public server list
  with hostname, country, city, load, and online status
- https://ipwho.is/ — connection check

WireGuard setup:
  Log into your IPVanish account → Service Management → WireGuard.
  Select a server location and click Generate. Download the .conf file
  and place it in /config/wireguard/wg0.conf.

Note: IPVanish-generated WireGuard configs are valid for 30 days.
Regenerate in your account portal before they expire.
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


class IPVanishProvider(VPNProvider):
    """IPVanish provider — server browser with BYO WireGuard config."""

    SERVERS_URL = "https://www.ipvanish.com/api/servers.geojson"
    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "ipvanish"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="ipvanish",
            display_name="IPVanish",
            description=(
                "Log into your IPVanish account → Service Management → WireGuard. "
                "Select a server, click Generate, and download the .conf file. "
                "Note: generated configs expire after 30 days."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=True,
            credentials=[],
            default_dns="8.8.8.8",
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
        """Fetch IPVanish server list from public GeoJSON API."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.SERVERS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            if props.get("online", True) is not False and not props.get("hostname"):
                continue

            hostname = props.get("hostname", "")
            if not hostname:
                continue

            servers.append(ServerInfo(
                hostname=hostname,
                country=props.get("title", ""),
                country_code=props.get("countryCode", ""),
                city=props.get("title", ""),
                server_type="wireguard",
                load=props.get("capacity", 0),
            ))

        return servers
