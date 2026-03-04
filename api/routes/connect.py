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

from api.services.state import StateManager
from api.services.vpn import get_provider
from api.services.history import log_event

router = APIRouter()

WIREGUARD_DIR = Path("/config/wireguard")
OPENVPN_DIR = Path("/config/openvpn")
WG_CONF_PATH = WIREGUARD_DIR / "wg0.conf"


class ConnectRequest(BaseModel):
    country: str | None = None
    city: str | None = None
    hostname: str | None = None


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

    # --- API-capable providers ---
    if provider.name == "mullvad":
        return await _connect_mullvad(body, provider, state_mgr, config)
    if provider.name == "ivpn":
        return await _connect_ivpn(body, provider, state_mgr, config)
    if provider.name == "pia":
        return await _connect_pia(body, provider, config, state_mgr)

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
        os.makedirs("/etc/wireguard", exist_ok=True)
        if os.path.exists("/etc/wireguard/wg0.conf"):
            os.remove("/etc/wireguard/wg0.conf")
        os.symlink(str(chosen), "/etc/wireguard/wg0.conf")

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
    """Pick a new random server and reconnect.

    Mullvad: new random server from entire pool (or filtered by VPN_COUNTRY/VPN_CITY env).
    Custom: pick different random config file from /config/wireguard/ or /config/openvpn/.
    """
    config = request.app.state.config
    return await connect_to_server(
        ConnectRequest(country=config.vpn_country or None, city=config.vpn_city or None),
        request,
    )


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


async def _connect_mullvad(body: ConnectRequest, provider, state_mgr: StateManager, config=None) -> ConnectResponse:
    """Generate wg0.conf for a Mullvad server and connect."""
    servers = await provider.list_servers(country=body.country, city=body.city)

    if not servers:
        desc = ""
        if body.country:
            desc += f" country={body.country}"
        if body.city:
            desc += f" city={body.city}"
        return ConnectResponse(success=False, error=f"No servers found{desc}")

    # Pick server
    if body.hostname:
        matching = [s for s in servers if s.hostname == body.hostname]
        if not matching:
            return ConnectResponse(success=False, error=f"Server {body.hostname} not found")
        server = matching[0]
    else:
        server = random.choice(servers)

    # Get private key from existing config or env
    private_key = config.wireguard_private_key if config else ""
    address = config.wireguard_addresses if config else ""
    dns = (config.wireguard_dns if config and config.wireguard_dns else "") or "10.64.0.1"

    if not private_key and WG_CONF_PATH.exists():
        for line in WG_CONF_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("PrivateKey"):
                private_key = stripped.split("=", 1)[1].strip()
            elif stripped.startswith("Address") and not address:
                address = stripped.split("=", 1)[1].strip()
            elif stripped.startswith("DNS") and dns == "10.64.0.1":
                dns = stripped.split("=", 1)[1].strip()

    if not private_key:
        return ConnectResponse(
            success=False,
            error="No WireGuard private key. Set WIREGUARD_PRIVATE_KEY env or have an existing wg0.conf.",
        )
    if not address:
        return ConnectResponse(success=False, error="No WireGuard address. Set WIREGUARD_ADDRESSES env.")

    # Fetch server pubkey + IP
    pubkey = ""
    ipv4 = ""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.mullvad.net/www/relays/wireguard/")
            for relay in resp.json():
                if relay.get("hostname") == server.hostname:
                    pubkey = relay.get("pubkey", "")
                    ipv4 = relay.get("ipv4_addr_in", "")
                    break
    except Exception:
        pass

    if not pubkey or not ipv4:
        return ConnectResponse(success=False, error=f"Couldn't get details for {server.hostname}")

    # Write wg0.conf
    WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)
    WG_CONF_PATH.write_text(
        f"[Interface]\n"
        f"PrivateKey = {private_key}\n"
        f"Address = {address}\n"
        f"DNS = {dns}\n\n"
        f"[Peer]\n"
        f"PublicKey = {pubkey}\n"
        f"Endpoint = {ipv4}:51820\n"
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
    return result


async def _connect_ivpn(body: ConnectRequest, provider, state_mgr: StateManager, config=None) -> ConnectResponse:
    """Pick an IVPN server and generate wg0.conf with its public key."""
    servers = await provider.list_servers(country=body.country, city=body.city)

    if not servers:
        desc = ""
        if body.country:
            desc += f" country={body.country}"
        if body.city:
            desc += f" city={body.city}"
        return ConnectResponse(success=False, error=f"No IVPN servers found{desc}")

    if body.hostname:
        matching = [s for s in servers if s.hostname == body.hostname]
        if not matching:
            return ConnectResponse(success=False, error=f"Server {body.hostname} not found")
        server = matching[0]
    else:
        server = random.choice(servers)

    private_key = config.wireguard_private_key if config else ""
    address = config.wireguard_addresses if config else ""
    dns = (config.wireguard_dns if config and config.wireguard_dns else "") or "172.16.0.1"  # IVPN default DNS

    if not private_key and WG_CONF_PATH.exists():
        for line in WG_CONF_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("PrivateKey"):
                private_key = stripped.split("=", 1)[1].strip()
            elif stripped.startswith("Address") and not address:
                address = stripped.split("=", 1)[1].strip()
            elif stripped.startswith("DNS") and dns == "172.16.0.1":
                dns = stripped.split("=", 1)[1].strip()

    if not private_key:
        return ConnectResponse(success=False, error="No WireGuard private key. Set WIREGUARD_PRIVATE_KEY or have an existing wg0.conf.")
    if not address:
        return ConnectResponse(success=False, error="No WireGuard address. Set WIREGUARD_ADDRESSES env.")

    pubkey = getattr(server, "_pubkey", "")
    ipv4 = getattr(server, "_ipv4", "")
    port = getattr(server, "_port", 2049)

    if not pubkey or not ipv4:
        return ConnectResponse(success=False, error=f"Missing pubkey/IP for {server.hostname}")

    WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)
    WG_CONF_PATH.write_text(
        f"[Interface]\n"
        f"PrivateKey = {private_key}\n"
        f"Address = {address}\n"
        f"DNS = {dns}\n\n"
        f"[Peer]\n"
        f"PublicKey = {pubkey}\n"
        f"Endpoint = {ipv4}:{port}\n"
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
    return result


async def _connect_pia(body: ConnectRequest, provider, config, state_mgr: StateManager) -> ConnectResponse:
    """Authenticate with PIA, negotiate WireGuard keys, and connect."""
    import subprocess as _sp

    servers = await provider.list_servers(country=body.country, city=body.city)
    if not servers:
        return ConnectResponse(success=False, error="No PIA servers found")

    # Prefer port-forward-capable servers if port forwarding is enabled
    if config.port_forward_enabled:
        pf_servers = [s for s in servers if getattr(s, "_port_forward", False)]
        if pf_servers:
            servers = pf_servers

    if body.hostname:
        matching = [s for s in servers if s.hostname == body.hostname]
        if not matching:
            return ConnectResponse(success=False, error=f"Server {body.hostname} not found")
        server = matching[0]
    else:
        server = random.choice(servers)

    server_ip = getattr(server, "_ipv4", "")
    if not server_ip:
        return ConnectResponse(success=False, error="No IP for selected server")

    # Get auth token
    token = await provider.get_token()
    if not token:
        return ConnectResponse(success=False, error="PIA auth failed. Check PIA_USER and PIA_PASS.")

    # Generate ephemeral WireGuard keypair
    try:
        privkey_result = _sp.run(["wg", "genkey"], capture_output=True, text=True, timeout=5)
        private_key = privkey_result.stdout.strip()
        pubkey_result = _sp.run(["wg", "pubkey"], input=private_key, capture_output=True, text=True, timeout=5)
        public_key = pubkey_result.stdout.strip()
    except Exception as e:
        return ConnectResponse(success=False, error=f"Key generation failed: {e}")

    # Exchange keys with PIA server
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.get(
                f"https://{server_ip}:1337/addKey",
                params={"pt": token, "pubkey": public_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return ConnectResponse(success=False, error=f"PIA key exchange failed: {e}")

    server_pubkey = data.get("server_key", "")
    our_ip = data.get("peer_ip", "")
    server_port = data.get("server_port", 1337)
    dns_servers = data.get("dns_servers", ["10.0.0.243"])

    if not server_pubkey or not our_ip:
        return ConnectResponse(success=False, error="PIA key exchange returned incomplete data")

    dns = dns_servers[0] if dns_servers else "10.0.0.243"

    WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)
    WG_CONF_PATH.write_text(
        f"[Interface]\n"
        f"PrivateKey = {private_key}\n"
        f"Address = {our_ip}\n"
        f"DNS = {dns}\n\n"
        f"[Peer]\n"
        f"PublicKey = {server_pubkey}\n"
        f"Endpoint = {server_ip}:{server_port}\n"
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

    # Start port forwarding if enabled
    if result.success and config.port_forward_enabled and getattr(server, "_port_forward", False):
        from api.services.port_forward import get_port_forward_service
        pf = get_port_forward_service()
        gateway_ip = data.get("server_vip", server_ip)
        pf.start(gateway_ip, token)

    return result


async def _reconnect_vpn(vpn_type: str = "wireguard") -> ConnectResponse:
    """Tear down and bring up VPN."""
    try:
        if vpn_type == "wireguard":
            subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=10)
            result = subprocess.run(["wg-quick", "up", "wg0"], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return ConnectResponse(success=False, error=result.stderr.strip())
        elif vpn_type == "openvpn":
            subprocess.run(["killall", "openvpn"], capture_output=True, timeout=5)
            # Give it a moment to clean up
            import asyncio
            await asyncio.sleep(2)
            result = subprocess.run(
                ["/etc/s6-overlay/scripts/init-wireguard.sh"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return ConnectResponse(success=False, error="OpenVPN reconnect failed")

        log_event("reconnect", {"vpn_type": vpn_type})
        return ConnectResponse(success=True)
    except Exception as e:
        log_event("reconnect_failed", {"vpn_type": vpn_type, "error": str(e)})
        return ConnectResponse(success=False, error=str(e))
