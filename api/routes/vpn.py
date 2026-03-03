"""VPN status endpoints — the core differentiator."""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from api.models import VPNStatusResponse, VPNIPResponse

router = APIRouter()


def _read_state(path: str, default: str = "") -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return default


@router.get("/vpn/status", response_model=VPNStatusResponse)
async def vpn_status(request: Request):
    """Full VPN connection status with transfer stats and location."""
    config = request.app.state.config

    state = _read_state("/var/run/tunnelvision/vpn_state", "disabled" if not config.vpn_enabled else "unknown")
    public_ip = _read_state("/var/run/tunnelvision/public_ip")
    vpn_ip = _read_state("/var/run/tunnelvision/vpn_ip")
    endpoint = _read_state("/var/run/tunnelvision/vpn_endpoint")
    killswitch = _read_state("/var/run/tunnelvision/killswitch_state", "disabled")
    country = _read_state("/var/run/tunnelvision/country")
    city = _read_state("/var/run/tunnelvision/city")

    # Parse timestamps
    connected_since = None
    started_at = _read_state("/var/run/tunnelvision/vpn_started_at")
    if started_at:
        try:
            connected_since = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            pass

    # Parse handshake
    last_handshake = None
    hs_epoch = _read_state("/var/run/tunnelvision/last_handshake")
    if hs_epoch and hs_epoch != "0":
        try:
            last_handshake = datetime.fromtimestamp(int(hs_epoch), tz=timezone.utc)
        except (ValueError, OSError):
            pass

    # Transfer stats
    rx = int(_read_state("/var/run/tunnelvision/rx_bytes", "0") or "0")
    tx = int(_read_state("/var/run/tunnelvision/tx_bytes", "0") or "0")

    return VPNStatusResponse(
        state=state,
        public_ip=public_ip,
        vpn_ip=vpn_ip,
        endpoint=endpoint,
        country=country,
        city=city,
        connected_since=connected_since,
        last_handshake=last_handshake,
        transfer_rx=rx,
        transfer_tx=tx,
        killswitch=killswitch,
        provider=config.vpn_provider,
    )


@router.get("/vpn/ip", response_model=VPNIPResponse)
async def vpn_ip(request: Request):
    """Just the public IP — for Homepage widgets and quick checks."""
    config = request.app.state.config
    ip = _read_state("/var/run/tunnelvision/public_ip", "unknown")
    state = _read_state("/var/run/tunnelvision/vpn_state", "disabled")

    return VPNIPResponse(
        ip=ip,
        vpn_active=state == "up",
    )


@router.get("/vpn/widget")
async def vpn_widget(request: Request):
    """Widget-optimized endpoint — everything Homepage needs in one call.

    Returns flat, simple fields designed for Homepage's customapi widget.
    Works with any VPN provider — country/city come from geo-IP services.
    """
    state = _read_state("/var/run/tunnelvision/vpn_state", "unknown")
    public_ip = _read_state("/var/run/tunnelvision/public_ip", "unknown")
    country = _read_state("/var/run/tunnelvision/country", "unknown")
    city = _read_state("/var/run/tunnelvision/city", "unknown")
    killswitch = _read_state("/var/run/tunnelvision/killswitch_state", "disabled")
    rx = int(_read_state("/var/run/tunnelvision/rx_bytes", "0") or "0")
    tx = int(_read_state("/var/run/tunnelvision/tx_bytes", "0") or "0")

    # Human-readable location
    location = ""
    if city and country:
        location = f"{city}, {country}"
    elif country:
        location = country

    # Human-readable transfer
    def _human_bytes(b: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

    return {
        "vpn": state,
        "ip": public_ip,
        "location": location,
        "country": country,
        "city": city,
        "killswitch": killswitch,
        "download": _human_bytes(rx),
        "upload": _human_bytes(tx),
    }
