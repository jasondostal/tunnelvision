"""SlickVPN provider — connection check with BYO WireGuard config.

Note: SlickVPN is no longer accepting new subscriptions. Existing
subscribers can continue to use the service.

WireGuard setup:
  Log into your SlickVPN dashboard to download your WireGuard
  configuration file. Place it in /config/wireguard/wg0.conf.
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


class SlickVPNProvider(VPNProvider):
    """SlickVPN provider — BYO WireGuard config with connection monitoring."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "slickvpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="slickvpn",
            display_name="SlickVPN",
            description=(
                "SlickVPN is no longer accepting new subscribers. "
                "Existing subscribers: log into your SlickVPN dashboard "
                "to download your WireGuard config and place it in "
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
