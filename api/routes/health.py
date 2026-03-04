"""Health endpoint — comprehensive container health."""

import subprocess
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from api.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """Comprehensive container health status."""
    config = request.app.state.config
    state_mgr = request.app.state.state

    setup_required = state_mgr.setup_required
    vpn_state = state_mgr.read("vpn_state", "disabled" if not config.vpn_enabled else "unknown")
    killswitch_state = state_mgr.killswitch_state
    healthy_str = state_mgr.healthy

    # In setup mode, qBit isn't running — that's expected
    if setup_required:
        return HealthResponse(
            healthy=True,
            setup_required=True,
            vpn="setup_required",
            killswitch="disabled",
            qbittorrent="waiting",
            uptime_seconds=round(time.time() - request.app.state.started_at, 1),
            checked_at=datetime.now(timezone.utc),
        )

    # Check qBittorrent (if enabled)
    if config.qbt_enabled:
        try:
            result = subprocess.run(
                ["curl", "-sf", "-o", "/dev/null", "--max-time", "3",
                 f"http://localhost:{config.webui_port}"],
                capture_output=True, timeout=5,
            )
            qbt_state = "running" if result.returncode == 0 else "stopped"
        except Exception:
            qbt_state = "stopped"
    else:
        qbt_state = "disabled"

    uptime = time.time() - request.app.state.started_at

    # Publish state to MQTT on each health check
    try:
        from api.services.mqtt import get_mqtt_service
        get_mqtt_service().publish_state()
    except Exception:
        pass

    healthy = healthy_str == "true"
    if config.qbt_enabled:
        healthy = healthy and qbt_state == "running"

    return HealthResponse(
        healthy=healthy,
        vpn=vpn_state,
        killswitch=killswitch_state,
        qbittorrent=qbt_state,
        uptime_seconds=round(uptime, 1),
        checked_at=datetime.now(timezone.utc),
    )
