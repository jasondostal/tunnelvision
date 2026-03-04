"""AirVPN provider — server status API + account check.

Endpoints used:
- https://airvpn.org/api/?service=status&format=json — public server list
  with country, city, load, and capabilities
- https://airvpn.org/api/?service=userinfo&format=json&key=KEY — account info
- https://ipwho.is/ — connection check

WireGuard setup:
  Go to airvpn.org → Client Area → Config Generator. Select WireGuard,
  choose your server, download the config, and place it in
  /config/wireguard/wg0.conf. Optionally set AIRVPN_API_KEY for
  account info in the dashboard.
"""

from datetime import datetime, timezone

from api.constants import TIMEOUT_FETCH, http_client
from api.services.providers.base import (
    CredentialField,
    ProviderMeta,
    SetupType,
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
    AccountInfo,
)


class AirVPNProvider(VPNProvider):
    """AirVPN provider — server browsing and account check via API key."""

    SERVERS_URL = "https://airvpn.org/api/?service=status&format=json"
    ACCOUNT_URL = "https://airvpn.org/api/?service=userinfo&format=json&key={key}"
    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "airvpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="airvpn",
            display_name="AirVPN",
            description=(
                "Generate your WireGuard config at airvpn.org → Client Area → Config Generator. "
                "Optionally add your API key (from Client Area → API) for account visibility."
            ),
            setup_type=SetupType.PASTE,
            supports_server_list=True,
            supports_account_check=True,
            credentials=[
                CredentialField(
                    key="airvpn_api_key", label="API Key",
                    field_type="password", secret=True,
                    hint="Optional — from airvpn.org Client Area → API. Enables account info.",
                    required=False,
                    env_var="AIRVPN_API_KEY",
                ),
            ],
            default_dns="10.128.0.1",
            filter_capabilities=["country", "city"],
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

    async def get_account_info(self) -> AccountInfo | None:
        """Check AirVPN account status via API key."""
        api_key = self.config.airvpn_api_key if self.config else ""
        if not api_key:
            return None

        try:
            async with http_client() as client:
                resp = await client.get(self.ACCOUNT_URL.format(key=api_key))
                resp.raise_for_status()
                data = resp.json()

            user = data.get("user", {})
            expiry_ts = user.get("expiry_days")
            if expiry_ts is not None:
                days = int(expiry_ts)
                return AccountInfo(active=days > 0, days_remaining=days)

            return AccountInfo(active=data.get("result") == "OK")
        except Exception:
            return None

    async def _fetch_servers(self) -> list[ServerInfo]:
        """Fetch AirVPN server list from public status API."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.SERVERS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for server in data.get("Servers", []):
            ips = server.get("ip_addresses", [])
            ipv4 = ips[0] if ips else ""

            servers.append(ServerInfo(
                hostname=server.get("public_name", ""),
                country=server.get("country_name", server.get("country", "")),
                country_code=server.get("country_code", ""),
                city=server.get("city_name", ""),
                server_type="wireguard",
                ipv4=ipv4,
                load=int(server.get("health", 100)),
            ))

        return servers
