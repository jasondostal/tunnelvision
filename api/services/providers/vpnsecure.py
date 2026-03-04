"""VPNSecure provider — OpenVPN only.

VPNSecure does not support WireGuard. Supported protocols are
OpenVPN, HTTP Proxy, Smart DNS, and obfuscation variants.

Setup:
  Download your OpenVPN config from vpnsecure.me → Downloads.
  Place the .conf file in /config/openvpn/ and set
  VPN_TYPE=openvpn in your environment.
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


class VPNSecureProvider(VPNProvider):
    """VPNSecure provider — OpenVPN only, no WireGuard."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "vpnsecure"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="vpnsecure",
            display_name="VPNSecure",
            description=(
                "VPNSecure does not support WireGuard. Download your OpenVPN "
                "config from vpnsecure.me → Downloads and place it in "
                "/config/openvpn/. Set VPN_TYPE=openvpn."
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
