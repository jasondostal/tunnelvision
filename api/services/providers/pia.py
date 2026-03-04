"""PIA (Private Internet Access) provider — token-based auth + port forwarding.

PIA uses a different model than Mullvad/IVPN:
- No static WireGuard public keys in the server list
- Authenticate with username/password to get a token
- Exchange token + our generated pubkey with the server to get its pubkey + our IP
- Port forwarding available on select servers (requires periodic keep-alive)

Endpoints used:
- https://serverlist.piaservers.net/vpninfo/servers/v6 — server list with regions
- https://www.privateinternetaccess.com/api/client/v2/token — auth token
- https://<server-ip>:1337/addKey — WireGuard key exchange
- https://<gateway>:19999/getSignature — port forwarding signature
- https://<gateway>:19999/bindPort — port forwarding bind (every 15 min)
"""

import ssl
from datetime import datetime, timezone

from api.constants import PIA_TOKEN_CACHE_TTL, TIMEOUT_FETCH, http_client
from api.services.providers.base import (
    ConnectError,
    CredentialField,
    PeerConfig,
    ProviderMeta,
    SetupType,
    VPNProvider,
    ConnectionCheck,
    ServerInfo,
)

# PIA uses self-signed certs on their gateway endpoints
_no_verify = ssl.create_default_context()
_no_verify.check_hostname = False
_no_verify.verify_mode = ssl.CERT_NONE


class PIAProvider(VPNProvider):
    """PIA provider with token auth, key negotiation, and port forwarding."""

    SERVERS_URL = "https://serverlist.piaservers.net/vpninfo/servers/v6"
    TOKEN_URL = "https://www.privateinternetaccess.com/api/client/v2/token"
    WG_PORT = 1337

    def __init__(self, config=None):
        super().__init__(config)
        self._token: str | None = None
        self._token_time: datetime | None = None

    @property
    def name(self) -> str:
        return "pia"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="pia",
            display_name="Private Internet Access",
            description="Port forwarding support. Authenticates with username/password, auto-negotiates WireGuard keys.",
            setup_type=SetupType.ACCOUNT,
            supports_server_list=True,
            supports_port_forwarding=True,
            credentials=[
                CredentialField(
                    key="pia_user", label="PIA Username",
                    hint="Your PIA username (not email)",
                    env_var="PIA_USER",
                ),
                CredentialField(
                    key="pia_pass", label="PIA Password",
                    field_type="password", secret=True,
                    env_var="PIA_PASS",
                ),
            ],
            default_dns="10.0.0.243",
            filter_capabilities=["country", "city", "port_forward"],
        )

    async def check_connection(self) -> ConnectionCheck:
        """Generic IP check — PIA has no branded check endpoint."""
        try:
            async with http_client() as client:
                resp = await client.get("https://ipwho.is/")
                resp.raise_for_status()
                data = resp.json()

            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                is_vpn_ip=None,  # Can't determine from generic check
                organization=data.get("connection", {}).get("org", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def _fetch_servers(self) -> list[ServerInfo]:
        """Fetch PIA server list with WireGuard endpoints and port-forward flags."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.SERVERS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for region in data.get("regions", []):
            region_name = region.get("name", "")
            country_name = region.get("country", region_name)
            has_port_forward = region.get("port_forward", False)

            for wg_server in region.get("servers", {}).get("wg", []):
                servers.append(ServerInfo(
                    hostname=wg_server.get("cn", ""),
                    country=country_name,
                    country_code=region.get("id", "")[:2].upper(),
                    city=region_name,
                    server_type="wireguard",
                    ipv4=wg_server.get("ip", ""),
                    port_forward=has_port_forward,
                    extra={"region_id": region.get("id", "")},
                ))

        return servers

    async def resolve_connect(self, server: ServerInfo, config) -> PeerConfig:
        """PIA: authenticate, generate ephemeral WG keys, exchange with server."""
        import subprocess as _sp
        from api.constants import SUBPROCESS_TIMEOUT_QUICK

        token = await self.get_token()
        if not token:
            raise ConnectError("PIA auth failed. Check PIA_USER and PIA_PASS.")

        server_ip = server.ipv4
        if not server_ip:
            raise ConnectError("No IP for selected server")

        # Generate ephemeral WireGuard keypair
        try:
            privkey_result = _sp.run(["wg", "genkey"], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
            private_key = privkey_result.stdout.strip()
            pubkey_result = _sp.run(["wg", "pubkey"], input=private_key, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
            public_key = pubkey_result.stdout.strip()
        except Exception as e:
            raise ConnectError(f"Key generation failed: {e}")

        # Exchange keys with PIA server
        try:
            async with http_client(verify=False) as client:
                resp = await client.get(
                    f"https://{server_ip}:1337/addKey",
                    params={"pt": token, "pubkey": public_key},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            raise ConnectError(f"PIA key exchange failed: {e}")

        server_pubkey = data.get("server_key", "")
        our_ip = data.get("peer_ip", "")
        server_port = data.get("server_port", 1337)
        dns_servers = data.get("dns_servers", ["10.0.0.243"])

        if not server_pubkey or not our_ip:
            raise ConnectError("PIA key exchange returned incomplete data")

        return PeerConfig(
            private_key=private_key,
            address=our_ip,
            dns=dns_servers[0] if dns_servers else "10.0.0.243",
            public_key=server_pubkey,
            endpoint=server_ip,
            port=server_port,
            extra={"token": token, "server_vip": data.get("server_vip", server_ip)},
        )

    async def post_connect(self, server: ServerInfo, config, peer: PeerConfig) -> None:
        """Start PIA port forwarding if enabled."""
        if config and config.port_forward_enabled and server.port_forward:
            from api.services.port_forward import get_port_forward_service
            pf = get_port_forward_service()
            gateway_ip = peer.extra.get("server_vip", peer.endpoint)
            pf.start(gateway_ip, peer.extra.get("token", ""))

    async def get_token(self) -> str | None:
        """Authenticate with PIA and get a connection token."""
        # Cache token for 12 hours
        now = datetime.now(timezone.utc)
        if self._token and self._token_time:
            age = (now - self._token_time).total_seconds()
            if age < PIA_TOKEN_CACHE_TTL:
                return self._token

        username = self.config.pia_user if self.config else ""
        password = self.config.pia_pass if self.config else ""
        if not username or not password:
            return None

        try:
            async with http_client() as client:
                resp = await client.post(
                    self.TOKEN_URL,
                    data={"username": username, "password": password},
                )
                resp.raise_for_status()
                data = resp.json()

            self._token = data.get("token")
            self._token_time = now
            return self._token
        except Exception:
            return None
