"""Port forwarding service — PIA port forwarding with keep-alive.

PIA assigns a port via getSignature, which must be bound and refreshed
periodically or it expires. This service handles the lifecycle.
"""

import asyncio
import base64
import json
import logging
import os
import ssl
from pathlib import Path

from api.config import Config
from api.constants import PORT_FORWARD_INTERVAL, http_client
from api.services.hooks import fire_port_change_hook
from api.services.state import StateManager

logger = logging.getLogger(__name__)

# PIA gateway uses self-signed certs
_no_verify = ssl.create_default_context()
_no_verify.check_hostname = False
_no_verify.verify_mode = ssl.CERT_NONE


class PortForwardService:
    """Manages PIA port forwarding lifecycle."""

    def __init__(self, config: Config | None = None, state_mgr: StateManager | None = None):
        self._config = config
        self._state = state_mgr or StateManager()
        self._task: asyncio.Task | None = None
        self._port: int | None = None
        self._payload: str | None = None
        self._signature: str | None = None

    @property
    def _refresh_interval(self) -> int:
        """Port forward keep-alive interval, configurable via settings."""
        if self._config:
            return self._config.port_forward_interval
        return PORT_FORWARD_INTERVAL

    @property
    def _hook_script(self) -> str:
        return self._config.port_forward_hook if self._config else ""

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
        self._state.delete_forwarded_port()

    async def _run(self, gateway_ip: str, token: str):
        """Get signature, bind port, then keep alive on configured interval."""
        try:
            # Step 1: Get signature
            async with http_client(verify=False) as client:
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

            # Write port to state file and fire hook
            self._state.forwarded_port = str(self._port)
            logger.info(f"Port forwarding: assigned port {self._port}")
            await fire_port_change_hook(self._hook_script, self._port)

            # Step 2: Bind and keep alive
            while True:
                await self._bind_port(gateway_ip)
                await asyncio.sleep(self._refresh_interval)

        except asyncio.CancelledError:
            logger.info("Port forwarding: stopped")
            await fire_port_change_hook(self._hook_script, 0)
        except Exception as e:
            logger.error(f"Port forwarding error: {e}")

    async def _bind_port(self, gateway_ip: str):
        """Bind the forwarded port (must be called periodically)."""
        try:
            async with http_client(verify=False) as client:
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


def get_port_forward_service(config: Config | None = None) -> PortForwardService:
    global _service
    if _service is None:
        _service = PortForwardService(config=config)
    return _service
