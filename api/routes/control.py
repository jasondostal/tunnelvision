"""Control plane — VPN and qBittorrent management actions."""

import subprocess

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ActionResponse(BaseModel):
    success: bool
    action: str
    message: str = ""
    error: str = ""


def _run(cmd: list[str], timeout: int = 15) -> tuple[bool, str]:
    """Run a command, return (success, output)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


# --- VPN Controls ---

@router.post("/vpn/disconnect", response_model=ActionResponse)
async def vpn_disconnect():
    """Disconnect the VPN tunnel. Killswitch remains active."""
    from pathlib import Path
    vpn_type = Path("/var/run/tunnelvision/vpn_type").read_text().strip() if Path("/var/run/tunnelvision/vpn_type").exists() else "wireguard"

    if vpn_type == "wireguard":
        ok, msg = _run(["wg-quick", "down", "wg0"])
    else:
        ok, msg = _run(["killall", "openvpn"])

    if ok:
        Path("/var/run/tunnelvision/vpn_state").write_text("down")

    return ActionResponse(
        success=ok,
        action="vpn_disconnect",
        message="VPN disconnected" if ok else "",
        error="" if ok else msg,
    )


@router.post("/vpn/restart", response_model=ActionResponse)
async def vpn_restart():
    """Restart the VPN tunnel (down + up)."""
    from pathlib import Path
    vpn_type = Path("/var/run/tunnelvision/vpn_type").read_text().strip() if Path("/var/run/tunnelvision/vpn_type").exists() else "wireguard"

    if vpn_type == "wireguard":
        _run(["wg-quick", "down", "wg0"], timeout=10)
        ok, msg = _run(["wg-quick", "up", "wg0"])
    else:
        _run(["killall", "openvpn"], timeout=5)
        ok, msg = _run(["/etc/s6-overlay/scripts/init-wireguard.sh"], timeout=30)

    if ok:
        Path("/var/run/tunnelvision/vpn_state").write_text("up")

    return ActionResponse(
        success=ok,
        action="vpn_restart",
        message="VPN restarted" if ok else "",
        error="" if ok else msg,
    )


# --- Killswitch Controls ---

@router.post("/killswitch/enable", response_model=ActionResponse)
async def killswitch_enable():
    """Re-apply killswitch firewall rules."""
    ok, msg = _run(["/etc/s6-overlay/scripts/init-killswitch.sh"], timeout=10)
    return ActionResponse(
        success=ok,
        action="killswitch_enable",
        message="Killswitch enabled" if ok else "",
        error="" if ok else msg,
    )


@router.post("/killswitch/disable", response_model=ActionResponse)
async def killswitch_disable():
    """Flush killswitch rules — WARNING: traffic may leak outside VPN."""
    ok, msg = _run(["nft", "flush", "ruleset"])
    if ok:
        from pathlib import Path
        Path("/var/run/tunnelvision/killswitch_state").write_text("disabled")

    return ActionResponse(
        success=ok,
        action="killswitch_disable",
        message="Killswitch disabled — traffic is NOT protected" if ok else "",
        error="" if ok else msg,
    )


# --- qBittorrent Controls ---

@router.post("/qbt/restart", response_model=ActionResponse)
async def qbt_restart():
    """Restart the qBittorrent service via s6."""
    ok, msg = _run(["s6-svc", "-r", "/run/service/svc-qbittorrent"])
    return ActionResponse(
        success=ok,
        action="qbt_restart",
        message="qBittorrent restarted" if ok else "",
        error="" if ok else msg,
    )


@router.post("/qbt/pause", response_model=ActionResponse)
async def qbt_pause_all():
    """Pause all torrents."""
    ok, msg = _run(["curl", "-sf", "-X", "POST",
                     "http://localhost:8080/api/v2/torrents/pause",
                     "-d", "hashes=all"])
    return ActionResponse(
        success=ok,
        action="qbt_pause",
        message="All torrents paused" if ok else "",
        error="" if ok else msg,
    )


@router.post("/qbt/resume", response_model=ActionResponse)
async def qbt_resume_all():
    """Resume all torrents."""
    ok, msg = _run(["curl", "-sf", "-X", "POST",
                     "http://localhost:8080/api/v2/torrents/resume",
                     "-d", "hashes=all"])
    return ActionResponse(
        success=ok,
        action="qbt_resume",
        message="All torrents resumed" if ok else "",
        error="" if ok else msg,
    )
