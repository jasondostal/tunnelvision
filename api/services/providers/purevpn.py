"""PureVPN provider — connection check with BYO WireGuard config.

WireGuard setup:
  Log into your PureVPN Member Area → Manual Configuration → select your
  country and city → Download → choose WireGuard. Place the downloaded
  .conf in /config/wireguard/wg0.conf.

Important: PureVPN-generated WireGuard configs expire after 30 minutes.
You must regenerate from the Member Area each time you restart.
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


class PureVPNProvider(VPNProvider):
    """PureVPN provider — BYO WireGuard config with connection monitoring."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "purevpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="purevpn",
            display_name="PureVPN",
            description=(
                "Go to your PureVPN Member Area → Manual Configuration → select "
                "country/city → Download → WireGuard. "
                "Warning: configs expire after 30 minutes and must be regenerated."
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
