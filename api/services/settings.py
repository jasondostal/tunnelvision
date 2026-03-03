"""Persistent settings — YAML file in /config, env vars as defaults."""

import os
from pathlib import Path
from typing import Any

import yaml

SETTINGS_PATH = Path("/config/tunnelvision.yml")

# Fields that can be configured via the settings file/UI
CONFIGURABLE_FIELDS = {
    "admin_user": {"env": "ADMIN_USER", "default": "", "secret": False},
    "admin_pass": {"env": "ADMIN_PASS", "default": "", "secret": True},
    "auth_proxy_header": {"env": "AUTH_PROXY_HEADER", "default": "", "secret": False},
    "api_key": {"env": "API_KEY", "default": "", "secret": True},
    "health_check_interval": {"env": "HEALTH_CHECK_INTERVAL", "default": "30", "secret": False},
    "vpn_provider": {"env": "VPN_PROVIDER", "default": "custom", "secret": False},
    "vpn_country": {"env": "VPN_COUNTRY", "default": "", "secret": False},
    "vpn_city": {"env": "VPN_CITY", "default": "", "secret": False},
    "vpn_dns": {"env": "VPN_DNS", "default": "", "secret": False},
    "killswitch_enabled": {"env": "KILLSWITCH_ENABLED", "default": "true", "secret": False},
    "ui_enabled": {"env": "UI_ENABLED", "default": "true", "secret": False},
    "mqtt_enabled": {"env": "MQTT_ENABLED", "default": "false", "secret": False},
    "mqtt_broker": {"env": "MQTT_BROKER", "default": "", "secret": False},
    "mqtt_port": {"env": "MQTT_PORT", "default": "1883", "secret": False},
    "mqtt_user": {"env": "MQTT_USER", "default": "", "secret": False},
    "mqtt_pass": {"env": "MQTT_PASS", "default": "", "secret": True},
    "pia_user": {"env": "PIA_USER", "default": "", "secret": False},
    "pia_pass": {"env": "PIA_PASS", "default": "", "secret": True},
    "port_forward_enabled": {"env": "PORT_FORWARD_ENABLED", "default": "false", "secret": False},
    "auto_reconnect": {"env": "AUTO_RECONNECT", "default": "true", "secret": False},
    "notify_webhook_url": {"env": "NOTIFY_WEBHOOK_URL", "default": "", "secret": False},
    "notify_gotify_url": {"env": "NOTIFY_GOTIFY_URL", "default": "", "secret": False},
    "notify_gotify_token": {"env": "NOTIFY_GOTIFY_TOKEN", "default": "", "secret": True},
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
