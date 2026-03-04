"""HideMyAss (HMA) VPN provider — connection check with BYO OpenVPN config.

HMA WireGuard support is limited to their Windows app and is not available
for manual configuration. For container deployments, use OpenVPN.

Setup:
  Log into your HMA account → Servers → Manual setup → OpenVPN.
  Download the config for your chosen server location and place it
  in /config/openvpn/. Set VPN_TYPE=openvpn.
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


class HideMyAssProvider(VPNProvider):
    """HideMyAss VPN provider — OpenVPN via BYO config."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "hidemyass"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="hidemyass",
            display_name="HideMyAss",
            description=(
                "HMA WireGuard is app-only (Windows). For container use, "
                "download an OpenVPN config from your HMA account → Servers → "
                "Manual setup. Place it in /config/openvpn/. Set VPN_TYPE=openvpn."
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
