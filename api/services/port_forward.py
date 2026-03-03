"""Port forwarding service — PIA port forwarding with keep-alive.

PIA assigns a port via getSignature, which must be bound and refreshed
every 15 minutes or it expires. This service handles the lifecycle.
"""

import asyncio
import base64
import json
import logging
import os
import ssl
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

STATE_DIR = Path("/var/run/tunnelvision")
PORT_FILE = STATE_DIR / "forwarded_port"

# PIA gateway uses self-signed certs
_no_verify = ssl.create_default_context()
_no_verify.check_hostname = False
_no_verify.verify_mode = ssl.CERT_NONE


class PortForwardService:
    """Manages PIA port forwarding lifecycle."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._port: int | None = None
        self._payload: str | None = None
        self._signature: str | None = None

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def active(self) -> bool:
        return self._port is not None and self._task is not None and not self._task.done()

    def start(self, gateway_ip: str, token: str):
        """Start port forwarding on the given gateway."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._run(gateway_ip, token))

    def stop(self):
        """Stop port forwarding."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._port = None
        self._payload = None
        self._signature = None
        PORT_FILE.unlink(missing_ok=True)

    async def _run(self, gateway_ip: str, token: str):
        """Get signature, bind port, then keep alive every 15 minutes."""
        try:
            # Step 1: Get signature
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                resp = await client.get(
                    f"https://{gateway_ip}:19999/getSignature",
                    params={"token": token},
                )
                resp.raise_for_status()
                data = resp.json()

            self._payload = data.get("payload")
            self._signature = data.get("signature")

            if not self._payload or not self._signature:
                logger.error("Port forwarding: no payload/signature from PIA")
                return

            # Decode port from payload
            decoded = json.loads(base64.b64decode(self._payload))
            self._port = decoded.get("port")

            if not self._port:
                logger.error("Port forwarding: no port in payload")
                return

            # Write port to state file
            PORT_FILE.write_text(str(self._port))
            logger.info(f"Port forwarding: assigned port {self._port}")

            # Step 2: Bind and keep alive
            while True:
                await self._bind_port(gateway_ip)
                await asyncio.sleep(900)  # 15 minutes

        except asyncio.CancelledError:
            logger.info("Port forwarding: stopped")
        except Exception as e:
            logger.error(f"Port forwarding error: {e}")

    async def _bind_port(self, gateway_ip: str):
        """Bind the forwarded port (must be called every 15 min)."""
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                resp = await client.get(
                    f"https://{gateway_ip}:19999/bindPort",
                    params={
                        "payload": self._payload,
                        "signature": self._signature,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "OK":
                logger.debug(f"Port forwarding: bound port {self._port}")
            else:
                logger.warning(f"Port forwarding bind response: {data}")
        except Exception as e:
            logger.warning(f"Port forwarding bind error: {e}")


# Singleton
_service: PortForwardService | None = None


def get_port_forward_service() -> PortForwardService:
    global _service
    if _service is None:
        _service = PortForwardService()
    return _service
