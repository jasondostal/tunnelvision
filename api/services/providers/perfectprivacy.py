"""Perfect Privacy VPN provider — OpenVPN only.

Perfect Privacy deliberately does not support WireGuard. Their architecture
(TrackStop ad-blocking, NeuroRouting multi-hop, unlimited simultaneous
connections) is incompatible with WireGuard's requirement for static
pre-assigned client IPs stored server-side.

Supported protocols: OpenVPN, IPsec/IKEv2.

Setup:
  Download your OpenVPN configs from perfect-privacy.com → Downloads →
  OpenVPN. Place the .conf file in /config/openvpn/ and set
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


class PerfectPrivacyProvider(VPNProvider):
    """Perfect Privacy VPN provider — OpenVPN/IPsec, no WireGuard."""

    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "perfectprivacy"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="perfectprivacy",
            display_name="Perfect Privacy",
            description=(
                "Perfect Privacy uses OpenVPN and IPsec — WireGuard is not supported. "
                "Download your OpenVPN config from perfect-privacy.com → Downloads and "
                "place it in /config/openvpn/. Set VPN_TYPE=openvpn."
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
