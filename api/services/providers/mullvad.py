"""Mullvad VPN provider — full API integration.

Endpoints used:
- https://am.i.mullvad.net/json — connection verification, IP, location, blacklist
- https://api.mullvad.net/www/relays/wireguard/ — server list with metadata
- https://api.mullvad.net/public/accounts/v1/{account}/ — account expiry
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


class MullvadProvider(VPNProvider):
    """Mullvad VPN provider with rich API integration."""

    CHECK_URL = "https://am.i.mullvad.net/json"
    RELAYS_URL = "https://api.mullvad.net/www/relays/wireguard/"
    ACCOUNT_URL = "https://api.mullvad.net/public/accounts/v1/{account}/"
    HEALTH_PING_URL = "https://api.mullvad.net/"

    @property
    def name(self) -> str:
        return "mullvad"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="mullvad",
            display_name="Mullvad VPN",
            description="Privacy-focused VPN. Enter your account number and pick a server.",
            setup_type=SetupType.ACCOUNT,
            supports_server_list=True,
            supports_account_check=True,
            credentials=[
                CredentialField(
                    key="mullvad_account", label="Account Number",
                    hint="16-digit number from mullvad.net",
                    env_var="MULLVAD_ACCOUNT",
                ),
                CredentialField(
                    key="private_key", label="WireGuard Private Key",
                    field_type="password", secret=True,
                    hint="From Mullvad WireGuard key management",
                    env_var="WIREGUARD_PRIVATE_KEY",
                ),
                CredentialField(
                    key="addresses", label="WireGuard Address",
                    hint="e.g. 10.66.0.1/32",
                    env_var="WIREGUARD_ADDRESSES",
                ),
            ],
            default_dns="10.64.0.1",
            filter_capabilities=["country", "city", "owned_only"],
        )

    async def check_connection(self) -> ConnectionCheck:
        """Verify VPN via am.i.mullvad.net — IP, location, blacklist status."""
        try:
            async with http_client() as client:
                resp = await client.get(self.CHECK_URL)
                resp.raise_for_status()
                data = resp.json()

            blacklist_data = data.get("blacklisted", {})

            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                is_vpn_ip=data.get("mullvad_exit_ip", False),
                blacklisted=blacklist_data.get("blacklisted", False) if blacklist_data else None,
                blacklist_results=blacklist_data.get("results", []) if blacklist_data else [],
                organization=data.get("organization", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def get_account_info(self) -> AccountInfo | None:
        """Check Mullvad account expiry."""
        account = self.config.mullvad_account if self.config else ""
        if not account:
            return None

        try:
            async with http_client() as client:
                resp = await client.get(self.ACCOUNT_URL.format(account=account))
                resp.raise_for_status()
                data = resp.json()

            expiry_str = data.get("expiry", "")
            if expiry_str:
                expires_at = datetime.fromisoformat(expiry_str)
                now = datetime.now(timezone.utc)
                days_remaining = (expires_at - now).days

                return AccountInfo(
                    expires_at=expires_at,
                    days_remaining=days_remaining,
                    active=days_remaining > 0,
                )
        except Exception:
            pass

        return None

    async def _fetch_servers(self) -> list[ServerInfo]:
        """Fetch Mullvad WireGuard server list with full metadata."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.RELAYS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for relay in data:
            if not relay.get("active", False):
                continue

            servers.append(ServerInfo(
                hostname=relay.get("hostname", ""),
                country=relay.get("country_name", ""),
                country_code=relay.get("country_code", ""),
                city=relay.get("city_name", ""),
                city_code=relay.get("city_code", ""),
                provider=relay.get("provider", ""),
                owned=relay.get("owned"),
                speed_gbps=relay.get("network_port_speed"),
                server_type=relay.get("type", "wireguard"),
                fqdn=relay.get("fqdn", ""),
                ipv4=relay.get("ipv4_addr_in", ""),
                public_key=relay.get("pubkey", ""),
            ))

        return servers
