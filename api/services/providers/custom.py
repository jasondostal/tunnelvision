"""Custom/BYO WireGuard provider — works with any wg0.conf."""

from datetime import datetime, timezone

import httpx

from api.services.providers.base import VPNProvider, ConnectionCheck


class CustomProvider(VPNProvider):
    """Generic WireGuard provider for BYO configs.

    Uses public IP check services to verify connectivity.
    No server metadata, no account checks — just the basics.
    """

    IP_CHECK_SERVICES = [
        "https://ifconfig.me/ip",
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com",
    ]

    @property
    def name(self) -> str:
        return "custom"

    async def check_connection(self) -> ConnectionCheck:
        """Get public IP via generic services."""
        ip = ""
        for service in self.IP_CHECK_SERVICES:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(service)
                    if resp.status_code == 200:
                        ip = resp.text.strip()
                        break
            except Exception:
                continue

        return ConnectionCheck(
            ip=ip,
            is_vpn_ip=None,  # can't determine without provider API
            checked_at=datetime.now(timezone.utc),
        )
