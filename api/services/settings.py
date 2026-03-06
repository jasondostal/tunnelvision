"""Persistent settings — YAML file in /config, env vars as defaults, Docker secrets."""

import os
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from api.constants import (
    COOLDOWN_SECONDS,
    GLUETUN_DEFAULT_URL,
    HANDSHAKE_STALE_SECONDS,
    HEALTH_CHECK_INTERVAL,
    HTTP_PROXY_PORT,
    MQTT_PORT,
    PORT_FORWARD_INTERVAL,
    DNS_BLOCKLIST_REFRESH,
    PROVIDER_CACHE_TTL,
    RECONNECT_THRESHOLD,
    SETTINGS_PATH,
    SHADOWSOCKS_PORT,
    SOCKS_PROXY_PORT,
    WEBUI_PORT,
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
    "trusted_proxy_ips": {"env": "TRUSTED_PROXY_IPS", "default": "", "secret": False},
    "api_key": {"env": "API_KEY", "default": "", "secret": True},
    "health_check_interval": {"env": "HEALTH_CHECK_INTERVAL", "default": str(HEALTH_CHECK_INTERVAL), "secret": False},
    "vpn_provider": {"env": "VPN_PROVIDER", "default": "custom", "secret": False},
    "vpn_country": {"env": "VPN_COUNTRY", "default": "", "secret": False},
    "vpn_city": {"env": "VPN_CITY", "default": "", "secret": False},
    "vpn_dns": {"env": "VPN_DNS", "default": "", "secret": False},
    "killswitch_enabled": {"env": "KILLSWITCH_ENABLED", "default": "true", "secret": False},
    "wg_userspace": {"env": "WG_USERSPACE", "default": "auto", "secret": False},
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
    "port_forward_hook": {"env": "PORT_FORWARD_HOOK", "default": "", "secret": False},
    "auto_reconnect": {"env": "AUTO_RECONNECT", "default": "true", "secret": False},
    # Watchdog tuning (hot-reloadable)
    "handshake_stale_seconds": {"env": "HANDSHAKE_STALE_SECONDS", "default": str(HANDSHAKE_STALE_SECONDS), "secret": False},
    "reconnect_threshold": {"env": "RECONNECT_THRESHOLD", "default": str(RECONNECT_THRESHOLD), "secret": False},
    "cooldown_seconds": {"env": "COOLDOWN_SECONDS", "default": str(COOLDOWN_SECONDS), "secret": False},
    # Server list
    "server_list_auto_update": {"env": "SERVER_LIST_AUTO_UPDATE", "default": "true", "secret": False},
    "server_list_update_interval": {"env": "SERVER_LIST_UPDATE_INTERVAL", "default": str(PROVIDER_CACHE_TTL), "secret": False},
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
    "shadowsocks_port": {"env": "SHADOWSOCKS_PORT", "default": str(SHADOWSOCKS_PORT), "secret": False},
    "shadowsocks_password": {"env": "SHADOWSOCKS_PASSWORD", "default": "", "secret": True},
    "shadowsocks_cipher": {"env": "SHADOWSOCKS_CIPHER", "default": "aes-256-gcm", "secret": False},
    # Container / general (env var reference — displayed in UI, some require compose update)
    "tz": {"env": "TZ", "default": "UTC", "secret": False},
    "vpn_enabled": {"env": "VPN_ENABLED", "default": "true", "secret": False},
    "vpn_type": {"env": "VPN_TYPE", "default": "auto", "secret": False},
    "wireguard_dns": {"env": "WIREGUARD_DNS", "default": "", "secret": False},
    "qbt_enabled": {"env": "QBT_ENABLED", "default": "true", "secret": False},
    "webui_port": {"env": "WEBUI_PORT", "default": str(WEBUI_PORT), "secret": False},
    "mqtt_topic_prefix": {"env": "MQTT_TOPIC_PREFIX", "default": "tunnelvision", "secret": False},
    "mqtt_discovery_prefix": {"env": "MQTT_DISCOVERY_PREFIX", "default": "homeassistant", "secret": False},
    "allowed_networks": {"env": "WEBUI_ALLOWED_NETWORKS", "default": "", "secret": False},
}


def get_all_configurable_fields() -> dict[str, dict]:
    """Base fields + auto-discovered provider credential fields.

    Provider metadata declares credentials via CredentialField. This function
    merges those into CONFIGURABLE_FIELDS so new providers are automatically
    configurable without editing this module.
    """
    fields = dict(CONFIGURABLE_FIELDS)
    try:
        from api.services.vpn import PROVIDERS
        for provider_cls in PROVIDERS.values():
            meta = provider_cls.get_meta()
            for cred in meta.credentials:
                if cred.key not in fields:
                    fields[cred.key] = {
                        "env": cred.env_var or cred.key.upper(),
                        "default": "",
                        "secret": cred.secret,
                    }
    except Exception:
        pass
    return fields


def load_settings() -> dict[str, Any]:
    """Load settings: YAML file wins, env var is fallback."""
    file_settings: dict[str, Any] = {}
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH) as f:
                file_settings = yaml.safe_load(f) or {}
        except Exception:
            pass

    all_fields = get_all_configurable_fields()
    result = {}
    for key, meta in all_fields.items():
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
    all_fields = get_all_configurable_fields()
    current.update({k: v for k, v in updates.items() if k in all_fields})

    # Write to YAML
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False)

    return current


def get_public_settings() -> dict[str, Any]:
    """Return settings with secrets masked."""
    settings = load_settings()
    all_fields = get_all_configurable_fields()
    result = {}
    for key, value in settings.items():
        meta = all_fields.get(key, {})
        if meta.get("secret") and value:
            result[key] = "********"
        else:
            result[key] = value
    return result
