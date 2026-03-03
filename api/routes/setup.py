"""Setup wizard API — first-run configuration flow."""

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

WIREGUARD_DIR = Path("/config/wireguard")
WG_CONF_PATH = WIREGUARD_DIR / "wg0.conf"
STATE_DIR = Path("/var/run/tunnelvision")


def _is_setup_required() -> bool:
    try:
        return (STATE_DIR / "setup_required").read_text().strip() == "true"
    except FileNotFoundError:
        return not WG_CONF_PATH.exists()


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


# -- Endpoints --

@router.get("/setup/status", response_model=SetupStatus)
async def setup_status():
    """Current setup state — drives the wizard UI."""
    required = _is_setup_required()
    has_config = WG_CONF_PATH.exists()

    # Determine current step
    provider_file = STATE_DIR / "setup_provider"
    provider = None
    if provider_file.exists():
        provider = provider_file.read_text().strip()

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
                "description": "Open-source VPN. Paste your WireGuard config from the IVPN dashboard.",
                "setup_type": "paste",
            },
            {
                "id": "proton",
                "name": "Proton VPN",
                "description": "From the Proton team. Download your WireGuard config from account.protonvpn.com.",
                "setup_type": "paste",
            },
            {
                "id": "custom",
                "name": "Custom WireGuard",
                "description": "Any WireGuard server. Paste your wg0.conf or generate one from your provider.",
                "setup_type": "paste",
            },
        ]
    }


@router.post("/setup/provider")
async def select_provider(body: ProviderSelectRequest):
    """Select VPN provider."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "setup_provider").write_text(body.provider)
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
            import json
            try:
                data = json.loads(ip_result.stdout)
                public_ip = data.get("ip", "")
                country = data.get("country", "")
                city = data.get("city", "")
            except json.JSONDecodeError:
                pass

        # Bring tunnel back down (setup/complete will bring it up for real)
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
        # Clean up
        subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=5)
        return VerifyResponse(success=False, error="Connection timed out")
    except Exception as e:
        subprocess.run(["wg-quick", "down", "wg0"], capture_output=True, timeout=5)
        return VerifyResponse(success=False, error=str(e))


@router.post("/setup/complete")
async def complete_setup():
    """Finalize setup — mark setup as complete and signal s6 to restart services."""
    if not WG_CONF_PATH.exists():
        return {"success": False, "error": "No WireGuard config — run /setup/wireguard first"}

    # Write provider to env file for s6
    provider = "custom"
    provider_file = STATE_DIR / "setup_provider"
    if provider_file.exists():
        provider = provider_file.read_text().strip()

    # Mark setup complete
    (STATE_DIR / "setup_required").write_text("false")

    # Signal s6 to restart the init chain + services
    # s6-svc -r tells s6 to restart the service
    try:
        # Restart the whole container's service tree by touching a restart flag
        # The health monitor will pick this up, or we restart services directly
        subprocess.run(["s6-svc", "-r", "/run/service/svc-qbittorrent"], capture_output=True, timeout=5)
    except Exception:
        pass

    return {
        "success": True,
        "provider": provider,
        "message": "Setup complete. Restarting services — refresh in a few seconds.",
    }
