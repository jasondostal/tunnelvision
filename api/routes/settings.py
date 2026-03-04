"""Settings management — read/write persistent YAML config."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from api.services.settings import get_public_settings, save_settings, load_settings, CONFIGURABLE_FIELDS, get_all_configurable_fields

router = APIRouter()


class SettingsUpdate(BaseModel):
    """Partial settings update — only include fields you want to change.

    Declared fields cover core settings. Provider-specific credentials
    are accepted via extra="allow" — provider metadata drives validation.
    """
    model_config = ConfigDict(extra="allow")

    admin_user: str | None = None
    admin_pass: str | None = None
    auth_proxy_header: str | None = None
    api_key: str | None = None
    health_check_interval: str | None = None
    vpn_provider: str | None = None
    vpn_country: str | None = None
    vpn_city: str | None = None
    vpn_dns: str | None = None
    killswitch_enabled: str | None = None
    wg_userspace: str | None = None
    ui_enabled: str | None = None
    mqtt_enabled: str | None = None
    mqtt_broker: str | None = None
    mqtt_port: str | None = None
    mqtt_user: str | None = None
    mqtt_pass: str | None = None
    gluetun_url: str | None = None
    gluetun_api_key: str | None = None
    pia_user: str | None = None
    pia_pass: str | None = None
    wireguard_private_key: str | None = None
    wireguard_addresses: str | None = None
    port_forward_enabled: str | None = None
    port_forward_hook: str | None = None
    auto_reconnect: str | None = None
    # Server list
    server_list_auto_update: str | None = None
    server_list_update_interval: str | None = None
    notify_webhook_url: str | None = None
    notify_gotify_url: str | None = None
    notify_gotify_token: str | None = None
    # Firewall
    firewall_vpn_input_ports: str | None = None
    firewall_outbound_subnets: str | None = None
    firewall_custom_rules_file: str | None = None
    # DNS
    dns_enabled: str | None = None
    dns_upstream: str | None = None
    dns_dot_enabled: str | None = None
    dns_cache_enabled: str | None = None
    dns_block_ads: str | None = None
    dns_block_malware: str | None = None
    dns_block_surveillance: str | None = None
    dns_custom_blocklist_url: str | None = None
    dns_blocklist_refresh_interval: str | None = None
    # Intervals
    port_forward_interval: str | None = None
    # ProtonVPN
    proton_user: str | None = None
    proton_pass: str | None = None
    # HTTP Proxy
    http_proxy_enabled: str | None = None
    http_proxy_port: str | None = None
    http_proxy_user: str | None = None
    http_proxy_pass: str | None = None
    # SOCKS5 / Shadowsocks
    socks_proxy_enabled: str | None = None
    socks_proxy_port: str | None = None
    socks_proxy_user: str | None = None
    socks_proxy_pass: str | None = None
    shadowsocks_enabled: str | None = None
    shadowsocks_password: str | None = None
    shadowsocks_cipher: str | None = None


@router.get("/settings")
async def get_settings(request: Request):
    """Get current settings (secrets masked)."""
    all_fields = get_all_configurable_fields()
    return {
        "settings": get_public_settings(),
        "fields": {
            k: {"secret": v["secret"], "env": v["env"]}
            for k, v in all_fields.items()
        },
    }


@router.put("/settings")
async def update_settings(body: SettingsUpdate, request: Request):
    """Update settings. Saves to /config/tunnelvision.yml. Some changes require container restart."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    # Don't save masked placeholder values
    updates = {k: v for k, v in updates.items() if v != "********"}

    if not updates:
        return {"message": "No changes", "settings": get_public_settings()}

    save_settings(updates)

    # These fields are re-read from settings YAML at runtime — no restart needed
    hot_reload_fields = {
        "auto_reconnect",       # watchdog re-reads each tick
        "health_check_interval",  # watchdog re-reads each tick
        "vpn_country",          # rotate endpoint re-reads
        "vpn_city",             # rotate endpoint re-reads
        "notify_webhook_url",   # notifications re-read on send
        "notify_gotify_url",    # notifications re-read on send
        "notify_gotify_token",  # notifications re-read on send
        "dns_block_ads",        # blocklist manager re-reads periodically
        "dns_block_malware",    # blocklist manager re-reads periodically
        "dns_block_surveillance",  # blocklist manager re-reads periodically
    }
    needs_restart = bool(set(updates.keys()) - hot_reload_fields)

    return {
        "message": "Settings saved to /config/tunnelvision.yml",
        "needs_restart": needs_restart,
        "settings": get_public_settings(),
    }
