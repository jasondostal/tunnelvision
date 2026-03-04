"""Settings management — read/write persistent YAML config."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.services.settings import get_public_settings, save_settings, load_settings, CONFIGURABLE_FIELDS

router = APIRouter()


class SettingsUpdate(BaseModel):
    """Partial settings update — only include fields you want to change."""
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
    ui_enabled: str | None = None
    mqtt_enabled: str | None = None
    mqtt_broker: str | None = None
    mqtt_port: str | None = None
    mqtt_user: str | None = None
    mqtt_pass: str | None = None
    auto_reconnect: str | None = None


@router.get("/settings")
async def get_settings(request: Request):
    """Get current settings (secrets masked)."""
    return {
        "settings": get_public_settings(),
        "fields": {
            k: {"secret": v["secret"], "env": v["env"]}
            for k, v in CONFIGURABLE_FIELDS.items()
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

    # Determine if restart is needed
    restart_fields = {"killswitch_enabled", "vpn_dns", "vpn_provider", "mqtt_enabled", "mqtt_broker"}
    needs_restart = bool(restart_fields & set(updates.keys()))

    return {
        "message": "Settings saved to /config/tunnelvision.yml",
        "needs_restart": needs_restart,
        "settings": get_public_settings(),
    }
