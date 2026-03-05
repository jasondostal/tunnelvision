"""qBittorrent status endpoint."""

from fastapi import APIRouter, Request

from api.constants import ServiceState, TIMEOUT_QUICK, http_client
from api.models import QBTStatusResponse

router = APIRouter()


@router.get("/qbt/status", response_model=QBTStatusResponse)
async def qbt_status(request: Request):
    """qBittorrent connection stats."""
    config = request.app.state.config

    if not config.qbt_enabled:
        return QBTStatusResponse(state=ServiceState.DISABLED, webui_port=config.webui_port)

    base = f"http://localhost:{config.webui_port}/api/v2"
    dl_speed = 0
    up_speed = 0
    version = ""
    active = 0
    total = 0
    state = ServiceState.ERROR

    async with http_client(timeout=TIMEOUT_QUICK) as client:
        # Transfer info — determines running state
        try:
            resp = await client.get(f"{base}/transfer/info")
            if resp.status_code < 400:
                data = resp.json()
                dl_speed = data.get("dl_info_speed", 0)
                up_speed = data.get("up_info_speed", 0)
                state = ServiceState.RUNNING
            else:
                state = ServiceState.STOPPED
        except Exception:
            state = ServiceState.STOPPED

        # App version
        try:
            resp = await client.get(f"{base}/app/version")
            if resp.status_code < 400:
                version = resp.text.strip()
        except Exception:
            pass

        # Torrent counts
        try:
            resp = await client.get(f"{base}/torrents/info")
            if resp.status_code < 400:
                torrents = resp.json()
                total = len(torrents)
                active = sum(
                    1 for t in torrents
                    if t.get("state", "").startswith(
                        ("downloading", "uploading", "stalledDL", "stalledUP")
                    )
                )
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
