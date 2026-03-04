"""TunnelVision configuration — all from environment variables."""

import os
from dataclasses import dataclass, field


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
    gluetun_url: str = field(default_factory=lambda: os.getenv("GLUETUN_URL", "http://gluetun:8000"))
    gluetun_api_key: str = field(default_factory=lambda: os.getenv("GLUETUN_API_KEY", ""))

    # Provider credentials
    mullvad_account: str = field(default_factory=lambda: os.getenv("MULLVAD_ACCOUNT", ""))
    pia_user: str = field(default_factory=lambda: os.getenv("PIA_USER", ""))
    pia_pass: str = field(default_factory=lambda: os.getenv("PIA_PASS", ""))
    port_forward_enabled: bool = field(default_factory=lambda: os.getenv("PORT_FORWARD_ENABLED", "false").lower() == "true")

    # WireGuard config generation (for API-capable providers)
    wireguard_private_key: str = field(default_factory=lambda: os.getenv("WIREGUARD_PRIVATE_KEY", ""))
    wireguard_addresses: str = field(default_factory=lambda: os.getenv("WIREGUARD_ADDRESSES", ""))
    wireguard_dns: str = field(default_factory=lambda: os.getenv("WIREGUARD_DNS", ""))

    # qBittorrent
    qbt_enabled: bool = field(default_factory=lambda: os.getenv("QBT_ENABLED", "true").lower() == "true")
    webui_port: int = field(default_factory=lambda: int(os.getenv("WEBUI_PORT", "8080")))

    # API
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8081")))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))

    # Auth
    admin_user: str = field(default_factory=lambda: os.getenv("ADMIN_USER", ""))
    admin_pass: str = field(default_factory=lambda: os.getenv("ADMIN_PASS", ""))
    auth_proxy_header: str = field(default_factory=lambda: os.getenv("AUTH_PROXY_HEADER", ""))

    # UI
    ui_enabled: bool = field(default_factory=lambda: os.getenv("UI_ENABLED", "true").lower() == "true")

    # MQTT
    mqtt_enabled: bool = field(default_factory=lambda: os.getenv("MQTT_ENABLED", "false").lower() == "true")
    mqtt_broker: str = field(default_factory=lambda: os.getenv("MQTT_BROKER", ""))
    mqtt_port: int = field(default_factory=lambda: int(os.getenv("MQTT_PORT", "1883")))
    mqtt_user: str = field(default_factory=lambda: os.getenv("MQTT_USER", ""))
    mqtt_pass: str = field(default_factory=lambda: os.getenv("MQTT_PASS", ""))
    mqtt_topic_prefix: str = field(default_factory=lambda: os.getenv("MQTT_TOPIC_PREFIX", "tunnelvision"))
    mqtt_discovery_prefix: str = field(default_factory=lambda: os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"))

    # Networking
    allowed_networks: str = field(default_factory=lambda: os.getenv("WEBUI_ALLOWED_NETWORKS", ""))

    # Notifications
    notify_webhook_url: str = field(default_factory=lambda: os.getenv("NOTIFY_WEBHOOK_URL", ""))
    notify_gotify_url: str = field(default_factory=lambda: os.getenv("NOTIFY_GOTIFY_URL", ""))
    notify_gotify_token: str = field(default_factory=lambda: os.getenv("NOTIFY_GOTIFY_TOKEN", ""))

    # Health
    health_check_interval: int = field(default_factory=lambda: int(os.getenv("HEALTH_CHECK_INTERVAL", "30")))
    auto_reconnect: bool = field(default_factory=lambda: os.getenv("AUTO_RECONNECT", "true").lower() == "true")

    @property
    def api_auth_required(self) -> bool:
        return bool(self.api_key)

    @property
    def login_required(self) -> bool:
        return bool(self.admin_user)


def load_config() -> Config:
    return Config()
