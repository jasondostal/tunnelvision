"""TunnelVision API response models."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Container health status."""

    healthy: bool
    setup_required: bool = False
    vpn: str = Field(description="VPN state: up, down, disabled, error")
    killswitch: str = Field(description="Killswitch state: active, disabled")
    qbittorrent: str = Field(description="qBittorrent state: running, stopped")
    api: str = "running"
    uptime_seconds: float = 0
    checked_at: datetime


class VPNStatusResponse(BaseModel):
    """Full VPN connection status."""

    state: str = Field(description="up, down, disabled, error")
    public_ip: str = ""
    vpn_ip: str = ""
    endpoint: str = ""
    country: str = Field("", description="Exit country (geo-IP, works with any provider)")
    city: str = Field("", description="Exit city (geo-IP, works with any provider)")
    location: str = Field("", description="Human-readable location (city, country)")
    interface: str = "wg0"
    connected_since: datetime | None = None
    last_handshake: datetime | None = None
    transfer_rx: int = Field(0, description="Bytes received through VPN")
    transfer_tx: int = Field(0, description="Bytes sent through VPN")
    killswitch: str = "active"
    provider: str = "custom"


class VPNIPResponse(BaseModel):
    """Simple public IP response."""

    ip: str
    vpn_active: bool


class QBTStatusResponse(BaseModel):
    """qBittorrent connection stats."""

    state: str = Field(description="running, stopped, error")
    version: str = ""
    webui_port: int = 8080
    download_speed: int = Field(0, description="Bytes/second")
    upload_speed: int = Field(0, description="Bytes/second")
    active_torrents: int = 0
    total_torrents: int = 0


class SystemResponse(BaseModel):
    """Container system information."""

    version: str
    container_uptime: float = Field(description="Seconds since container start")
    vpn_uptime: float | None = Field(None, description="Seconds since VPN connected")
    alpine_version: str = ""
    qbittorrent_version: str = ""
    wireguard_version: str = ""
    python_version: str = ""
    api_port: int = 8081
    webui_port: int = 8080


class ConfigResponse(BaseModel):
    """Current configuration (safe subset — no secrets)."""

    vpn_enabled: bool
    vpn_provider: str
    killswitch_enabled: bool
    webui_port: int
    api_port: int
    ui_enabled: bool
    health_check_interval: int
    timezone: str
    puid: int
    pgid: int
    allowed_networks: str = ""
