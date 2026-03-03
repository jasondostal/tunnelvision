"""Custom/BYO WireGuard provider — works with any wg0.conf.

Uses geo-aware IP check services to return country, city, and ISP
regardless of which VPN provider is being used. This is the baseline
that makes TunnelVision's widget work with any WireGuard config.
"""

from datetime import datetime, timezone

import httpx

from api.services.providers.base import VPNProvider, ConnectionCheck


class CustomProvider(VPNProvider):
    """Generic WireGuard provider for BYO configs.

    Uses public geo-IP services for location data — no provider API needed.
    Tries multiple services in order, falls back gracefully.
    """

    # Geo-aware services (return IP + location as JSON) — tried in order
    GEO_SERVICES = [
        {
            "url": "https://ipwho.is/",
            "ip_field": "ip",
            "country_field": "country",
            "city_field": "city",
            "org_field": "connection.isp",
        },
        {
            "url": "http://ip-api.com/json/?fields=query,country,city,isp,org",
            "ip_field": "query",
            "country_field": "country",
            "city_field": "city",
            "org_field": "isp",
        },
        {
            "url": "https://ifconfig.co/json",
            "ip_field": "ip",
            "country_field": "country",
            "city_field": "city",
            "org_field": "asn_org",
        },
    ]

    # Plain IP fallbacks (no location, but at least we get the IP)
    IP_FALLBACKS = [
        "https://ifconfig.me/ip",
        "https://api.ipify.org",
        "https://icanhazip.com",
    ]

    @property
    def name(self) -> str:
        return "custom"

    async def check_connection(self) -> ConnectionCheck:
        """Get public IP + location via geo-aware services."""
        # Try geo services first — we want country/city for the widget
        for svc in self.GEO_SERVICES:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(svc["url"])
                    if resp.status_code == 200:
                        data = resp.json()
                        return ConnectionCheck(
                            ip=self._extract(data, svc["ip_field"]),
                            country=self._extract(data, svc["country_field"]),
                            city=self._extract(data, svc["city_field"]),
                            organization=self._extract(data, svc["org_field"]),
                            is_vpn_ip=None,  # can't determine without provider API
                            checked_at=datetime.now(timezone.utc),
                        )
            except Exception:
                continue

        # Fall back to plain IP services
        for url in self.IP_FALLBACKS:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return ConnectionCheck(
                            ip=resp.text.strip(),
                            checked_at=datetime.now(timezone.utc),
                        )
            except Exception:
                continue

        return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    @staticmethod
    def _extract(data: dict, field_path: str) -> str:
        """Extract a value from nested dict using dot notation (e.g. 'connection.isp')."""
        keys = field_path.split(".")
        val = data
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key, "")
            else:
                return ""
        return str(val) if val else ""
