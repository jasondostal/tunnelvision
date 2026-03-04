"""VyprVPN provider — connection check with BYO config.

VyprVPN supports WireGuard through their native apps (Windows, macOS,
Android, iOS). Manual WireGuard config export is not publicly documented.

For OpenVPN: configs are available at account.vyprvpn.com.
For WireGuard: use the VyprVPN app.

Note: Giganews members receive VyprVPN as a bundled service.
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


class VyprVPNProvider(VPNProvider):
    """VyprVPN provider — BYO config with connection monitoring."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "vyprvpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="vyprvpn",
            display_name="VyprVPN",
            description=(
                "VyprVPN WireGuard is available through their native apps only — "
                "manual config export is not documented. For container use, "
                "download an OpenVPN config from account.vyprvpn.com and place "
                "it in /config/openvpn/. Set VPN_TYPE=openvpn."
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
