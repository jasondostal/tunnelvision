"""Health endpoint — comprehensive container health."""

import subprocess
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from api.models import HealthResponse

router = APIRouter()


def _read_state(path: str, default: str = "unknown") -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return default


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """Comprehensive container health status."""
    config = request.app.state.config

    setup_required = _read_state("/var/run/tunnelvision/setup_required", "false") == "true"
    vpn_state = _read_state("/var/run/tunnelvision/vpn_state", "disabled" if not config.vpn_enabled else "unknown")
    killswitch_state = _read_state("/var/run/tunnelvision/killswitch_state", "disabled")
    healthy_str = _read_state("/var/run/tunnelvision/healthy", "true")

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

    # Check qBittorrent
    try:
        result = subprocess.run(
            ["curl", "-sf", "-o", "/dev/null", "--max-time", "3",
             f"http://localhost:{config.webui_port}"],
            capture_output=True, timeout=5,
        )
        qbt_state = "running" if result.returncode == 0 else "stopped"
    except Exception:
        qbt_state = "stopped"

    uptime = time.time() - request.app.state.started_at

    return HealthResponse(
        healthy=healthy_str == "true" and qbt_state == "running",
        vpn=vpn_state,
        killswitch=killswitch_state,
        qbittorrent=qbt_state,
        uptime_seconds=round(uptime, 1),
        checked_at=datetime.now(timezone.utc),
    )
