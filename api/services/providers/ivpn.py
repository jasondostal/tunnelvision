"""IVPN provider — public API integration.

Endpoints used:
- https://api.ivpn.net/v5/servers.json — server list with WireGuard pubkeys
- https://api.ivpn.net/v4/geo-lookup — connection verification, IP, location
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
)


class IVPNProvider(VPNProvider):
    """IVPN provider with server list and connection check."""

    SERVERS_URL = "https://api.ivpn.net/v5/servers.json"
    GEO_URL = "https://api.ivpn.net/v4/geo-lookup"

    @property
    def name(self) -> str:
        return "ivpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="ivpn",
            display_name="IVPN",
            description="Privacy-focused, open-source. Auto-generates configs, server rotation, connection verification.",
            setup_type=SetupType.ACCOUNT,
            supports_server_list=True,
            credentials=[
                CredentialField(
                    key="private_key", label="WireGuard Private Key",
                    field_type="password", secret=True,
                    hint="From IVPN WireGuard key management",
                    env_var="WIREGUARD_PRIVATE_KEY",
                ),
                CredentialField(
                    key="addresses", label="WireGuard Address",
                    hint="e.g. 172.x.x.x/32",
                    env_var="WIREGUARD_ADDRESSES",
                ),
            ],
            default_dns="172.16.0.1",
            filter_capabilities=["country", "city"],
        )

    async def check_connection(self) -> ConnectionCheck:
        """Verify VPN via IVPN geo-lookup — IP, location, isIvpnServer."""
        try:
            async with http_client() as client:
                resp = await client.get(self.GEO_URL)
                resp.raise_for_status()
                data = resp.json()

            return ConnectionCheck(
                ip=data.get("ip_address", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                is_vpn_ip=data.get("isIvpnServer", False),
                organization=data.get("organization", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def _fetch_servers(self) -> list[ServerInfo]:
        """Fetch IVPN WireGuard server list with pubkeys."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.SERVERS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for gateway in data.get("wireguard", []):
            for host in gateway.get("hosts", []):
                servers.append(ServerInfo(
                    hostname=host.get("hostname", ""),
                    country=gateway.get("country", ""),
                    country_code=gateway.get("country_code", ""),
                    city=gateway.get("city", ""),
                    provider=host.get("isp", gateway.get("isp", "")),
                    server_type="wireguard",
                    fqdn=host.get("dns_name", ""),
                    ipv4=host.get("host", ""),
                    public_key=host.get("public_key", ""),
                    port=host.get("multihop_port", 2049),
                    multihop=True,
                ))

        return servers
