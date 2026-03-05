"""Control plane — VPN and qBittorrent management actions.

Action logic lives in standalone do_*() functions so both
the REST routes and MQTT command handler can call them directly.
"""

import subprocess

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.config import Config
from api.constants import (
    KillswitchState,
    SCRIPT_INIT_VPN,
    SCRIPT_KILLSWITCH,
    SUBPROCESS_TIMEOUT_DEFAULT,
    SUBPROCESS_TIMEOUT_LONG,
    SUBPROCESS_TIMEOUT_QUICK,
    SUBPROCESS_TIMEOUT_VPN,
    VpnState,
)
from api.routes.events import broadcast
from api.services.state import StateManager

router = APIRouter()


class ActionResponse(BaseModel):
    success: bool
    action: str
    message: str = ""
    error: str = ""


def _run(cmd: list[str], timeout: int = SUBPROCESS_TIMEOUT_LONG) -> tuple[bool, str]:
    """Run a command, return (success, output)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


# --- Action functions (callable from routes AND MQTT) ---

def do_vpn_disconnect(state_mgr: StateManager) -> ActionResponse:
    vpn_type = state_mgr.vpn_type

    if vpn_type == "wireguard":
        ok, msg = _run(["wg-quick", "down", "wg0"])
    else:
        ok, msg = _run(["killall", "openvpn"])

    if ok:
        state_mgr.vpn_state = VpnState.DOWN
        broadcast("vpn_state", {"state": VpnState.DOWN, "action": "disconnect"})

    return ActionResponse(
        success=ok,
        action="vpn_disconnect",
        message="VPN disconnected" if ok else "",
        error="" if ok else msg,
    )


def do_vpn_restart(state_mgr: StateManager) -> ActionResponse:
    vpn_type = state_mgr.vpn_type

    if vpn_type == "wireguard":
        _run(["wg-quick", "down", "wg0"], timeout=SUBPROCESS_TIMEOUT_DEFAULT)
        ok, msg = _run(["wg-quick", "up", "wg0"])
    else:
        _run(["killall", "openvpn"], timeout=SUBPROCESS_TIMEOUT_QUICK)
        ok, msg = _run([str(SCRIPT_INIT_VPN)], timeout=SUBPROCESS_TIMEOUT_VPN)

    if ok:
        state_mgr.vpn_state = VpnState.UP
        broadcast("vpn_state", {"state": VpnState.UP, "action": "restart"})

    return ActionResponse(
        success=ok,
        action="vpn_restart",
        message="VPN restarted" if ok else "",
        error="" if ok else msg,
    )


def do_killswitch_enable() -> ActionResponse:
    ok, msg = _run([str(SCRIPT_KILLSWITCH)], timeout=SUBPROCESS_TIMEOUT_DEFAULT)
    return ActionResponse(
        success=ok,
        action="killswitch_enable",
        message="Killswitch enabled" if ok else "",
        error="" if ok else msg,
    )


def do_killswitch_disable(state_mgr: StateManager) -> ActionResponse:
    ok, msg = _run(["nft", "flush", "ruleset"])
    if ok:
        state_mgr.killswitch_state = KillswitchState.DISABLED

    return ActionResponse(
        success=ok,
        action="killswitch_disable",
        message="Killswitch disabled — traffic is NOT protected" if ok else "",
        error="" if ok else msg,
    )


def do_qbt_restart(config: Config) -> ActionResponse:
    if not config.qbt_enabled:
        return ActionResponse(success=False, action="qbt_restart", error="qBittorrent is disabled")
    ok, msg = _run(["s6-svc", "-r", "/run/service/svc-qbittorrent"])
    return ActionResponse(
        success=ok,
        action="qbt_restart",
        message="qBittorrent restarted" if ok else "",
        error="" if ok else msg,
    )


def do_qbt_pause(config: Config) -> ActionResponse:
    if not config.qbt_enabled:
        return ActionResponse(success=False, action="qbt_pause", error="qBittorrent is disabled")
    ok, msg = _run(["curl", "-sf", "-X", "POST",
                     f"http://localhost:{config.webui_port}/api/v2/torrents/pause",
                     "-d", "hashes=all"])
    return ActionResponse(
        success=ok,
        action="qbt_pause",
        message="All torrents paused" if ok else "",
        error="" if ok else msg,
    )


def do_qbt_resume(config: Config) -> ActionResponse:
    if not config.qbt_enabled:
        return ActionResponse(success=False, action="qbt_resume", error="qBittorrent is disabled")
    ok, msg = _run(["curl", "-sf", "-X", "POST",
                     f"http://localhost:{config.webui_port}/api/v2/torrents/resume",
                     "-d", "hashes=all"])
    return ActionResponse(
        success=ok,
        action="qbt_resume",
        message="All torrents resumed" if ok else "",
        error="" if ok else msg,
    )


# --- REST Routes (thin wrappers around action functions) ---

@router.post("/vpn/disconnect", response_model=ActionResponse)
async def vpn_disconnect(request: Request):
    """Disconnect the VPN tunnel. Killswitch remains active."""
    return do_vpn_disconnect(request.app.state.state)


@router.post("/vpn/restart", response_model=ActionResponse)
async def vpn_restart(request: Request):
    """Restart the VPN tunnel (down + up)."""
    return do_vpn_restart(request.app.state.state)


@router.post("/killswitch/enable", response_model=ActionResponse)
async def killswitch_enable():
    """Re-apply killswitch firewall rules."""
    return do_killswitch_enable()


@router.post("/killswitch/disable", response_model=ActionResponse)
async def killswitch_disable(request: Request):
    """Flush killswitch rules — WARNING: traffic may leak outside VPN."""
    return do_killswitch_disable(request.app.state.state)


@router.post("/qbt/restart", response_model=ActionResponse)
async def qbt_restart(request: Request):
    """Restart the qBittorrent service via s6."""
    return do_qbt_restart(request.app.state.config)


@router.post("/qbt/pause", response_model=ActionResponse)
async def qbt_pause_all(request: Request):
    """Pause all torrents."""
    return do_qbt_pause(request.app.state.config)


@router.post("/qbt/resume", response_model=ActionResponse)
async def qbt_resume_all(request: Request):
    """Resume all torrents."""
    return do_qbt_resume(request.app.state.config)
