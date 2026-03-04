"""Privado VPN provider — connection check with BYO WireGuard config.

WireGuard setup:
  Log into your Privado VPN account and navigate to the manual setup
  section to obtain your WireGuard configuration file. Place it in
  /config/wireguard/wg0.conf.
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


class PrivadoProvider(VPNProvider):
    """Privado VPN provider — BYO WireGuard config with connection monitoring."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "privado"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="privado",
            display_name="Privado VPN",
            description=(
                "Log into your Privado VPN account to download your WireGuard "
                "configuration file. Place it in /config/wireguard/wg0.conf."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=False,
            credentials=[],
            default_dns="1.1.1.1",
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
