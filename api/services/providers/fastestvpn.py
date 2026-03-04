"""FastestVPN provider — connection check with BYO WireGuard config.

WireGuard setup:
  Contact FastestVPN support at support@fastestvpn.com to request
  WireGuard configuration files for your account. Place the received
  .conf file in /config/wireguard/wg0.conf.
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


class FastestVPNProvider(VPNProvider):
    """FastestVPN provider — BYO WireGuard config with connection monitoring."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "fastestvpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="fastestvpn",
            display_name="FastestVPN",
            description=(
                "Contact FastestVPN support (support@fastestvpn.com) to request "
                "your WireGuard configuration files. Place the .conf file in "
                "/config/wireguard/wg0.conf."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=False,
            credentials=[],
            default_dns="8.8.8.8",
            filter_capabilities=[],
        )

    async def check_connection(self) -> ConnectionCheck:
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
