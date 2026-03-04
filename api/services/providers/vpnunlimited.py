"""VPN Unlimited (KeepSolid) provider — connection check with BYO WireGuard config.

WireGuard setup:
  Log into my.keepsolid.com → Manual Configurations → Create configuration.
  Enter a device name, select your server location, choose WireGuard
  protocol, and click Generate. Download the .conf file and place it
  in /config/wireguard/wg0.conf.
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


class VPNUnlimitedProvider(VPNProvider):
    """VPN Unlimited (KeepSolid) provider — BYO WireGuard config."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "vpnunlimited"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="vpnunlimited",
            display_name="VPN Unlimited",
            description=(
                "Go to my.keepsolid.com → Manual Configurations → Create configuration. "
                "Name your device, select a server location, choose WireGuard, "
                "and click Generate. Place the downloaded .conf in /config/wireguard/wg0.conf."
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
