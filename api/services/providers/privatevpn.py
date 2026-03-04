"""PrivateVPN provider — connection check with BYO config.

PrivateVPN does not expose a public server list API. Server configs are
generated through the PrivateVPN account portal.

WireGuard setup:
  Log into your PrivateVPN account → WireGuard Configurations.
  Select a server location and click Generate Config. Download the
  generated .conf file and place it in /config/wireguard/wg0.conf.

Server hostnames follow the pattern: {country_code}-{city_code}.pvdata.host
"""

from datetime import datetime, timezone

from api.constants import http_client
from api.services.providers.base import (
    ProviderMeta,
    SetupType,
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
)


class PrivateVPNProvider(VPNProvider):
    """PrivateVPN provider — BYO config with connection monitoring."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "privatevpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="privatevpn",
            display_name="PrivateVPN",
            description=(
                "Log into your PrivateVPN account → WireGuard Configurations. "
                "Select a server location, download the generated .conf file, "
                "and place it in /config/wireguard/wg0.conf."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=False,
            credentials=[],
            default_dns="8.8.8.8",
            filter_capabilities=[],
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
        return []
