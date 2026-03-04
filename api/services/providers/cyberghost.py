"""CyberGhost VPN provider — connection check with BYO OpenVPN config.

CyberGhost WireGuard is available only through their proprietary apps
(Windows, Android, iOS). Manual WireGuard config export is not supported.
For router and container deployments, CyberGhost provides OpenVPN configs
through their account portal.

Setup:
  For OpenVPN: log into your CyberGhost account → My Devices →
  Configure Device → set up manually. Download the OpenVPN config
  and place it in /config/openvpn/. Set VPN_TYPE=openvpn.

  For WireGuard: use the CyberGhost app — manual config generation
  is not available for WireGuard.
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


class CyberGhostProvider(VPNProvider):
    """CyberGhost VPN provider — OpenVPN via BYO config (WireGuard app-only)."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "cyberghost"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="cyberghost",
            display_name="CyberGhost",
            description=(
                "CyberGhost WireGuard is only available through their apps — "
                "manual config export is not supported. For container use, "
                "download an OpenVPN config from your CyberGhost account portal "
                "and place it in /config/openvpn/. Set VPN_TYPE=openvpn."
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
