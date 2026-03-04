"""NAT-PMP port forwarding — RFC 6886 implementation.

ProtonVPN (and some other providers) use NAT-PMP for port forwarding.
The protocol is trivially simple — raw UDP to gateway:5351.

Request format (12 bytes):
  - Version (1 byte): 0
  - Opcode (1 byte): 1 (UDP) or 2 (TCP)
  - Reserved (2 bytes): 0
  - Internal port (2 bytes, big-endian)
  - External port (2 bytes, big-endian): 0 for any
  - Lifetime (4 bytes, big-endian): 60 seconds

Response format (16 bytes):
  - Version (1 byte): 0
  - Opcode (1 byte): 128 + request opcode
  - Result (2 bytes): 0 = success
  - Epoch (4 bytes)
  - Internal port (2 bytes)
  - External port (2 bytes)
  - Lifetime (4 bytes)

Same lifecycle pattern as PIA's port_forward.py.
"""

import asyncio
import logging
import socket
import struct

from api.constants import (
    NATPMP_LIFETIME,
    NATPMP_PORT,
    NATPMP_REFRESH_INTERVAL,
    TIMEOUT_QUICK,
)
from api.services.hooks import fire_port_change_hook
from api.services.state import StateManager

logger = logging.getLogger(__name__)

NATPMP_VERSION = 0
OPCODE_UDP = 1
OPCODE_TCP = 2


def build_request(opcode: int = OPCODE_UDP, internal_port: int = 0,
                  external_port: int = 0, lifetime: int = NATPMP_LIFETIME) -> bytes:
    """Build a NAT-PMP mapping request packet."""
    return struct.pack("!BBHHHi",
                       NATPMP_VERSION, opcode, 0,
                       internal_port, external_port, lifetime)


def parse_response(data: bytes) -> dict | None:
    """Parse a NAT-PMP mapping response packet."""
    if len(data) < 16:
        return None
    try:
        version, opcode, result, epoch, internal, external, lifetime = \
            struct.unpack("!BBHiHHi", data[:16])
        if result != 0:
            logger.warning(f"NAT-PMP error: result code {result}")
            return None
        return {
            "version": version,
            "opcode": opcode,
            "epoch": epoch,
            "internal_port": internal,
            "external_port": external,
            "lifetime": lifetime,
        }
    except struct.error:
        return None


class NatPMPService:
    """Manages NAT-PMP port forwarding lifecycle."""

    def __init__(self, config=None, state_mgr: StateManager | None = None):
        self._config = config
        self._state = state_mgr or StateManager()
        self._task: asyncio.Task | None = None
        self._port: int | None = None

    @property
    def _hook_script(self) -> str:
        return self._config.port_forward_hook if self._config else ""

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def active(self) -> bool:
        return self._port is not None and self._task is not None and not self._task.done()

    def start(self, gateway_ip: str):
        """Start NAT-PMP port forwarding."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._run(gateway_ip))

    def stop(self):
        """Stop port forwarding."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._port = None
        self._state.delete_forwarded_port()
        asyncio.get_event_loop().create_task(
            fire_port_change_hook(self._hook_script, 0)
        )

    async def _run(self, gateway_ip: str):
        """Request mapping, then keep alive before lifetime expires."""
        try:
            while True:
                result = await self._request_mapping(gateway_ip)
                if result:
                    ext_port = result["external_port"]
                    if ext_port != self._port:
                        self._port = ext_port
                        self._state.forwarded_port = str(ext_port)
                        logger.info(f"NAT-PMP: mapped external port {ext_port}")
                        await fire_port_change_hook(self._hook_script, ext_port)
                else:
                    logger.warning("NAT-PMP: mapping request failed")

                await asyncio.sleep(NATPMP_REFRESH_INTERVAL)

        except asyncio.CancelledError:
            logger.info("NAT-PMP: stopped")
        except Exception as e:
            logger.error(f"NAT-PMP error: {e}")

    async def _request_mapping(self, gateway_ip: str, opcode: int = OPCODE_UDP,
                               lifetime: int = NATPMP_LIFETIME) -> dict | None:
        """Send a NAT-PMP request and parse the response."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(TIMEOUT_QUICK)
            sock.sendto(build_request(opcode, lifetime=lifetime), (gateway_ip, NATPMP_PORT))
            data, _ = sock.recvfrom(256)
            sock.close()
            return parse_response(data)
        except Exception as e:
            logger.warning(f"NAT-PMP request failed: {e}")
            return None


# Singleton
_service: NatPMPService | None = None


def get_natpmp_service(config=None) -> NatPMPService:
    global _service
    if _service is None:
        _service = NatPMPService(config=config)
    return _service
