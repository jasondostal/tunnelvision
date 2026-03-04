"""ExpressVPN provider — connection check with BYO config.

Endpoints used:
- https://ipwho.is/ — connection check (ExpressVPN has no public check endpoint)

ExpressVPN does not expose a public API for WireGuard config generation
or server lists. Use the ExpressVPN app or website to download your
WireGuard config and place it in /config/wireguard/wg0.conf.
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


class ExpressVPNProvider(VPNProvider):
    """ExpressVPN provider — BYO WireGuard config with connection monitoring."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "expressvpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="expressvpn",
            display_name="ExpressVPN",
            description=(
                "Download your WireGuard config from the ExpressVPN website or app "
                "and place it in /config/wireguard/wg0.conf."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=False,
            credentials=[],
            default_dns="8.8.8.8",
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
