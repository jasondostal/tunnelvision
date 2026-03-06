"""Gluetun sidecar provider — reads VPN state from gluetun's control server.

TunnelVision becomes the observability layer; gluetun handles the tunnel.
Works alongside any gluetun-managed VPN — TunnelVision adds the dashboard,
API, Home Assistant integration, and monitoring without touching the tunnel.

Endpoints used:
- http://<gluetun>:8000/v1/vpn/status — VPN running/stopped
- http://<gluetun>:8000/v1/publicip/ip — current VPN exit IP
- http://<gluetun>:8000/v1/portforward — forwarded port (if available)
"""

from datetime import datetime, timezone

from api.constants import GLUETUN_DEFAULT_URL, TIMEOUT_QUICK, http_client
from api.services.providers.base import (
    CredentialField,
    ProviderMeta,
    SetupType,
    VPNProvider,
    ConnectionCheck,
)
from api.services.providers.custom import CustomProvider


class GluetunProvider(VPNProvider):
    """Reads VPN state from gluetun's control server API."""

    def __init__(self, config=None):
        super().__init__(config)
        self._base_url = config.gluetun_url if config else GLUETUN_DEFAULT_URL
        self._api_key = config.gluetun_api_key if config else ""
        # Fall back to CustomProvider for geo-IP (gluetun only returns the IP, not location)
        self._geo = CustomProvider(config)

    @property
    def name(self) -> str:
        return "gluetun"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="gluetun",
            display_name="Gluetun (Sidecar)",
            description="Already running gluetun? TunnelVision adds the dashboard, HA integration, and observability layer on top.",
            setup_type=SetupType.SIDECAR,
            credentials=[
                CredentialField(
                    key="gluetun_url", label="Gluetun URL",
                    required=False,
                    hint=f"Default: {GLUETUN_DEFAULT_URL}",
                    env_var="GLUETUN_URL",
                ),
                CredentialField(
                    key="gluetun_api_key", label="API Key",
                    field_type="password", secret=True, required=False,
                    hint="Optional — only if gluetun has auth enabled",
                    env_var="GLUETUN_API_KEY",
                ),
            ],
        )

    def _headers(self) -> dict:
        if self._api_key:
            return {"X-API-Key": self._api_key}
        return {}

    async def check_connection(self) -> ConnectionCheck:
        """Get VPN status from gluetun, enrich with geo-IP for location."""
        try:
            async with http_client(timeout=TIMEOUT_QUICK) as client:
                # Get public IP from gluetun
                ip_resp = await client.get(
                    f"{self._base_url}/v1/publicip/ip",
                    headers=self._headers(),
                )
                ip_data = ip_resp.json() if ip_resp.status_code == 200 else {}
                public_ip = ip_data.get("public_ip", "")

            if public_ip:
                # Enrich with geo-IP for country/city
                geo = await self._geo.check_connection()
                return ConnectionCheck(
                    ip=public_ip,
                    country=geo.country,
                    city=geo.city,
                    organization=geo.organization,
                    is_vpn_ip=None,
                    checked_at=datetime.now(timezone.utc),
                )
        except Exception:
            pass

        return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def get_vpn_status(self) -> str:
        """Get gluetun VPN status: running/stopped."""
        try:
            async with http_client(timeout=TIMEOUT_QUICK) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/vpn/status",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    return resp.json().get("status", "unknown")
        except Exception:
            pass
        return "unknown"

    async def get_forwarded_port(self) -> int | None:
        """Get gluetun's forwarded port (if port forwarding is enabled)."""
        try:
            async with http_client(timeout=TIMEOUT_QUICK) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/portforward",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    port = resp.json().get("port", 0)
                    return port if port > 0 else None
        except Exception:
            pass
        return None
