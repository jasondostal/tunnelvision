"""qBittorrent status endpoint."""

import subprocess

from fastapi import APIRouter, Request

from api.models import QBTStatusResponse

router = APIRouter()


@router.get("/qbt/status", response_model=QBTStatusResponse)
async def qbt_status(request: Request):
    """qBittorrent connection stats."""
    config = request.app.state.config

    if not config.qbt_enabled:
        return QBTStatusResponse(state="disabled", webui_port=config.webui_port)

    # Check if qBittorrent is responding
    try:
        result = subprocess.run(
            ["curl", "-sf", "--max-time", "3",
             f"http://localhost:{config.webui_port}/api/v2/transfer/info"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            dl_speed = data.get("dl_info_speed", 0)
            up_speed = data.get("up_info_speed", 0)
            state = "running"
        else:
            dl_speed = 0
            up_speed = 0
            state = "stopped"
    except Exception:
        dl_speed = 0
        up_speed = 0
        state = "error"

    # Get version
    version = ""
    try:
        result = subprocess.run(
            ["curl", "-sf", "--max-time", "3",
             f"http://localhost:{config.webui_port}/api/v2/app/version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
    except Exception:
        pass

    # Get torrent counts
    active = 0
    total = 0
    try:
        result = subprocess.run(
            ["curl", "-sf", "--max-time", "3",
             f"http://localhost:{config.webui_port}/api/v2/torrents/info"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import json
            torrents = json.loads(result.stdout)
            total = len(torrents)
            active = sum(1 for t in torrents if t.get("state", "").startswith(("downloading", "uploading", "stalledDL", "stalledUP")))
    except Exception:
        pass

    return QBTStatusResponse(
        state=state,
        version=version,
        webui_port=config.webui_port,
        download_speed=dl_speed,
        upload_speed=up_speed,
        active_torrents=active,
        total_torrents=total,
    )
