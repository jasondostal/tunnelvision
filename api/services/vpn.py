"""VPN service — provider-aware VPN management layer."""

import os

from api.services.providers.base import VPNProvider, ConnectionCheck, ServerInfo, AccountInfo
from api.services.providers.custom import CustomProvider
from api.services.providers.mullvad import MullvadProvider
from api.services.providers.ivpn import IVPNProvider
from api.services.providers.pia import PIAProvider
from api.services.providers.gluetun import GluetunProvider


# Provider registry — add new providers here
PROVIDERS: dict[str, type[VPNProvider]] = {
    "custom": CustomProvider,
    "mullvad": MullvadProvider,
    "ivpn": IVPNProvider,
    "pia": PIAProvider,
    "gluetun": GluetunProvider,
}


def get_provider(provider_name: str | None = None) -> VPNProvider:
    """Get the configured VPN provider instance.

    Args:
        provider_name: Override provider name. Defaults to VPN_PROVIDER env var.

    Returns:
        VPNProvider instance. Falls back to CustomProvider if unknown.
    """
    name = (provider_name or os.getenv("VPN_PROVIDER", "custom")).lower()
    provider_cls = PROVIDERS.get(name, CustomProvider)
    return provider_cls()


async def check_connection(provider: VPNProvider | None = None) -> ConnectionCheck:
    """Verify VPN connection via the configured provider."""
    if provider is None:
        provider = get_provider()
    return await provider.check_connection()


async def get_server_info(endpoint_ip: str, provider: VPNProvider | None = None) -> ServerInfo | None:
    """Look up server metadata for the current connection."""
    if provider is None:
        provider = get_provider()
    return await provider.get_server_info(endpoint_ip)


async def get_account_info(provider: VPNProvider | None = None) -> AccountInfo | None:
    """Check VPN account status."""
    if provider is None:
        provider = get_provider()
    return await provider.get_account_info()
