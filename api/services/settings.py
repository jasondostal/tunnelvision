"""Persistent settings — YAML file in /config, env vars as defaults, Docker secrets."""

import os
from pathlib import Path
from typing import Any

import yaml

from api.constants import (
    GLUETUN_DEFAULT_URL,
    HEALTH_CHECK_INTERVAL,
    HTTP_PROXY_PORT,
    MQTT_PORT,
    PORT_FORWARD_INTERVAL,
    DNS_BLOCKLIST_REFRESH,
    SETTINGS_PATH,
    SOCKS_PROXY_PORT,
)

def _read_secret_file(env_name: str) -> str | None:
    """Read a Docker secret from a file path specified by {ENV}_SECRETFILE.

    Supports Docker secrets, Kubernetes secrets, or any file-based secret injection.
    Returns stripped file content or None if not configured / unreadable.
    """
    secret_path = os.getenv(f"{env_name}_SECRETFILE", "")
    if secret_path:
        try:
            return Path(secret_path).read_text().strip()
        except Exception:
            pass
    return None

# Fields that can be configured via the settings file/UI
CONFIGURABLE_FIELDS = {
    "admin_user": {"env": "ADMIN_USER", "default": "", "secret": False},
    "admin_pass": {"env": "ADMIN_PASS", "default": "", "secret": True},
    "auth_proxy_header": {"env": "AUTH_PROXY_HEADER", "default": "", "secret": False},
    "api_key": {"env": "API_KEY", "default": "", "secret": True},
    "health_check_interval": {"env": "HEALTH_CHECK_INTERVAL", "default": str(HEALTH_CHECK_INTERVAL), "secret": False},
    "vpn_provider": {"env": "VPN_PROVIDER", "default": "custom", "secret": False},
    "vpn_country": {"env": "VPN_COUNTRY", "default": "", "secret": False},
    "vpn_city": {"env": "VPN_CITY", "default": "", "secret": False},
    "vpn_dns": {"env": "VPN_DNS", "default": "", "secret": False},
    "killswitch_enabled": {"env": "KILLSWITCH_ENABLED", "default": "true", "secret": False},
    "ui_enabled": {"env": "UI_ENABLED", "default": "true", "secret": False},
    "mqtt_enabled": {"env": "MQTT_ENABLED", "default": "false", "secret": False},
    "mqtt_broker": {"env": "MQTT_BROKER", "default": "", "secret": False},
    "mqtt_port": {"env": "MQTT_PORT", "default": str(MQTT_PORT), "secret": False},
    "mqtt_user": {"env": "MQTT_USER", "default": "", "secret": False},
    "mqtt_pass": {"env": "MQTT_PASS", "default": "", "secret": True},
    "gluetun_url": {"env": "GLUETUN_URL", "default": GLUETUN_DEFAULT_URL, "secret": False},
    "gluetun_api_key": {"env": "GLUETUN_API_KEY", "default": "", "secret": True},
    "pia_user": {"env": "PIA_USER", "default": "", "secret": False},
    "pia_pass": {"env": "PIA_PASS", "default": "", "secret": True},
    "wireguard_private_key": {"env": "WIREGUARD_PRIVATE_KEY", "default": "", "secret": True},
    "wireguard_addresses": {"env": "WIREGUARD_ADDRESSES", "default": "", "secret": False},
    "port_forward_enabled": {"env": "PORT_FORWARD_ENABLED", "default": "false", "secret": False},
    "port_forward_interval": {"env": "PORT_FORWARD_INTERVAL", "default": str(PORT_FORWARD_INTERVAL), "secret": False},
    "auto_reconnect": {"env": "AUTO_RECONNECT", "default": "true", "secret": False},
    "notify_webhook_url": {"env": "NOTIFY_WEBHOOK_URL", "default": "", "secret": False},
    "notify_gotify_url": {"env": "NOTIFY_GOTIFY_URL", "default": "", "secret": False},
    "notify_gotify_token": {"env": "NOTIFY_GOTIFY_TOKEN", "default": "", "secret": True},
    # Firewall
    "firewall_vpn_input_ports": {"env": "FIREWALL_VPN_INPUT_PORTS", "default": "", "secret": False},
    "firewall_outbound_subnets": {"env": "FIREWALL_OUTBOUND_SUBNETS", "default": "", "secret": False},
    "firewall_custom_rules_file": {"env": "FIREWALL_CUSTOM_RULES_FILE", "default": "", "secret": False},
    # DNS
    "dns_enabled": {"env": "DNS_ENABLED", "default": "false", "secret": False},
    "dns_upstream": {"env": "DNS_UPSTREAM", "default": "1.1.1.1,1.0.0.1", "secret": False},
    "dns_dot_enabled": {"env": "DNS_DOT_ENABLED", "default": "true", "secret": False},
    "dns_cache_enabled": {"env": "DNS_CACHE_ENABLED", "default": "true", "secret": False},
    "dns_block_ads": {"env": "DNS_BLOCK_ADS", "default": "false", "secret": False},
    "dns_block_malware": {"env": "DNS_BLOCK_MALWARE", "default": "false", "secret": False},
    "dns_block_surveillance": {"env": "DNS_BLOCK_SURVEILLANCE", "default": "false", "secret": False},
    "dns_custom_blocklist_url": {"env": "DNS_CUSTOM_BLOCKLIST_URL", "default": "", "secret": False},
    "dns_blocklist_refresh_interval": {"env": "DNS_BLOCKLIST_REFRESH_INTERVAL", "default": str(DNS_BLOCKLIST_REFRESH), "secret": False},
    # ProtonVPN
    "proton_user": {"env": "PROTON_USER", "default": "", "secret": False},
    "proton_pass": {"env": "PROTON_PASS", "default": "", "secret": True},
    # HTTP Proxy
    "http_proxy_enabled": {"env": "HTTP_PROXY_ENABLED", "default": "false", "secret": False},
    "http_proxy_port": {"env": "HTTP_PROXY_PORT", "default": str(HTTP_PROXY_PORT), "secret": False},
    "http_proxy_user": {"env": "HTTP_PROXY_USER", "default": "", "secret": False},
    "http_proxy_pass": {"env": "HTTP_PROXY_PASS", "default": "", "secret": True},
    # SOCKS5 / Shadowsocks
    "socks_proxy_enabled": {"env": "SOCKS_PROXY_ENABLED", "default": "false", "secret": False},
    "socks_proxy_port": {"env": "SOCKS_PROXY_PORT", "default": str(SOCKS_PROXY_PORT), "secret": False},
    "socks_proxy_user": {"env": "SOCKS_PROXY_USER", "default": "", "secret": False},
    "socks_proxy_pass": {"env": "SOCKS_PROXY_PASS", "default": "", "secret": True},
    "shadowsocks_enabled": {"env": "SHADOWSOCKS_ENABLED", "default": "false", "secret": False},
    "shadowsocks_password": {"env": "SHADOWSOCKS_PASSWORD", "default": "", "secret": True},
    "shadowsocks_cipher": {"env": "SHADOWSOCKS_CIPHER", "default": "aes-256-gcm", "secret": False},
}


def load_settings() -> dict[str, Any]:
    """Load settings: YAML file wins, env var is fallback."""
    file_settings = {}
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH) as f:
                file_settings = yaml.safe_load(f) or {}
        except Exception:
            pass

    result = {}
    for key, meta in CONFIGURABLE_FIELDS.items():
        if key in file_settings:
            result[key] = file_settings[key]
        else:
            # For secret fields, check _SECRETFILE before env var
            if meta.get("secret"):
                secret_val = _read_secret_file(meta["env"])
                if secret_val is not None:
                    result[key] = secret_val
                    continue
            result[key] = os.getenv(meta["env"], meta["default"])

    return result


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Save settings to YAML file. Only saves fields that differ from env defaults."""
    current = load_settings()
    current.update({k: v for k, v in updates.items() if k in CONFIGURABLE_FIELDS})

    # Write to YAML
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False)

    return current


def get_public_settings() -> dict[str, Any]:
    """Return settings with secrets masked."""
    settings = load_settings()
    result = {}
    for key, value in settings.items():
        meta = CONFIGURABLE_FIELDS.get(key, {})
        if meta.get("secret") and value:
            result[key] = "********"
        else:
            result[key] = value
    return result
