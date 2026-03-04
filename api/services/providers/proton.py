"""ProtonVPN provider — server list API + NAT-PMP port forwarding.

ProtonVPN provides:
- Public API for free servers, authenticated for Plus/Visionary
- WireGuard support with public keys in server list
- NAT-PMP port forwarding on supported servers (Feature bit 4)

Endpoints used:
- https://api.protonvpn.ch/vpn/logicals — server list with features bitmask
- https://api.protonvpn.ch/vpn/sessions — auth check (Plus/Visionary)
"""

from datetime import datetime, timezone

from api.constants import TIMEOUT_FETCH, http_client
from api.services.providers.base import (
    CredentialField,
    PeerConfig,
    ProviderMeta,
    SetupType,
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
    AccountInfo,
)

# ProtonVPN feature bitmask (from API docs)
FEATURE_SECURE_CORE = 1
FEATURE_TOR = 2
FEATURE_P2P = 4
FEATURE_STREAMING = 8
FEATURE_PORT_FORWARD = 16


class ProtonProvider(VPNProvider):
    """ProtonVPN provider with server list and NAT-PMP port forwarding."""

    SERVERS_URL = "https://api.protonvpn.ch/vpn/logicals"
    GEO_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "proton"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="proton",
            display_name="Proton VPN",
            description="From the Proton team. Download your WireGuard config from account.protonvpn.com.",
            setup_type=SetupType.PASTE,
            supports_server_list=True,
            supports_account_check=True,
            supports_port_forwarding=True,
            credentials=[
                CredentialField(
                    key="proton_user", label="Proton Username",
                    hint="e.g. user@proton.me",
                    env_var="PROTON_USER",
                ),
                CredentialField(
                    key="proton_pass", label="Proton Password",
                    field_type="password", secret=True,
                    env_var="PROTON_PASS",
                ),
            ],
            default_dns="10.2.0.1",
            filter_capabilities=["country", "city", "p2p", "streaming", "port_forward", "secure_core"],
        )

    async def check_connection(self) -> ConnectionCheck:
        """Generic IP check via geo-IP fallback chain."""
        try:
            async with http_client() as client:
                resp = await client.get(self.GEO_URL)
                resp.raise_for_status()
                data = resp.json()

            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                is_vpn_ip=None,
                organization=data.get("connection", {}).get("org", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def get_account_info(self) -> AccountInfo | None:
        """Check ProtonVPN account via authenticated API."""
        username = self.config.proton_user if self.config else ""
        password = self.config.proton_pass if self.config else ""
        if not username or not password:
            return None

        try:
            async with http_client() as client:
                # ProtonVPN uses SRP auth — simplified check via sessions endpoint
                resp = await client.get(
                    "https://api.protonvpn.ch/vpn/sessions",
                    auth=(username, password),
                )
                if resp.status_code == 200:
                    return AccountInfo(active=True)
                return AccountInfo(active=False)
        except Exception:
            return None

    async def post_connect(self, server: ServerInfo, config, peer: PeerConfig) -> None:
        """Start NAT-PMP port forwarding if enabled and server supports it."""
        if config and config.port_forward_enabled and server.port_forward:
            from api.services.natpmp import get_natpmp_service
            get_natpmp_service(config=config).start(peer.endpoint)

    async def _fetch_servers(self) -> list[ServerInfo]:
        """Fetch ProtonVPN server list with WireGuard endpoints."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.SERVERS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for logical in data.get("LogicalServers", []):
            server_name = logical.get("Name", "")
            exit_country = logical.get("ExitCountry", "")
            city_name = logical.get("City", "")
            features = logical.get("Features", 0)
            tier = logical.get("Tier", 0)
            load = logical.get("Load", 0)

            for physical in logical.get("Servers", []):
                servers.append(ServerInfo(
                    hostname=server_name,
                    country=exit_country,
                    country_code=exit_country,
                    city=city_name,
                    server_type="wireguard",
                    ipv4=physical.get("EntryIP", ""),
                    port_forward=bool(features & FEATURE_PORT_FORWARD),
                    streaming=bool(features & FEATURE_STREAMING),
                    p2p=bool(features & FEATURE_P2P),
                    secure_core=bool(features & FEATURE_SECURE_CORE),
                    tier=tier,
                    load=load,
                    extra={
                        "exit_ip": physical.get("ExitIP", ""),
                        "features": features,
                    },
                ))

        return servers
