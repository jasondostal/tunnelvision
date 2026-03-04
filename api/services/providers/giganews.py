"""Giganews VPN provider — powered by VyprVPN.

Giganews is a Usenet provider that bundles VyprVPN for its members.
VyprVPN WireGuard is available through the VyprVPN app only — manual
WireGuard config export is not publicly documented.

For OpenVPN: Giganews VyprVPN servers use the format
{city}.giganews.com. Download configs from your Giganews account
or the VyprVPN app. Set VPN_TYPE=openvpn.
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


class GiganewsProvider(VPNProvider):
    """Giganews VPN provider — VyprVPN-powered, BYO config."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "giganews"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="giganews",
            display_name="Giganews VPN",
            description=(
                "Giganews bundles VyprVPN. WireGuard is app-only — "
                "manual config export is not available. For container use, "
                "download an OpenVPN config via the VyprVPN app or your "
                "Giganews account. Set VPN_TYPE=openvpn."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=False,
            supports_wireguard=False,
            supports_openvpn=True,
            credentials=[],
            default_dns="",
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
