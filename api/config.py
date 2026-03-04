"""TunnelVision configuration — environment variables + Docker secrets."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from api.constants import (
    API_PORT,
    DNS_BLOCKLIST_REFRESH,
    GLUETUN_DEFAULT_URL,
    HEALTH_CHECK_INTERVAL,
    HTTP_PROXY_PORT,
    MQTT_PORT,
    PORT_FORWARD_INTERVAL,
    SOCKS_PROXY_PORT,
    WEBUI_PORT,
)


def _secret_or_env(env_name: str, default: str = "") -> str:
    """Read from {ENV}_SECRETFILE first, then env var, then default.

    Supports Docker secrets, Kubernetes secrets, or any file-based secret injection.
    Precedence: secret file > env var > default.
    """
    secret_path = os.getenv(f"{env_name}_SECRETFILE", "")
    if secret_path:
        try:
            return Path(secret_path).read_text().strip()
        except Exception:
            pass
    return os.getenv(env_name, default)


@dataclass(frozen=True)
class Config:
    """Immutable container configuration loaded from environment."""

    # General
    tz: str = field(default_factory=lambda: os.getenv("TZ", "UTC"))
    puid: int = field(default_factory=lambda: int(os.getenv("PUID", "1000")))
    pgid: int = field(default_factory=lambda: int(os.getenv("PGID", "1000")))

    # VPN
    vpn_enabled: bool = field(default_factory=lambda: os.getenv("VPN_ENABLED", "true").lower() == "true")
    vpn_type: str = field(default_factory=lambda: os.getenv("VPN_TYPE", "auto"))
    vpn_provider: str = field(default_factory=lambda: os.getenv("VPN_PROVIDER", "custom"))
    vpn_country: str = field(default_factory=lambda: os.getenv("VPN_COUNTRY", ""))
    vpn_city: str = field(default_factory=lambda: os.getenv("VPN_CITY", ""))
    killswitch_enabled: bool = field(default_factory=lambda: os.getenv("KILLSWITCH_ENABLED", "true").lower() == "true")

    # Sidecar mode (gluetun)
    gluetun_url: str = field(default_factory=lambda: os.getenv("GLUETUN_URL", GLUETUN_DEFAULT_URL))
    gluetun_api_key: str = field(default_factory=lambda: _secret_or_env("GLUETUN_API_KEY"))

    # Provider credentials
    mullvad_account: str = field(default_factory=lambda: os.getenv("MULLVAD_ACCOUNT", ""))
    pia_user: str = field(default_factory=lambda: os.getenv("PIA_USER", ""))
    pia_pass: str = field(default_factory=lambda: _secret_or_env("PIA_PASS"))
    port_forward_enabled: bool = field(default_factory=lambda: os.getenv("PORT_FORWARD_ENABLED", "false").lower() == "true")
    port_forward_interval: int = field(default_factory=lambda: int(os.getenv("PORT_FORWARD_INTERVAL", str(PORT_FORWARD_INTERVAL))))

    # WireGuard config generation (for API-capable providers)
    wireguard_private_key: str = field(default_factory=lambda: _secret_or_env("WIREGUARD_PRIVATE_KEY"))
    wireguard_addresses: str = field(default_factory=lambda: os.getenv("WIREGUARD_ADDRESSES", ""))
    wireguard_dns: str = field(default_factory=lambda: os.getenv("WIREGUARD_DNS", ""))

    # qBittorrent
    qbt_enabled: bool = field(default_factory=lambda: os.getenv("QBT_ENABLED", "true").lower() == "true")
    webui_port: int = field(default_factory=lambda: int(os.getenv("WEBUI_PORT", str(WEBUI_PORT))))

    # API
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", str(API_PORT))))
    api_key: str = field(default_factory=lambda: _secret_or_env("API_KEY"))

    # Auth
    admin_user: str = field(default_factory=lambda: os.getenv("ADMIN_USER", ""))
    admin_pass: str = field(default_factory=lambda: _secret_or_env("ADMIN_PASS"))
    auth_proxy_header: str = field(default_factory=lambda: os.getenv("AUTH_PROXY_HEADER", ""))

    # UI
    ui_enabled: bool = field(default_factory=lambda: os.getenv("UI_ENABLED", "true").lower() == "true")

    # MQTT
    mqtt_enabled: bool = field(default_factory=lambda: os.getenv("MQTT_ENABLED", "false").lower() == "true")
    mqtt_broker: str = field(default_factory=lambda: os.getenv("MQTT_BROKER", ""))
    mqtt_port: int = field(default_factory=lambda: int(os.getenv("MQTT_PORT", str(MQTT_PORT))))
    mqtt_user: str = field(default_factory=lambda: os.getenv("MQTT_USER", ""))
    mqtt_pass: str = field(default_factory=lambda: _secret_or_env("MQTT_PASS"))
    mqtt_topic_prefix: str = field(default_factory=lambda: os.getenv("MQTT_TOPIC_PREFIX", "tunnelvision"))
    mqtt_discovery_prefix: str = field(default_factory=lambda: os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"))

    # Networking
    allowed_networks: str = field(default_factory=lambda: os.getenv("WEBUI_ALLOWED_NETWORKS", ""))

    # Notifications
    notify_webhook_url: str = field(default_factory=lambda: os.getenv("NOTIFY_WEBHOOK_URL", ""))
    notify_gotify_url: str = field(default_factory=lambda: os.getenv("NOTIFY_GOTIFY_URL", ""))
    notify_gotify_token: str = field(default_factory=lambda: _secret_or_env("NOTIFY_GOTIFY_TOKEN"))

    # Health
    health_check_interval: int = field(default_factory=lambda: int(os.getenv("HEALTH_CHECK_INTERVAL", str(HEALTH_CHECK_INTERVAL))))
    auto_reconnect: bool = field(default_factory=lambda: os.getenv("AUTO_RECONNECT", "true").lower() == "true")

    # Firewall
    firewall_vpn_input_ports: str = field(default_factory=lambda: os.getenv("FIREWALL_VPN_INPUT_PORTS", ""))
    firewall_outbound_subnets: str = field(default_factory=lambda: os.getenv("FIREWALL_OUTBOUND_SUBNETS", ""))
    firewall_custom_rules_file: str = field(default_factory=lambda: os.getenv("FIREWALL_CUSTOM_RULES_FILE", ""))

    # DNS
    dns_enabled: bool = field(default_factory=lambda: os.getenv("DNS_ENABLED", "false").lower() == "true")
    dns_upstream: str = field(default_factory=lambda: os.getenv("DNS_UPSTREAM", "1.1.1.1,1.0.0.1"))
    dns_dot_enabled: bool = field(default_factory=lambda: os.getenv("DNS_DOT_ENABLED", "true").lower() == "true")
    dns_cache_enabled: bool = field(default_factory=lambda: os.getenv("DNS_CACHE_ENABLED", "true").lower() == "true")
    dns_block_ads: bool = field(default_factory=lambda: os.getenv("DNS_BLOCK_ADS", "false").lower() == "true")
    dns_block_malware: bool = field(default_factory=lambda: os.getenv("DNS_BLOCK_MALWARE", "false").lower() == "true")
    dns_block_surveillance: bool = field(default_factory=lambda: os.getenv("DNS_BLOCK_SURVEILLANCE", "false").lower() == "true")
    dns_custom_blocklist_url: str = field(default_factory=lambda: os.getenv("DNS_CUSTOM_BLOCKLIST_URL", ""))
    dns_blocklist_refresh_interval: int = field(default_factory=lambda: int(os.getenv("DNS_BLOCKLIST_REFRESH_INTERVAL", str(DNS_BLOCKLIST_REFRESH))))

    # ProtonVPN
    proton_user: str = field(default_factory=lambda: os.getenv("PROTON_USER", ""))
    proton_pass: str = field(default_factory=lambda: _secret_or_env("PROTON_PASS"))

    # HTTP Proxy
    http_proxy_enabled: bool = field(default_factory=lambda: os.getenv("HTTP_PROXY_ENABLED", "false").lower() == "true")
    http_proxy_port: int = field(default_factory=lambda: int(os.getenv("HTTP_PROXY_PORT", str(HTTP_PROXY_PORT))))
    http_proxy_user: str = field(default_factory=lambda: os.getenv("HTTP_PROXY_USER", ""))
    http_proxy_pass: str = field(default_factory=lambda: _secret_or_env("HTTP_PROXY_PASS"))

    # SOCKS5 / Shadowsocks
    socks_proxy_enabled: bool = field(default_factory=lambda: os.getenv("SOCKS_PROXY_ENABLED", "false").lower() == "true")
    socks_proxy_port: int = field(default_factory=lambda: int(os.getenv("SOCKS_PROXY_PORT", str(SOCKS_PROXY_PORT))))
    socks_proxy_user: str = field(default_factory=lambda: os.getenv("SOCKS_PROXY_USER", ""))
    socks_proxy_pass: str = field(default_factory=lambda: _secret_or_env("SOCKS_PROXY_PASS"))
    shadowsocks_enabled: bool = field(default_factory=lambda: os.getenv("SHADOWSOCKS_ENABLED", "false").lower() == "true")
    shadowsocks_password: str = field(default_factory=lambda: _secret_or_env("SHADOWSOCKS_PASSWORD"))
    shadowsocks_cipher: str = field(default_factory=lambda: os.getenv("SHADOWSOCKS_CIPHER", "aes-256-gcm"))

    def __getattr__(self, name: str) -> str:
        """Dynamic lookup for provider credentials declared in ProviderMeta.

        When a new provider is added, its credentials are accessible via
        config.<key> without editing this dataclass — the provider's
        CredentialField declarations drive the lookup.
        """
        try:
            from api.services.vpn import PROVIDERS
            for provider_cls in PROVIDERS.values():
                instance = provider_cls.__new__(provider_cls)
                meta = provider_cls.meta.fget(instance)  # type: ignore[union-attr]
                for cred in meta.credentials:
                    if cred.key == name:
                        env_var = cred.env_var or name.upper()
                        if cred.secret:
                            return _secret_or_env(env_var)
                        return os.getenv(env_var, "")
        except Exception:
            pass
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    @property
    def api_auth_required(self) -> bool:
        return bool(self.api_key)

    @property
    def login_required(self) -> bool:
        return bool(self.admin_user)


def load_config() -> Config:
    return Config()
