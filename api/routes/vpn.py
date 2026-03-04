"""VPN status endpoints — the core differentiator."""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from api.constants import KillswitchState, VpnState
from api.models import VPNStatusResponse, VPNIPResponse
from api.routes.events import broadcast

# Track last state for change detection
_last_state: dict = {}

router = APIRouter()


@router.get("/vpn/status", response_model=VPNStatusResponse)
async def vpn_status(request: Request):
    """Full VPN connection status with transfer stats and location."""
    config = request.app.state.config
    state_mgr = request.app.state.state

    # Sidecar mode: read all VPN state from gluetun
    if config.vpn_provider == "gluetun":
        from api.services.providers.gluetun import GluetunProvider
        gluetun = GluetunProvider(config)
        gluetun_status = await gluetun.get_vpn_status()
        state = VpnState.UP if gluetun_status == "running" else VpnState.DOWN
        check = await gluetun.check_connection()
        public_ip = check.ip
        country = check.country
        city = check.city
        vpn_ip = ""
        endpoint = ""
        killswitch = "gluetun"  # Gluetun manages the firewall
    else:
        state = state_mgr.read("vpn_state", VpnState.DISABLED if not config.vpn_enabled else VpnState.UNKNOWN)
        public_ip = state_mgr.public_ip
        country = state_mgr.country
        city = state_mgr.city
        vpn_ip = state_mgr.vpn_ip
        endpoint = state_mgr.vpn_endpoint
        killswitch = state_mgr.killswitch_state

    # Parse timestamps
    connected_since = None
    started_at = state_mgr.vpn_started_at
    if started_at:
        try:
            connected_since = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            pass

    # Parse handshake
    last_handshake = None
    hs_epoch = state_mgr.last_handshake
    if hs_epoch and hs_epoch != "0":
        try:
            last_handshake = datetime.fromtimestamp(int(hs_epoch), tz=timezone.utc)
        except (ValueError, OSError):
            pass

    # Transfer stats
    rx = int(state_mgr.rx_bytes or "0")
    tx = int(state_mgr.tx_bytes or "0")

    # Human-readable location
    location = ""
    if city and country:
        location = f"{city}, {country}"
    elif country:
        location = country

    # Human-readable uptime
    uptime = ""
    if connected_since:
        delta = datetime.now(timezone.utc) - connected_since
        total_secs = int(delta.total_seconds())
        if total_secs < 60:
            uptime = f"{total_secs}s"
        elif total_secs < 3600:
            uptime = f"{total_secs // 60}m"
        elif total_secs < 86400:
            uptime = f"{total_secs // 3600}h {(total_secs % 3600) // 60}m"
        else:
            uptime = f"{total_secs // 86400}d {(total_secs % 86400) // 3600}h"

    # Port forwarding (PIA or gluetun)
    forwarded_port = None
    if config.vpn_provider == "gluetun":
        from api.services.providers.gluetun import GluetunProvider
        gluetun = GluetunProvider(config)
        forwarded_port = await gluetun.get_forwarded_port()
    else:
        pf_str = state_mgr.forwarded_port
        if pf_str:
            try:
                forwarded_port = int(pf_str)
            except ValueError:
                pass

    response = VPNStatusResponse(
        state=state,
        public_ip=public_ip,
        vpn_ip=vpn_ip,
        endpoint=endpoint,
        country=country,
        city=city,
        location=location,
        connected_since=connected_since,
        uptime=uptime,
        last_handshake=last_handshake,
        transfer_rx=rx,
        transfer_tx=tx,
        killswitch=killswitch,
        provider=config.vpn_provider,
        forwarded_port=forwarded_port,
    )

    # Broadcast state changes to SSE clients
    current = {"state": state, "public_ip": public_ip, "killswitch": killswitch, "forwarded_port": forwarded_port}
    if current != _last_state:
        broadcast("vpn_status", response.model_dump(mode="json"))
        _last_state.update(current)

    return response


@router.get("/vpn/history")
async def vpn_history(limit: int = 50):
    """Connection history — server rotations, disconnects, reconnects."""
    from api.services.history import get_history
    return {"history": get_history(limit)}


@router.get("/vpn/ip", response_model=VPNIPResponse)
async def vpn_ip(request: Request):
    """Just the public IP — for Homepage widgets and quick checks."""
    state_mgr = request.app.state.state
    ip = state_mgr.read("public_ip", "unknown")
    state = state_mgr.vpn_state

    return VPNIPResponse(
        ip=ip,
        vpn_active=state == VpnState.UP,
    )
