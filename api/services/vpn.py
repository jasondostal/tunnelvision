"""VPN service — provider-aware VPN management layer."""

from api.config import Config
from api.services.providers.base import VPNProvider, ConnectionCheck, ServerInfo, AccountInfo
from api.services.providers.custom import CustomProvider
from api.services.providers.mullvad import MullvadProvider
from api.services.providers.ivpn import IVPNProvider
from api.services.providers.pia import PIAProvider
from api.services.providers.gluetun import GluetunProvider
from api.services.providers.proton import ProtonProvider


# Provider registry — add new providers here
PROVIDERS: dict[str, type[VPNProvider]] = {
    "custom": CustomProvider,
    "mullvad": MullvadProvider,
    "ivpn": IVPNProvider,
    "pia": PIAProvider,
    "gluetun": GluetunProvider,
    "proton": ProtonProvider,
}


def get_provider(provider_name: str | None = None, config: Config | None = None) -> VPNProvider:
    """Get the configured VPN provider instance.

    Args:
        provider_name: Override provider name. Defaults to config.vpn_provider.
        config: Config object. Passed through to the provider.

    Returns:
        VPNProvider instance. Falls back to CustomProvider if unknown.
    """
    name = (provider_name or (config.vpn_provider if config else "custom")).lower()
    provider_cls = PROVIDERS.get(name, CustomProvider)
    return provider_cls(config)


async def check_connection(config: Config | None = None, provider: VPNProvider | None = None) -> ConnectionCheck:
    """Verify VPN connection via the configured provider."""
    if provider is None:
        provider = get_provider(config=config)
    return await provider.check_connection()


async def get_server_info(endpoint_ip: str, config: Config | None = None, provider: VPNProvider | None = None) -> ServerInfo | None:
    """Look up server metadata for the current connection."""
    if provider is None:
        provider = get_provider(config=config)
    return await provider.get_server_info(endpoint_ip)


async def get_account_info(config: Config | None = None, provider: VPNProvider | None = None) -> AccountInfo | None:
    """Check VPN account status."""
    if provider is None:
        provider = get_provider(config=config)
    return await provider.get_account_info()
