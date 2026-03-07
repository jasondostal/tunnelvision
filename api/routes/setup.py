"""Setup wizard API — first-run configuration flow."""

import asyncio
import base64
import os
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.constants import (
    GLUETUN_DEFAULT_URL,
    OPENVPN_CONF_PATH,
    OPENVPN_CREDS_PATH,
    OPENVPN_DIR,
    SUBPROCESS_TIMEOUT_DEFAULT,
    SUBPROCESS_TIMEOUT_LONG,
    SUBPROCESS_TIMEOUT_QUICK,
    TIMEOUT_FETCH,
    WG_CONF_PATH,
    WIREGUARD_DIR,
    activate_wg_config,
    http_client,
)
from api.services.settings import save_settings
from api.services.state import StateManager

router = APIRouter()


def _require_setup(request: Request):
    """Guard: reject mutating setup calls if setup is already complete."""
    state_mgr: StateManager = request.app.state.state
    if not state_mgr.setup_required:
        return JSONResponse(status_code=403, content={"detail": "Setup already complete"})
    return None


# Dangerous OpenVPN directives that allow arbitrary script execution
_OVPN_DANGEROUS_DIRECTIVES = {
    "up", "down", "route-up", "route-pre-down", "ipchange",
    "auth-user-pass-verify", "client-connect", "client-disconnect",
    "learn-address", "tls-verify", "script-security",
}


def _strip_dangerous_ovpn_directives(config_text: str) -> str:
    """Remove directives that allow arbitrary script execution from .ovpn configs."""
    lines = config_text.splitlines()
    safe_lines = []
    for line in lines:
        stripped = line.strip()
        directive = stripped.split()[0].lower() if stripped and not stripped.startswith("#") else ""
        if directive in _OVPN_DANGEROUS_DIRECTIVES:
            continue
        safe_lines.append(line)
    return "\n".join(safe_lines)


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


class OpenVPNConfigRequest(BaseModel):
    config: str      # .ovpn file content
    username: str = ""
    password: str = ""


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
    mullvad_account: str | None = None
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
        token = await pia_provider.get_token()  # type: ignore[attr-defined]
        if not token:
            return CredentialsResponse(success=False, error="PIA authentication failed — check username and password")
    except Exception:
        return CredentialsResponse(success=False, error="PIA authentication failed — check username and password")
    return None


async def _validate_gluetun(body: CredentialsRequest) -> CredentialsResponse | None:
    """Validate connection to gluetun. Returns error response or None on success."""
    url = (body.gluetun_url or GLUETUN_DEFAULT_URL).rstrip("/")
    try:
        headers = {}
        if body.gluetun_api_key:
            headers["X-Api-Key"] = body.gluetun_api_key
        async with http_client() as client:
            resp = await client.get(f"{url}/v1/vpn/status", headers=headers)
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
    has_config = WG_CONF_PATH.exists() or OPENVPN_CONF_PATH.exists()

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
    """Available VPN providers — auto-discovered from provider metadata."""
    from api.services.vpn import get_all_provider_meta
    return {"providers": get_all_provider_meta()}


@router.post("/setup/provider")
async def select_provider(body: ProviderSelectRequest, request: Request):
    """Select VPN provider."""
    gate = _require_setup(request)
    if gate:
        return gate
    request.app.state.state.setup_provider = body.provider
    return {"provider": body.provider, "next": "needs_config"}


@router.post("/setup/wireguard")
async def upload_wireguard_config(body: WireGuardConfigRequest, request: Request):
    """Accept WireGuard config content and write to /config/wireguard/wg0.conf."""
    gate = _require_setup(request)
    if gate:
        return gate
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


async def _geo_ip_check() -> tuple[str, str, str]:
    """Geo-IP check — returns (public_ip, country, city). Empty strings on failure."""
    try:
        async with http_client(timeout=TIMEOUT_FETCH) as client:
            resp = await client.get("https://ipwho.is/")
            resp.raise_for_status()
            data = resp.json()
        return data.get("ip", ""), data.get("country", ""), data.get("city", "")
    except Exception:
        return "", "", ""


@router.post("/setup/generate-keypair")
async def generate_keypair():
    """Generate a WireGuard keypair. Returns both private and public key.

    The private key is returned once — store it immediately. The public key
    must be registered with your VPN provider before connecting.
    """
    try:
        private_result = subprocess.run(
            ["wg", "genkey"],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_QUICK,
        )
        if private_result.returncode != 0:
            return {"success": False, "error": "Failed to generate key — is wireguard-tools installed?"}

        private_key = private_result.stdout.strip()

        public_result = subprocess.run(
            ["wg", "pubkey"],
            input=private_key,
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_QUICK,
        )
        if public_result.returncode != 0:
            return {"success": False, "error": "Failed to derive public key"}

        public_key = public_result.stdout.strip()
        return {"success": True, "private_key": private_key, "public_key": public_key}
    except FileNotFoundError:
        return {"success": False, "error": "wireguard-tools not found — install wg or use an existing key"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/setup/openvpn")
async def upload_openvpn_config(body: OpenVPNConfigRequest, request: Request):
    """Accept OpenVPN config content and write to /config/openvpn/provider.ovpn."""
    gate = _require_setup(request)
    if gate:
        return gate
    config_text = body.config.strip()

    # Reject WireGuard configs
    if "[Interface]" in config_text:
        return {"success": False, "error": "This looks like a WireGuard config — use the WireGuard paste flow instead"}

    # Require at least one OpenVPN directive
    if "remote " not in config_text and "client" not in config_text:
        return {"success": False, "error": "Invalid OpenVPN config — missing 'remote' or 'client' directive"}

    # Strip dangerous directives that allow script execution
    config_text = _strip_dangerous_ovpn_directives(config_text)

    OPENVPN_DIR.mkdir(parents=True, exist_ok=True)
    OPENVPN_CONF_PATH.write_text(config_text + "\n")
    os.chmod(OPENVPN_CONF_PATH, 0o600)

    if body.username and body.password:
        OPENVPN_CREDS_PATH.write_text(f"{body.username}\n{body.password}\n")
        os.chmod(OPENVPN_CREDS_PATH, 0o600)

    return {"success": True, "path": str(OPENVPN_CONF_PATH), "next": "needs_verify"}


@router.post("/setup/verify", response_model=VerifyResponse)
async def verify_connection():
    """Bring up the VPN temporarily and verify connectivity. Supports WireGuard and OpenVPN."""
    if WG_CONF_PATH.exists():
        return await _verify_wireguard()
    elif OPENVPN_CONF_PATH.exists():
        return await _verify_openvpn()
    return VerifyResponse(success=False, error="No VPN config found — upload a WireGuard or OpenVPN config first")


async def _verify_wireguard() -> VerifyResponse:
    try:
        activate_wg_config(WG_CONF_PATH)

        result = subprocess.run(
            ["wg-quick", "up", "wg0"],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_LONG,
        )
        if result.returncode != 0:
            return VerifyResponse(
                success=False,
                error=f"WireGuard failed to start: {result.stderr.strip()}"
            )

        public_ip, country, city = await _geo_ip_check()

        # Always tear down — setup/complete will bring it up for real
        subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_DEFAULT)

        if not public_ip:
            return VerifyResponse(success=False, error="VPN connected but couldn't verify public IP")
        return VerifyResponse(success=True, public_ip=public_ip, country=country, city=city)

    except subprocess.TimeoutExpired:
        subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
        return VerifyResponse(success=False, error="Connection timed out")
    except Exception as e:
        subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
        return VerifyResponse(success=False, error=str(e))


async def _verify_openvpn() -> VerifyResponse:
    pid_file = Path("/tmp/ovpn-verify.pid")
    log_file = Path("/tmp/ovpn-verify.log")

    def _teardown() -> None:
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                subprocess.run(["kill", str(pid)], capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
            except Exception:
                pass
        subprocess.run(["killall", "openvpn"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK)

    try:
        # Clean up any lingering process
        _teardown()

        cmd = [
            "openvpn", "--config", str(OPENVPN_CONF_PATH),
            "--daemon",
            "--log", str(log_file),
            "--writepid", str(pid_file),
        ]
        if OPENVPN_CREDS_PATH.exists():
            cmd += ["--auth-user-pass", str(OPENVPN_CREDS_PATH)]

        subprocess.run(cmd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_LONG)

        # Poll for tun0 (up to 30s)
        tun_up = False
        for _ in range(30):
            check = subprocess.run(["ip", "link", "show", "tun0"], capture_output=True)
            if check.returncode == 0:
                tun_up = True
                break
            await asyncio.sleep(1)

        if not tun_up:
            _teardown()
            return VerifyResponse(
                success=False,
                error="OpenVPN started but tun0 interface never appeared — check your config",
            )

        public_ip, country, city = await _geo_ip_check()
        _teardown()

        if not public_ip:
            return VerifyResponse(success=False, error="VPN connected but couldn't verify public IP")
        return VerifyResponse(success=True, public_ip=public_ip, country=country, city=city)

    except subprocess.TimeoutExpired:
        _teardown()
        return VerifyResponse(success=False, error="OpenVPN connection timed out")
    except Exception as e:
        _teardown()
        return VerifyResponse(success=False, error=str(e))


@router.post("/setup/credentials", response_model=CredentialsResponse)
async def setup_credentials(body: CredentialsRequest, request: Request):
    """Validate and persist provider-specific credentials."""
    gate = _require_setup(request)
    if gate:
        return gate
    from api.services.vpn import PROVIDERS

    provider = body.provider.lower()
    state_mgr: StateManager = request.app.state.state
    state_mgr.setup_provider = provider

    # PIA: unique token-exchange auth flow
    if provider == "pia":
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

    # Gluetun sidecar
    if provider == "gluetun":
        err = await _validate_gluetun(body)
        if err:
            return err

        url = (body.gluetun_url or GLUETUN_DEFAULT_URL).rstrip("/")
        settings: dict = {"vpn_provider": "gluetun", "gluetun_url": url}
        if body.gluetun_api_key:
            settings["gluetun_api_key"] = body.gluetun_api_key
        save_settings(settings)
        return CredentialsResponse(success=True, next="done")

    # WireGuard ACCOUNT providers — any provider with supports_wireguard=True
    # (Mullvad, IVPN, NordVPN, Windscribe, Surfshark, AirVPN, etc.)
    provider_cls = PROVIDERS.get(provider)
    if provider_cls is not None:
        meta = provider_cls.get_meta()
        if meta.supports_wireguard:
            err = _validate_wireguard_creds(body)
            if err:
                return err

            settings = {
                "vpn_provider": provider,
                "wireguard_private_key": body.private_key.strip(),  # type: ignore[union-attr]
                "wireguard_addresses": body.addresses.strip(),  # type: ignore[union-attr]
            }
            if body.dns:
                settings["vpn_dns"] = body.dns.strip()
            if body.mullvad_account and provider == "mullvad":
                settings["mullvad_account"] = body.mullvad_account.strip()
            save_settings(settings)
            return CredentialsResponse(success=True, next="server")

    # PASTE / OPENVPN providers — just persist provider selection
    save_settings({"vpn_provider": provider})
    return CredentialsResponse(success=True, next="config")


@router.post("/setup/server")
async def setup_server(body: ServerSelectRequest, request: Request):
    """Select a server and generate WireGuard config. Reuses connect logic."""
    from api.routes.connect import ConnectRequest, connect_to_server
    result = await connect_to_server(ConnectRequest(hostname=body.hostname), request)
    return result


@router.post("/setup/complete")
async def complete_setup(request: Request):
    """Finalize setup — mark setup as complete and signal s6 to restart services."""
    state_mgr: StateManager = request.app.state.state
    provider = state_mgr.setup_provider or "custom"

    # Gluetun manages VPN externally — no local config needed
    has_wg = WG_CONF_PATH.exists()
    has_ovpn = OPENVPN_CONF_PATH.exists()
    if provider != "gluetun" and not has_wg and not has_ovpn:
        return {"success": False, "error": "No VPN config found — run /setup/wireguard or /setup/openvpn first"}

    # Persist provider + vpn_type so it survives container restarts
    settings: dict = {"vpn_provider": provider}
    if has_ovpn and not has_wg:
        settings["vpn_type"] = "openvpn"
    save_settings(settings)

    # Mark setup complete
    state_mgr.setup_required = False

    # Signal s6 to restart the init chain + services
    try:
        subprocess.run(["s6-svc", "-r", "/run/service/svc-qbittorrent"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
    except Exception:
        pass

    return {
        "success": True,
        "provider": provider,
        "message": "Setup complete. Restarting services — refresh in a few seconds.",
    }
