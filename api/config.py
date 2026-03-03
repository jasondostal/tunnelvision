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

    # qBittorrent
    webui_port: int = field(default_factory=lambda: int(os.getenv("WEBUI_PORT", "8080")))

    # API
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8081")))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))

    # UI
    ui_enabled: bool = field(default_factory=lambda: os.getenv("UI_ENABLED", "true").lower() == "true")

    # Health
    health_check_interval: int = field(default_factory=lambda: int(os.getenv("HEALTH_CHECK_INTERVAL", "30")))

    @property
    def api_auth_required(self) -> bool:
        return bool(self.api_key)


def load_config() -> Config:
    return Config()
