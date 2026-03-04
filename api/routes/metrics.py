"""Prometheus /metrics endpoint — text exposition format."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


def _metric(name: str, value: float | int | str, help_text: str, type_: str = "gauge",
            labels: dict[str, str] | None = None) -> str:
    """Format a single Prometheus metric."""
    lines = [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} {type_}",
    ]
    if labels:
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        lines.append(f"{name}{{{label_str}}} {value}")
    else:
        lines.append(f"{name} {value}")
    return "\n".join(lines)


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics(request: Request):
    """Prometheus metrics in text exposition format."""
    state_mgr = request.app.state.state
    metrics: list[str] = []

    # VPN state
    vpn_state = state_mgr.vpn_state
    vpn_up = 1 if vpn_state == "up" else 0
    metrics.append(_metric("tunnelvision_vpn_up", vpn_up, "Whether the VPN tunnel is up (1) or down (0)"))

    # VPN uptime
    started_at = state_mgr.vpn_started_at
    if started_at:
        try:
            from datetime import datetime
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            uptime = time.time() - start.timestamp()
            metrics.append(_metric("tunnelvision_vpn_connected_seconds", round(uptime, 1),
                                   "Seconds since VPN connected"))
        except ValueError:
            pass

    # Killswitch
    ks = state_mgr.killswitch_state
    metrics.append(_metric("tunnelvision_killswitch_active", 1 if ks == "active" else 0,
                           "Whether the killswitch is active (1) or disabled (0)"))

    # Public IP info (as labels on a gauge)
    public_ip = state_mgr.public_ip
    country = state_mgr.country
    city = state_mgr.city
    if public_ip:
        metrics.append(_metric("tunnelvision_public_ip_info", 1,
                               "Public IP information",
                               labels={"ip": public_ip, "country": country, "city": city}))

    # Transfer
    rx = int(state_mgr.rx_bytes or "0")
    tx = int(state_mgr.tx_bytes or "0")
    metrics.append(_metric("tunnelvision_transfer_rx_bytes_total", rx,
                           "Total bytes received through VPN", type_="counter"))
    metrics.append(_metric("tunnelvision_transfer_tx_bytes_total", tx,
                           "Total bytes sent through VPN", type_="counter"))

    # Container uptime
    container_uptime = time.time() - request.app.state.started_at
    metrics.append(_metric("tunnelvision_container_uptime_seconds", round(container_uptime, 1),
                           "Seconds since container started"))

    # Health
    healthy = state_mgr.healthy
    metrics.append(_metric("tunnelvision_healthy", 1 if healthy == "true" else 0,
                           "Overall container health (1=healthy, 0=unhealthy)"))

    return "\n\n".join(metrics) + "\n"
