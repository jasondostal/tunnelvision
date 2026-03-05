"""Health endpoint — comprehensive container health."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from api.constants import HealthState, ServiceState, TIMEOUT_QUICK, VpnState, http_client
from api.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """Comprehensive container health status."""
    config = request.app.state.config
    state_mgr = request.app.state.state

    setup_required = state_mgr.setup_required
    vpn_state = state_mgr.read("vpn_state", VpnState.DISABLED if not config.vpn_enabled else VpnState.UNKNOWN)
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
            async with http_client(timeout=TIMEOUT_QUICK) as client:
                resp = await client.get(f"http://localhost:{config.webui_port}")
            qbt_state = ServiceState.RUNNING if resp.status_code < 500 else "stopped"
        except Exception:
            qbt_state = "stopped"
    else:
        qbt_state = ServiceState.DISABLED

    uptime = time.time() - request.app.state.started_at

    # Publish state to MQTT on each health check
    try:
        from api.services.mqtt import get_mqtt_service
        get_mqtt_service().publish_state()
    except Exception:
        pass

    healthy = healthy_str == HealthState.TRUE
    if config.qbt_enabled:
        healthy = healthy and qbt_state == ServiceState.RUNNING

    # Watchdog snapshot
    watchdog_snapshot = None
    try:
        from api.services.watchdog import get_watchdog_service
        watchdog_snapshot = get_watchdog_service().snapshot()
    except Exception:
        pass

    return HealthResponse(
        healthy=healthy,
        vpn=vpn_state,
        killswitch=killswitch_state,
        qbittorrent=qbt_state,
        dns=state_mgr.dns_state,
        http_proxy=state_mgr.http_proxy_state,
        socks_proxy=state_mgr.socks_proxy_state,
        uptime_seconds=round(uptime, 1),
        checked_at=datetime.now(timezone.utc),
        watchdog=watchdog_snapshot,
    )
