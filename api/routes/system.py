"""System information endpoint."""

import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request

from api import __version__
from api.constants import SUBPROCESS_TIMEOUT_QUICK
from api.models import SystemResponse

router = APIRouter()


def _get_command_output(cmd: list[str], default: str = "") -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
        return result.stdout.strip() if result.returncode == 0 else default
    except Exception:
        return default


@router.get("/system", response_model=SystemResponse)
async def system_info(request: Request):
    """Container system information."""
    config = request.app.state.config
    container_uptime = time.time() - request.app.state.started_at

    # VPN uptime
    vpn_uptime = None
    started_at = request.app.state.state.vpn_started_at
    if started_at:
        try:
            vpn_start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            vpn_uptime = time.time() - vpn_start.timestamp()
        except ValueError:
            pass

    return SystemResponse(
        version=__version__,
        container_uptime=round(container_uptime, 1),
        vpn_uptime=round(vpn_uptime, 1) if vpn_uptime else None,
        alpine_version=Path("/etc/alpine-release").read_text().strip() if Path("/etc/alpine-release").exists() else "",
        qbittorrent_version=_get_command_output(["qbittorrent-nox", "--version"]) if config.qbt_enabled else "",
        wireguard_version=_get_command_output(["wg", "--version"]),
        python_version=platform.python_version(),
        api_port=config.api_port,
        webui_port=config.webui_port,
    )
