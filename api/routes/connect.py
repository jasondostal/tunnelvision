"""Server connection management — select, rotate, reconnect.

Two rotation modes:
1. API-capable providers (Mullvad): auto-generate wg0.conf for any server
2. Config-file rotation: drop multiple .conf/.ovpn files, we pick randomly
"""

import os
import random
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.constants import (
    OPENVPN_DIR,
    SUBPROCESS_TIMEOUT_DEFAULT,
    SUBPROCESS_TIMEOUT_LONG,
    SUBPROCESS_TIMEOUT_QUICK,
    SUBPROCESS_TIMEOUT_VPN,
    WG_CONF_PATH,
    WIREGUARD_DIR,
    activate_wg_config,
)
from api.services.providers.base import ConnectError, ServerFilter
from api.services.state import StateManager
from api.services.vpn import get_provider
from api.services.history import log_event
from api.routes.events import broadcast

router = APIRouter()


class ConnectRequest(BaseModel):
    country: str | None = None
    city: str | None = None
    hostname: str | None = None
    owned_only: bool | None = None
    p2p: bool | None = None
    streaming: bool | None = None
    port_forward: bool | None = None
    secure_core: bool | None = None
    multihop: bool | None = None
    max_load: int | None = None
    exclude_hostname: str | None = None  # Internal: rotation avoids reconnecting same server


class ConnectResponse(BaseModel):
    success: bool
    hostname: str = ""
    country: str = ""
    city: str = ""
    config_file: str = ""
    error: str = ""


def _list_config_files() -> list[Path]:
    """Find all VPN config files for rotation."""
    files: list[Path] = []
    if WIREGUARD_DIR.exists():
        files.extend(WIREGUARD_DIR.glob("*.conf"))
    if OPENVPN_DIR.exists():
        files.extend(OPENVPN_DIR.glob("*.ovpn"))
        files.extend(OPENVPN_DIR.glob("*.conf"))
    return sorted(files)


@router.post("/vpn/connect", response_model=ConnectResponse)
async def connect_to_server(body: ConnectRequest, request: Request):
    """Connect to a VPN server.

    Mullvad provider: picks random server from pool, auto-generates config.
    Custom provider with multiple configs: picks random config file.
    Custom provider with one config: reconnects using it.
    """
    config = request.app.state.config
    state_mgr: StateManager = request.app.state.state
    provider = get_provider(config.vpn_provider, config)

    # --- API-capable providers: unified connect pipeline ---
    if provider.meta.supports_server_list:
        return await _connect_provider(body, provider, state_mgr, config)

    # --- Config-file rotation (custom/other providers) ---
    configs = _list_config_files()
    if not configs:
        return ConnectResponse(success=False, error="No VPN config files found")

    # Pick random config
    chosen = random.choice(configs)

    # Symlink as the active config
    vpn_type = "openvpn" if chosen.suffix == ".ovpn" else "wireguard"
    state_mgr.vpn_type = vpn_type

    if vpn_type == "wireguard":
        activate_wg_config(chosen)

    state_mgr.active_config = chosen.name
    result = await _reconnect_vpn(vpn_type)
    result.config_file = chosen.name
    return result


@router.post("/vpn/reconnect", response_model=ConnectResponse)
async def reconnect(request: Request):
    """Reconnect to VPN using current config."""
    vpn_type = request.app.state.state.vpn_type
    return await _reconnect_vpn(vpn_type)


@router.post("/vpn/rotate", response_model=ConnectResponse)
async def rotate_server(request: Request):
    """Pick a new server and reconnect, avoiding the current one.

    Mullvad: scored selection (load + speed) from pool, excluding current server.
    Custom: pick different config file from /config/wireguard/ or /config/openvpn/.

    Re-reads country/city from settings YAML so rotation filters are hot-reloadable.
    """
    config = request.app.state.config
    state_mgr: StateManager = request.app.state.state
    # Hot-reload: prefer settings YAML over frozen Config
    try:
        from api.services.settings import load_settings
        settings = load_settings()
        country = settings.get("vpn_country", config.vpn_country) or None
        city = settings.get("vpn_city", config.vpn_city) or None
    except Exception:
        country = config.vpn_country or None
        city = config.vpn_city or None
    current = state_mgr.vpn_server_hostname or ""
    return await connect_to_server(ConnectRequest(country=country, city=city, exclude_hostname=current), request)


@router.get("/vpn/configs")
async def list_configs(request: Request):
    """List available VPN config files (for config-file rotation)."""
    configs = _list_config_files()
    active = request.app.state.state.active_config

    return {
        "count": len(configs),
        "active": active,
        "configs": [
            {
                "name": f.name,
                "path": str(f),
                "type": "openvpn" if f.suffix == ".ovpn" else "wireguard",
                "active": f.name == active,
            }
            for f in configs
        ],
        "hint": "Drop multiple .conf or .ovpn files to enable rotation. POST /vpn/rotate picks a random one."
            if len(configs) <= 1 else f"{len(configs)} configs available for rotation.",
    }


@router.post("/vpn/configs/{name}/activate", response_model=ConnectResponse)
async def activate_config(name: str, request: Request):
    """Switch VPN to a specific config file by name."""
    configs = _list_config_files()
    matching = [f for f in configs if f.name == name]
    if not matching:
        return ConnectResponse(success=False, error=f"Config '{name}' not found")

    config_file = matching[0]
    vpn_type = "openvpn" if config_file.suffix == ".ovpn" else "wireguard"
    state_mgr: StateManager = request.app.state.state
    config = request.app.state.config

    try:
        if vpn_type == "wireguard":
            # Read config, strip PostUp/PostDown (we manage routing)
            content = config_file.read_text()
            clean_lines = [
                line for line in content.splitlines()
                if not line.strip().lower().startswith(("postup", "postdown"))
            ]

            subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_DEFAULT)

            os.makedirs("/etc/wireguard", exist_ok=True)
            wg_conf = Path("/etc/wireguard/wg0.conf")
            wg_conf.write_text("\n".join(clean_lines))
            os.chmod(wg_conf, 0o600)

            result = subprocess.run(
                ["wg-quick", "up", "wg0"],
                capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_LONG,
            )
            if result.returncode != 0:
                return ConnectResponse(success=False, error=result.stderr.strip())

            if config.killswitch_enabled:
                subprocess.run(
                    ["/etc/s6-overlay/scripts/init-killswitch.sh"],
                    capture_output=True, timeout=SUBPROCESS_TIMEOUT_DEFAULT,
                )
        else:
            subprocess.run(["killall", "openvpn"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
            import asyncio
            await asyncio.sleep(2)
            result = subprocess.run(
                ["/etc/s6-overlay/scripts/init-vpn.sh"],
                capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_VPN,
            )
            if result.returncode != 0:
                return ConnectResponse(success=False, error="OpenVPN reconnect failed")

        state_mgr.vpn_type = vpn_type
        state_mgr.active_config = config_file.name
        log_event("config_activated", {"config": config_file.name, "vpn_type": vpn_type})
        broadcast("vpn_status", {"event": "config_activated", "config": config_file.name})
        return ConnectResponse(success=True, config_file=config_file.name)

    except Exception as e:
        log_event("config_activate_failed", {"config": config_file.name, "error": str(e)})
        return ConnectResponse(success=False, error=str(e))


def _select_server(servers, exclude_hostname: str = ""):
    """Score servers by load and speed; pick randomly from the top tier.

    Scoring:
    - Load (0-100): primary signal. load=0 means unknown, treated as 50.
    - speed_gbps: secondary signal, normalized to 0-1 (10 Gbps = max).
    - Picks randomly from the top 5 to distribute traffic across best options.

    If the current server is the only option (e.g. forced by country/city filter),
    it's allowed through so the caller doesn't get stuck.
    """
    from api.services.providers.base import ServerInfo

    candidates = [s for s in servers if s.hostname != exclude_hostname]
    if not candidates:
        candidates = list(servers)

    def _score(s: ServerInfo) -> float:
        load_pct = s.load if s.load and s.load > 0 else 50
        load_score = 1.0 - (load_pct / 100.0)
        speed_score = min((s.speed_gbps or 0) / 10.0, 1.0)
        return load_score * 0.7 + speed_score * 0.3

    ranked = sorted(candidates, key=_score, reverse=True)
    top = ranked[:min(5, len(ranked))]
    return random.choice(top)


async def _connect_provider(body: ConnectRequest, provider, state_mgr: StateManager, config=None) -> ConnectResponse:
    """Unified connect pipeline for all API-capable providers.

    1. List & filter servers (prefer port-forward capable if enabled)
    2. Pick server (by hostname or random)
    3. Resolve credentials + peer config (provider-specific)
    4. Write wg0.conf
    5. Reconnect VPN
    6. Post-connect hooks (port forwarding, etc.)
    """
    server_filter = ServerFilter(
        country=body.country, city=body.city, owned_only=body.owned_only,
        p2p=body.p2p, streaming=body.streaming, port_forward=body.port_forward,
        secure_core=body.secure_core, multihop=body.multihop, max_load=body.max_load,
    )
    servers = await provider.list_servers(filter=server_filter)

    if not servers:
        desc = ""
        if body.country:
            desc += f" country={body.country}"
        if body.city:
            desc += f" city={body.city}"
        return ConnectResponse(success=False, error=f"No servers found{desc}")

    # Prefer port-forward-capable servers if port forwarding is enabled
    if config and config.port_forward_enabled:
        pf_servers = [s for s in servers if s.port_forward]
        if pf_servers:
            servers = pf_servers

    # Pick server
    if body.hostname:
        matching = [s for s in servers if s.hostname == body.hostname]
        if not matching:
            return ConnectResponse(success=False, error=f"Server {body.hostname} not found")
        server = matching[0]
    else:
        server = _select_server(servers, exclude_hostname=body.exclude_hostname or "")

    # Resolve credentials + peer config (provider handles key exchange if needed)
    try:
        peer = await provider.resolve_connect(server, config)
    except ConnectError as e:
        return ConnectResponse(success=False, error=str(e))

    # Write wg0.conf
    WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)
    WG_CONF_PATH.write_text(
        f"[Interface]\n"
        f"PrivateKey = {peer.private_key}\n"
        f"Address = {peer.address}\n"
        f"DNS = {peer.dns}\n\n"
        f"[Peer]\n"
        f"PublicKey = {peer.public_key}\n"
        f"Endpoint = {peer.endpoint}:{peer.port}\n"
        f"AllowedIPs = 0.0.0.0/0\n"
    )
    os.chmod(WG_CONF_PATH, 0o600)

    state_mgr.vpn_type = "wireguard"
    state_mgr.vpn_server_hostname = server.hostname
    state_mgr.active_config = "wg0.conf"

    result = await _reconnect_vpn("wireguard")
    result.hostname = server.hostname
    result.country = server.country
    result.city = server.city

    # Post-connect hooks (port forwarding, etc.)
    if result.success:
        await provider.post_connect(server, config, peer)

    return result


async def _reconnect_vpn(vpn_type: str = "wireguard") -> ConnectResponse:
    """Tear down and bring up VPN."""
    try:
        if vpn_type == "wireguard":
            # Sync config to /etc/wireguard/ so wg-quick reads the current version.
            # init-vpn.sh only runs once at startup; rotate/connect write to
            # /config/wireguard/wg0.conf which wg-quick doesn't read directly.
            if WG_CONF_PATH.exists():
                import shutil
                Path("/etc/wireguard").mkdir(parents=True, exist_ok=True)
                shutil.copy2(WG_CONF_PATH, "/etc/wireguard/wg0.conf")
                os.chmod("/etc/wireguard/wg0.conf", 0o600)
            subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_DEFAULT)
            result = subprocess.run(["wg-quick", "up", "wg0"], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_LONG)
            if result.returncode != 0:
                return ConnectResponse(success=False, error=result.stderr.strip())
        elif vpn_type == "openvpn":
            subprocess.run(["killall", "openvpn"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
            # Give it a moment to clean up
            import asyncio
            await asyncio.sleep(2)
            result = subprocess.run(
                ["/etc/s6-overlay/scripts/init-vpn.sh"],
                capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_VPN,
            )
            if result.returncode != 0:
                return ConnectResponse(success=False, error="OpenVPN reconnect failed")

        log_event("reconnect", {"vpn_type": vpn_type})
        return ConnectResponse(success=True)
    except Exception as e:
        log_event("reconnect_failed", {"vpn_type": vpn_type, "error": str(e)})
        return ConnectResponse(success=False, error=str(e))
