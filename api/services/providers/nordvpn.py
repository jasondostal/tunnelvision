"""NordVPN provider — WireGuard (NordLynx) with full server API.

Endpoints used:
- https://api.nordvpn.com/v1/servers — WireGuard server list with public keys,
  load, categories (P2P, Double VPN, etc.)
- https://nordvpn.com/wp-json/v1/iplookup — connection check
- https://ipwho.is/ — geo-IP fallback

WireGuard setup:
  In your NordVPN dashboard → Set up manually → WireGuard → Add new key.
  You receive a WireGuard private key and an assigned IP address.
  Set WIREGUARD_PRIVATE_KEY and WIREGUARD_ADDRESSES accordingly.
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

_WG_TECH_ID = "wireguard_udp"


class NordVPNProvider(VPNProvider):
    """NordVPN provider — NordLynx (WireGuard) with programmatic server rotation."""

    SERVERS_URL = (
        "https://api.nordvpn.com/v1/servers"
        "?limit=9999"
        "&filters[servers_technologies][identifier]=wireguard_udp"
    )
    CHECK_URL = "https://nordvpn.com/wp-json/v1/iplookup"
    GEO_FALLBACK_URL = "https://ipwho.is/"

    @property
    def name(self) -> str:
        return "nordvpn"

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="nordvpn",
            display_name="NordVPN",
            description=(
                "In your NordVPN dashboard go to Set up manually → WireGuard → Add new key. "
                "Copy the private key and assigned IP address shown after adding the key."
            ),
            setup_type=SetupType.ACCOUNT,
            supports_server_list=True,
            credentials=[
                CredentialField(
                    key="private_key", label="WireGuard Private Key",
                    field_type="password", secret=True,
                    hint="Shown once when you add a WireGuard key in the NordVPN dashboard",
                    env_var="WIREGUARD_PRIVATE_KEY",
                ),
                CredentialField(
                    key="addresses", label="WireGuard Address",
                    hint="e.g. 10.5.0.2/32 — assigned IP shown alongside your key",
                    env_var="WIREGUARD_ADDRESSES",
                ),
            ],
            default_dns="103.86.96.100",
            filter_capabilities=["country", "city", "p2p", "multihop"],
        )

    async def check_connection(self) -> ConnectionCheck:
        """Verify VPN via NordVPN IP lookup, falling back to generic geo-IP."""
        try:
            async with http_client() as client:
                resp = await client.get(self.CHECK_URL)
                resp.raise_for_status()
                data = resp.json()

            country = data.get("country", "")
            if isinstance(country, dict):
                country = country.get("name", "")

            isp_data = data.get("isp", {})
            org = isp_data.get("name", "") if isinstance(isp_data, dict) else str(isp_data)

            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=country,
                city="",
                is_vpn_ip=org.lower().startswith("nord") if org else None,
                organization=org,
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            pass

        try:
            async with http_client() as client:
                resp = await client.get(self.GEO_FALLBACK_URL)
                resp.raise_for_status()
                data = resp.json()
            return ConnectionCheck(
                ip=data.get("ip", ""),
                country=data.get("country", ""),
                city=data.get("city", ""),
                checked_at=datetime.now(timezone.utc),
            )
        except Exception:
            return ConnectionCheck(checked_at=datetime.now(timezone.utc))

    async def _fetch_servers(self) -> list[ServerInfo]:
        """Fetch NordVPN WireGuard server list with public keys and metadata."""
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get(self.SERVERS_URL)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for server in data:
            if server.get("status") != "online":
                continue

            # Location — first entry
            location = (server.get("locations") or [{}])[0]
            country_data = location.get("country", {})
            city_data = country_data.get("city", {})

            # WireGuard public key from technologies array
            public_key = ""
            for tech in server.get("technologies", []):
                if tech.get("identifier") == _WG_TECH_ID:
                    for meta in tech.get("metadata", []):
                        if meta.get("name") == "public_key":
                            public_key = meta.get("value", "")
                    break

            if not public_key:
                continue

            # Server capabilities from categories
            categories = {c.get("name", "") for c in server.get("categories", [])}
            p2p = "P2P" in categories
            multihop = "Double VPN" in categories

            servers.append(ServerInfo(
                hostname=server.get("hostname", ""),
                country=country_data.get("name", ""),
                country_code=country_data.get("code", ""),
                city=city_data.get("name", ""),
                city_code=city_data.get("dns_name", ""),
                server_type="wireguard",
                ipv4=server.get("station", ""),
                public_key=public_key,
                load=server.get("load", 0),
                p2p=p2p,
                multihop=multihop,
            ))

        return servers
