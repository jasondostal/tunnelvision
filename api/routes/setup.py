"""Setup wizard API — first-run configuration flow."""

import base64
import json
import os
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.services.settings import save_settings
from api.services.state import StateManager

router = APIRouter()

WIREGUARD_DIR = Path("/config/wireguard")
WG_CONF_PATH = WIREGUARD_DIR / "wg0.conf"


# -- Models --

class SetupStatus(BaseModel):
    setup_required: bool
    step: str  # needs_provider, needs_config, needs_verify, complete
    provider: str | None = None
    has_config: bool = False


class ProviderInfo(BaseModel):
    id: str
    name: str
    description: str
    setup_type: str  # "paste", "account", "upload"


class WireGuardConfigRequest(BaseModel):
    config: str  # wg0.conf content


class ProviderSelectRequest(BaseModel):
    provider: str


class VerifyResponse(BaseModel):
    success: bool
    public_ip: str = ""
    country: str = ""
    city: str = ""
    error: str = ""


class CredentialsRequest(BaseModel):
    provider: str
    private_key: str | None = None
    addresses: str | None = None
    dns: str | None = None
    pia_user: str | None = None
    pia_pass: str | None = None
    port_forward: bool = False
    gluetun_url: str | None = None
    gluetun_api_key: str | None = None


class CredentialsResponse(BaseModel):
    success: bool
    next: str = ""
    error: str = ""


class ServerSelectRequest(BaseModel):
    hostname: str


# -- Credential validators (per-provider) --

def _validate_wireguard_creds(body: CredentialsRequest) -> CredentialsResponse | None:
    """Validate WG private key + address for Mullvad/IVPN. Returns error response or None on success."""
    if not body.private_key:
        return CredentialsResponse(success=False, error="WireGuard private key is required")
    key = body.private_key.strip()
    if len(key) != 44 or key[-1] != "=":
        return CredentialsResponse(success=False, error="Invalid private key format — expected 44-character base64 string")
    try:
        decoded = base64.b64decode(key)
        if len(decoded) != 32:
            raise ValueError()
    except Exception:
        return CredentialsResponse(success=False, error="Invalid private key — not valid base64")

    if not body.addresses:
        return CredentialsResponse(success=False, error="WireGuard address is required (e.g. 10.x.x.x/32)")
    addr = body.addresses.strip()
    if not re.match(r"^[\d.:a-fA-F]+/\d+", addr):
        return CredentialsResponse(success=False, error="Address should be in CIDR format (e.g. 10.66.0.1/32)")
    return None


async def _validate_pia_creds(body: CredentialsRequest) -> CredentialsResponse | None:
    """Validate PIA username/password by getting a token. Returns error response or None on success."""
    if not body.pia_user or not body.pia_pass:
        return CredentialsResponse(success=False, error="PIA username and password are required")

    try:
        from api.services.vpn import get_provider
        from api.config import Config
        temp_config = Config()
        object.__setattr__(temp_config, "pia_user", body.pia_user)
        object.__setattr__(temp_config, "pia_pass", body.pia_pass)
        pia_provider = get_provider("pia", temp_config)
        token = await pia_provider.get_token()
        if not token:
            return CredentialsResponse(success=False, error="PIA authentication failed — check username and password")
    except Exception:
        return CredentialsResponse(success=False, error="PIA authentication failed — check username and password")
    return None


async def _validate_gluetun(body: CredentialsRequest) -> CredentialsResponse | None:
    """Validate connection to gluetun. Returns error response or None on success."""
    url = (body.gluetun_url or "http://gluetun:8000").rstrip("/")
    try:
        import httpx
        headers = {}
        if body.gluetun_api_key:
            headers["X-Api-Key"] = body.gluetun_api_key
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{url}/v1/openvpn/status", headers=headers)
            resp.raise_for_status()
    except Exception:
        return CredentialsResponse(success=False, error=f"Could not connect to gluetun at {url}")
    return None


# -- Endpoints --

@router.get("/setup/status", response_model=SetupStatus)
async def setup_status(request: Request):
    """Current setup state — drives the wizard UI."""
    state_mgr: StateManager = request.app.state.state
    required = state_mgr.setup_required
    has_config = WG_CONF_PATH.exists()

    # Determine current step
    provider = state_mgr.setup_provider or None

    if not required and has_config:
        step = "complete"
    elif provider is None:
        step = "needs_provider"
    elif not has_config:
        step = "needs_config"
    else:
        step = "needs_verify"

    return SetupStatus(
        setup_required=required,
        step=step,
        provider=provider,
        has_config=has_config,
    )


@router.get("/setup/providers")
async def list_providers():
    """Available VPN providers with setup instructions."""
    return {
        "providers": [
            {
                "id": "mullvad",
                "name": "Mullvad VPN",
                "description": "Privacy-focused VPN. Enter your account number and pick a server.",
                "setup_type": "account",
                "logo": "https://mullvad.net/favicon.ico",
            },
            {
                "id": "ivpn",
                "name": "IVPN",
                "description": "Privacy-focused, open-source. Auto-generates configs, server rotation, connection verification.",
                "setup_type": "account",
            },
            {
                "id": "pia",
                "name": "Private Internet Access",
                "description": "Port forwarding support. Authenticates with username/password, auto-negotiates WireGuard keys.",
                "setup_type": "account",
            },
            {
                "id": "proton",
                "name": "Proton VPN",
                "description": "From the Proton team. Download your WireGuard config from account.protonvpn.com.",
                "setup_type": "paste",
            },
            {
                "id": "gluetun",
                "name": "Gluetun (Sidecar)",
                "description": "Already running gluetun? TunnelVision adds the dashboard, HA integration, and observability layer on top.",
                "setup_type": "sidecar",
            },
            {
                "id": "custom",
                "name": "Custom / Other",
                "description": "Any WireGuard or OpenVPN provider. Paste your config or drop files in the config directory.",
                "setup_type": "paste",
            },
        ]
    }


@router.post("/setup/provider")
async def select_provider(body: ProviderSelectRequest, request: Request):
    """Select VPN provider."""
    request.app.state.state.setup_provider = body.provider
    return {"provider": body.provider, "next": "needs_config"}


@router.post("/setup/wireguard")
async def upload_wireguard_config(body: WireGuardConfigRequest):
    """Accept WireGuard config content and write to /config/wireguard/wg0.conf."""
    config_text = body.config.strip()

    # Basic validation
    if "[Interface]" not in config_text:
        return {"success": False, "error": "Invalid WireGuard config — missing [Interface] section"}
    if "PrivateKey" not in config_text:
        return {"success": False, "error": "Invalid WireGuard config — missing PrivateKey"}
    if "[Peer]" not in config_text:
        return {"success": False, "error": "Invalid WireGuard config — missing [Peer] section"}

    # Write config
    WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)
    WG_CONF_PATH.write_text(config_text + "\n")
    os.chmod(WG_CONF_PATH, 0o600)

    return {"success": True, "path": str(WG_CONF_PATH), "next": "needs_verify"}


@router.post("/setup/verify", response_model=VerifyResponse)
async def verify_connection():
    """Bring up WireGuard temporarily and verify connectivity."""
    if not WG_CONF_PATH.exists():
        return VerifyResponse(success=False, error="No WireGuard config found")

    try:
        # Symlink for wg-quick
        os.makedirs("/etc/wireguard", exist_ok=True)
        if os.path.exists("/etc/wireguard/wg0.conf"):
            os.remove("/etc/wireguard/wg0.conf")
        os.symlink(str(WG_CONF_PATH), "/etc/wireguard/wg0.conf")

        # Bring up tunnel
        result = subprocess.run(
            ["wg-quick", "up", "wg0"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return VerifyResponse(
                success=False,
                error=f"WireGuard failed to start: {result.stderr.strip()}"
            )

        # Check connectivity via geo-IP
        ip_result = subprocess.run(
            ["curl", "-sf", "--max-time", "8", "https://ipwho.is/"],
            capture_output=True, text=True, timeout=12,
        )

        public_ip = ""
        country = ""
        city = ""

        if ip_result.returncode == 0:
            try:
                data = json.loads(ip_result.stdout)
                public_ip = data.get("ip", "")
                country = data.get("country", "")
                city = data.get("city", "")
            except json.JSONDecodeError:
                pass

        # Always tear down — setup/complete will bring it up for real
        subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=10)

        if not public_ip:
            return VerifyResponse(
                success=False,
                error="VPN connected but couldn't verify public IP"
            )

        return VerifyResponse(
            success=True,
            public_ip=public_ip,
            country=country,
            city=city,
        )

    except subprocess.TimeoutExpired:
        subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=5)
        return VerifyResponse(success=False, error="Connection timed out")
    except Exception as e:
        subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=5)
        return VerifyResponse(success=False, error=str(e))


@router.post("/setup/credentials", response_model=CredentialsResponse)
async def setup_credentials(body: CredentialsRequest, request: Request):
    """Validate and persist provider-specific credentials."""
    provider = body.provider.lower()
    state_mgr: StateManager = request.app.state.state
    state_mgr.setup_provider = provider

    if provider in ("mullvad", "ivpn"):
        err = _validate_wireguard_creds(body)
        if err:
            return err

        settings: dict = {
            "vpn_provider": provider,
            "wireguard_private_key": body.private_key.strip(),  # type: ignore[union-attr]
            "wireguard_addresses": body.addresses.strip(),  # type: ignore[union-attr]
        }
        if body.dns:
            settings["vpn_dns"] = body.dns.strip()
        save_settings(settings)
        return CredentialsResponse(success=True, next="server")

    elif provider == "pia":
        err = await _validate_pia_creds(body)
        if err:
            return err

        save_settings({
            "vpn_provider": "pia",
            "pia_user": body.pia_user,
            "pia_pass": body.pia_pass,
            "port_forward_enabled": "true" if body.port_forward else "false",
        })
        return CredentialsResponse(success=True, next="server")

    elif provider == "gluetun":
        err = await _validate_gluetun(body)
        if err:
            return err

        url = (body.gluetun_url or "http://gluetun:8000").rstrip("/")
        settings = {"vpn_provider": "gluetun", "gluetun_url": url}
        if body.gluetun_api_key:
            settings["gluetun_api_key"] = body.gluetun_api_key
        save_settings(settings)
        return CredentialsResponse(success=True, next="done")

    else:
        save_settings({"vpn_provider": provider})
        return CredentialsResponse(success=True, next="config")


@router.post("/setup/server")
async def setup_server(body: ServerSelectRequest, request: Request):
    """Select a server and generate WireGuard config. Reuses connect logic."""
    from api.routes.connect import ConnectRequest, ConnectResponse, connect_to_server
    result = await connect_to_server(ConnectRequest(hostname=body.hostname), request)
    return result


@router.post("/setup/complete")
async def complete_setup(request: Request):
    """Finalize setup — mark setup as complete and signal s6 to restart services."""
    state_mgr: StateManager = request.app.state.state
    provider = state_mgr.setup_provider or "custom"

    # Gluetun manages VPN externally — no WG config needed
    if provider != "gluetun" and not WG_CONF_PATH.exists():
        return {"success": False, "error": "No WireGuard config — run /setup/wireguard first"}

    # Persist provider to settings YAML so it survives container restarts
    save_settings({"vpn_provider": provider})

    # Mark setup complete
    state_mgr.setup_required = False

    # Signal s6 to restart the init chain + services
    try:
        subprocess.run(["s6-svc", "-r", "/run/service/svc-qbittorrent"], capture_output=True, timeout=5)
    except Exception:
        pass

    return {
        "success": True,
        "provider": provider,
        "message": "Setup complete. Restarting services — refresh in a few seconds.",
    }
