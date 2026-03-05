"""VPN service — provider-aware VPN management layer."""

import importlib
import logging
import pkgutil

from api.config import Config
from api.services.providers.base import VPNProvider, ConnectionCheck, ServerInfo, AccountInfo
from api.services.providers.custom import CustomProvider

log = logging.getLogger(__name__)


def _discover_providers() -> dict[str, type[VPNProvider]]:
    """Auto-discover provider classes from api/services/providers/*.py.

    Any VPNProvider subclass with a `meta` property gets registered
    by its meta.id. Drop a new file in the package, it appears everywhere.
    """
    providers: dict[str, type[VPNProvider]] = {}
    package = importlib.import_module("api.services.providers")

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        if module_name == "base":
            continue
        try:
            mod = importlib.import_module(f"api.services.providers.{module_name}")
        except Exception:
            log.warning("Failed to import provider module: %s", module_name, exc_info=True)
            continue

        for attr_name in dir(mod):
            cls = getattr(mod, attr_name)
            if (
                isinstance(cls, type)
                and issubclass(cls, VPNProvider)
                and cls is not VPNProvider
                and hasattr(cls, "meta")
            ):
                try:
                    meta = cls.get_meta()
                    providers[meta.id] = cls
                except Exception:
                    log.warning("Failed to read meta from %s", cls.__name__, exc_info=True)

    return providers


# Provider registry — auto-discovered at import time
PROVIDERS: dict[str, type[VPNProvider]] = _discover_providers()

# Singleton instances — cache persists across requests
_instances: dict[str, VPNProvider] = {}


def get_provider(provider_name: str | None = None, config: Config | None = None) -> VPNProvider:
    """Get the configured VPN provider instance.

    Returns a cached singleton per provider name so server list caches
    persist across requests.
    """
    name = (provider_name or (config.vpn_provider if config else "custom")).lower()
    provider_cls = PROVIDERS.get(name, CustomProvider)

    if name not in _instances or type(_instances[name]) is not provider_cls:
        _instances[name] = provider_cls(config)
    return _instances[name]


def get_all_provider_meta() -> list[dict]:
    """Get metadata for all registered providers (for setup wizard, UI, etc.)."""
    result = []
    for provider_cls in PROVIDERS.values():
        try:
            meta = provider_cls.get_meta()
            result.append({
                "id": meta.id,
                "name": meta.display_name,
                "description": meta.description,
                "setup_type": meta.setup_type.value,
                "supports_server_list": meta.supports_server_list,
                "supports_account_check": meta.supports_account_check,
                "supports_port_forwarding": meta.supports_port_forwarding,
                "supports_wireguard": meta.supports_wireguard,
                "supports_openvpn": meta.supports_openvpn,
                "credentials": [
                    {
                        "key": c.key,
                        "label": c.label,
                        "field_type": c.field_type,
                        "required": c.required,
                        "secret": c.secret,
                        "hint": c.hint,
                    }
                    for c in meta.credentials
                ],
                "filter_capabilities": meta.filter_capabilities,
            })
        except Exception:
            log.warning("Failed to read meta for provider class", exc_info=True)
    return result


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


async def refresh_provider_server_list(name: str) -> int:
    """Force-refresh the cached server list for a named provider.

    Bypasses TTL — intended for background auto-updater use only.
    Only refreshes providers that have live instances (accessed at least once
    this session). Returns count of servers refreshed, or 0 otherwise.
    """
    provider = _instances.get(name)
    if provider is None:
        return 0
    count = await provider.refresh_cache()
    if count == 0 and provider.meta.supports_server_list:
        log.warning("Server list refresh returned 0 for %s", name)
    return count


def get_server_list_providers() -> list[str]:
    """Return names of all providers that support server lists."""
    result = []
    for name, cls in PROVIDERS.items():
        try:
            if cls.get_meta().supports_server_list:
                result.append(name)
        except Exception:
            pass
    return result
