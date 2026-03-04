"""Configuration endpoint — view current config (safe subset)."""

from fastapi import APIRouter, Request

from api.models import ConfigResponse

router = APIRouter()


@router.get("/config", response_model=ConfigResponse)
async def get_config(request: Request):
    """Current configuration — no secrets exposed."""
    config = request.app.state.config

    return ConfigResponse(
        vpn_enabled=config.vpn_enabled,
        vpn_provider=config.vpn_provider,
        killswitch_enabled=config.killswitch_enabled,
        qbt_enabled=config.qbt_enabled,
        webui_port=config.webui_port,
        api_port=config.api_port,
        ui_enabled=config.ui_enabled,
        health_check_interval=config.health_check_interval,
        timezone=config.tz,
        puid=config.puid,
        pgid=config.pgid,
        allowed_networks=config.allowed_networks,
    )
