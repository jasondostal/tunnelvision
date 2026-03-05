"""Config backup and restore — export/import container settings."""

import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

from api.constants import OPENVPN_DIR, SETTINGS_PATH, WIREGUARD_DIR

router = APIRouter()

BACKUP_PATHS = [
    str(SETTINGS_PATH),
    "/config/qBittorrent/config/qBittorrent.conf",
]


@router.get("/backup")
async def create_backup():
    """Export container config as a tar.gz archive.

    Includes: tunnelvision.yml, qBittorrent.conf, and VPN config files.
    Does NOT include downloads, torrent data, or secrets beyond what's in the configs.
    """
    buf = io.BytesIO()

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Static config files
        for path_str in BACKUP_PATHS:
            path = Path(path_str)
            if path.exists():
                tar.add(str(path), arcname=path.name)

        # WireGuard configs
        if WIREGUARD_DIR.exists():
            for conf in WIREGUARD_DIR.glob("*.conf"):
                tar.add(str(conf), arcname=f"wireguard/{conf.name}")

        # OpenVPN configs
        if OPENVPN_DIR.exists():
            for conf in list(OPENVPN_DIR.glob("*.ovpn")) + list(OPENVPN_DIR.glob("*.conf")):
                tar.add(str(conf), arcname=f"openvpn/{conf.name}")

        # Metadata
        meta = json.dumps({
            "version": "1.1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "type": "tunnelvision-backup",
        }).encode()
        info = tarfile.TarInfo(name="backup-meta.json")
        info.size = len(meta)
        tar.addfile(info, io.BytesIO(meta))

    buf.seek(0)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    return StreamingResponse(
        buf,
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename=tunnelvision-backup-{timestamp}.tar.gz"},
    )


@router.post("/restore")
async def restore_backup(file: UploadFile = File(...)):
    """Restore config from a backup archive. Requires container restart after."""
    content = await file.read()
    buf = io.BytesIO(content)

    restored = []
    try:
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name == "backup-meta.json":
                    continue

                # Security: prevent path traversal
                if member.name.startswith("/") or ".." in member.name:
                    continue

                if member.name == "tunnelvision.yml":
                    tar.extract(member, "/config", filter="data")
                    restored.append(member.name)
                elif member.name == "qBittorrent.conf":
                    tar.extract(member, "/config/qBittorrent/config", filter="data")
                    restored.append(member.name)
                elif member.name.startswith("wireguard/"):
                    WIREGUARD_DIR.mkdir(parents=True, exist_ok=True)
                    tar.extract(member, "/config", filter="data")
                    restored.append(member.name)
                elif member.name.startswith("openvpn/"):
                    OPENVPN_DIR.mkdir(parents=True, exist_ok=True)
                    tar.extract(member, "/config", filter="data")
                    restored.append(member.name)

    except Exception as e:
        return {"success": False, "error": str(e)}

    return {
        "success": True,
        "restored": restored,
        "message": "Config restored. Restart the container for changes to take effect.",
    }
