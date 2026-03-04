"""TorGuard VPN provider — connection check with BYO config.

TorGuard does not expose a public server list API. Server configs are
generated through the TorGuard member portal config generator.

WireGuard setup:
  Log into your TorGuard account → Tools → Config Generator.
  Select WireGuard as the tunnel type, choose a server location,
  enter your VPN username, and download the generated .conf file.
  Place it in /config/wireguard/wg0.conf.

Important: TorGuard WireGuard configs expire after 12-24 hours by design.
You must regenerate your config periodically from the member portal.
TorGuard uses port 1443 (not the standard 51820) on all WireGuard servers.
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


class TorGuardProvider(VPNProvider):
    """TorGuard VPN provider — BYO config with connection monitoring."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "torguard"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="torguard",
            display_name="TorGuard",
            description=(
                "Generate your config at torguard.net → Tools → Config Generator. "
                "Select WireGuard, choose a server, and download the .conf file. "
                "Configs expire after 12-24 hours — regenerate as needed."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=False,
            credentials=[],
            default_dns="1.1.1.1",
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
