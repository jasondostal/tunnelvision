"""Prometheus /metrics endpoint — text exposition format."""

import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


def _read_state(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except FileNotFoundError:
        return default


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
    config = request.app.state.config
    metrics: list[str] = []

    # VPN state
    vpn_state = _read_state("/var/run/tunnelvision/vpn_state", "unknown")
    vpn_up = 1 if vpn_state == "up" else 0
    metrics.append(_metric("tunnelvision_vpn_up", vpn_up, "Whether the VPN tunnel is up (1) or down (0)"))

    # VPN uptime
    started_at = _read_state("/var/run/tunnelvision/vpn_started_at")
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
    ks = _read_state("/var/run/tunnelvision/killswitch_state", "disabled")
    metrics.append(_metric("tunnelvision_killswitch_active", 1 if ks == "active" else 0,
                           "Whether the killswitch is active (1) or disabled (0)"))

    # Public IP info (as labels on a gauge)
    public_ip = _read_state("/var/run/tunnelvision/public_ip")
    country = _read_state("/var/run/tunnelvision/country")
    city = _read_state("/var/run/tunnelvision/city")
    if public_ip:
        metrics.append(_metric("tunnelvision_public_ip_info", 1,
                               "Public IP information",
                               labels={"ip": public_ip, "country": country, "city": city}))

    # Transfer
    rx = int(_read_state("/var/run/tunnelvision/rx_bytes", "0") or "0")
    tx = int(_read_state("/var/run/tunnelvision/tx_bytes", "0") or "0")
    metrics.append(_metric("tunnelvision_transfer_rx_bytes_total", rx,
                           "Total bytes received through VPN", type_="counter"))
    metrics.append(_metric("tunnelvision_transfer_tx_bytes_total", tx,
                           "Total bytes sent through VPN", type_="counter"))

    # Container uptime
    container_uptime = time.time() - request.app.state.started_at
    metrics.append(_metric("tunnelvision_container_uptime_seconds", round(container_uptime, 1),
                           "Seconds since container started"))

    # Health
    healthy = _read_state("/var/run/tunnelvision/healthy", "true")
    metrics.append(_metric("tunnelvision_healthy", 1 if healthy == "true" else 0,
                           "Overall container health (1=healthy, 0=unhealthy)"))

    return "\n\n".join(metrics) + "\n"
