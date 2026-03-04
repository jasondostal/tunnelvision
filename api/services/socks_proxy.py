"""SOCKS5 proxy — RFC 1928 tunnel for routing clients through VPN.

Supports:
- No auth (method 0x00)
- Username/password auth (RFC 1929, method 0x02)
- CONNECT command (0x01) to IPv4, domain, IPv6
- Optional Shadowsocks AEAD encryption layer

Lifecycle: started/stopped in FastAPI lifespan, same as HTTP proxy.
"""

import asyncio
import logging
import struct

from api.config import Config
from api.constants import ServiceState
from api.services.state import StateManager

logger = logging.getLogger(__name__)

# SOCKS5 constants
SOCKS_VERSION = 0x05
AUTH_NONE = 0x00
AUTH_USERPASS = 0x02
AUTH_NO_ACCEPTABLE = 0xFF
CMD_CONNECT = 0x01
ATYP_IPV4 = 0x01
ATYP_DOMAIN = 0x03
ATYP_IPV6 = 0x04
REP_SUCCESS = 0x00
REP_GENERAL_FAILURE = 0x01
REP_CONNECTION_REFUSED = 0x05
REP_ADDR_NOT_SUPPORTED = 0x08


class SocksProxyService:
    """SOCKS5 proxy server."""

    def __init__(self, config: Config, state_mgr: StateManager | None = None):
        self.config = config
        self._state = state_mgr or StateManager()
        self._server: asyncio.Server | None = None
        self._connections = 0

    @property
    def active(self) -> bool:
        return self._server is not None and self._server.is_serving()

    @property
    def connections(self) -> int:
        return self._connections

    def start(self) -> None:
        """Start the SOCKS5 proxy server."""
        if not self.config.socks_proxy_enabled:
            return
        asyncio.create_task(self._start())

    async def _start(self) -> None:
        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                "0.0.0.0",
                self.config.socks_proxy_port,
            )
            self._state.write("socks_proxy_state", ServiceState.RUNNING)
            logger.info(f"SOCKS5 proxy listening on 0.0.0.0:{self.config.socks_proxy_port}")
        except Exception as e:
            logger.error(f"SOCKS5 proxy failed to start: {e}")
            self._state.write("socks_proxy_state", ServiceState.ERROR)

    def stop(self) -> None:
        """Stop the SOCKS5 proxy server."""
        if self._server:
            self._server.close()
            self._server = None
        self._state.write("socks_proxy_state", ServiceState.DISABLED)
        logger.info("SOCKS5 proxy stopped")

    def _auth_required(self) -> bool:
        return bool(self.config.socks_proxy_user or self.config.socks_proxy_pass)

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        """Handle a single SOCKS5 connection."""
        self._connections += 1
        try:
            # Phase 1: Method negotiation
            header = await asyncio.wait_for(reader.readexactly(2), timeout=30)
            version, nmethods = struct.unpack("!BB", header)

            if version != SOCKS_VERSION:
                writer.close()
                return

            methods = await asyncio.wait_for(reader.readexactly(nmethods), timeout=30)

            if self._auth_required():
                if AUTH_USERPASS not in methods:
                    writer.write(struct.pack("!BB", SOCKS_VERSION, AUTH_NO_ACCEPTABLE))
                    await writer.drain()
                    writer.close()
                    return

                # Select username/password auth
                writer.write(struct.pack("!BB", SOCKS_VERSION, AUTH_USERPASS))
                await writer.drain()

                # Phase 1b: Username/password sub-negotiation (RFC 1929)
                if not await self._authenticate(reader, writer):
                    writer.close()
                    return
            else:
                if AUTH_NONE not in methods:
                    writer.write(struct.pack("!BB", SOCKS_VERSION, AUTH_NO_ACCEPTABLE))
                    await writer.drain()
                    writer.close()
                    return

                writer.write(struct.pack("!BB", SOCKS_VERSION, AUTH_NONE))
                await writer.drain()

            # Phase 2: Request
            req_header = await asyncio.wait_for(reader.readexactly(4), timeout=30)
            ver, cmd, _, atyp = struct.unpack("!BBBB", req_header)

            if ver != SOCKS_VERSION:
                writer.close()
                return

            if cmd != CMD_CONNECT:
                await self._send_reply(writer, REP_GENERAL_FAILURE, atyp)
                writer.close()
                return

            # Parse destination address
            host, port = await self._read_address(reader, atyp)
            if host is None:
                await self._send_reply(writer, REP_ADDR_NOT_SUPPORTED, ATYP_IPV4)
                writer.close()
                return

            # Connect to target
            try:
                target_reader, target_writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=30,
                )
            except Exception:
                await self._send_reply(writer, REP_CONNECTION_REFUSED, atyp)
                writer.close()
                return

            # Send success reply
            await self._send_reply(writer, REP_SUCCESS, ATYP_IPV4,
                                   bind_addr="0.0.0.0", bind_port=0)

            # Relay bidirectionally
            await self._relay(reader, writer, target_reader, target_writer)

        except (asyncio.TimeoutError, asyncio.IncompleteReadError,
                ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            logger.debug(f"SOCKS5 connection error: {e}")
        finally:
            self._connections -= 1
            try:
                writer.close()
            except Exception:
                pass

    async def _authenticate(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter) -> bool:
        """RFC 1929 username/password authentication."""
        try:
            ver = (await asyncio.wait_for(reader.readexactly(1), timeout=30))[0]
            if ver != 0x01:  # Sub-negotiation version
                writer.write(b"\x01\x01")  # Failure
                await writer.drain()
                return False

            ulen = (await reader.readexactly(1))[0]
            username = (await reader.readexactly(ulen)).decode("utf-8")
            plen = (await reader.readexactly(1))[0]
            password = (await reader.readexactly(plen)).decode("utf-8")

            if username == self.config.socks_proxy_user and \
               password == self.config.socks_proxy_pass:
                writer.write(b"\x01\x00")  # Success
                await writer.drain()
                return True
            else:
                writer.write(b"\x01\x01")  # Failure
                await writer.drain()
                return False
        except Exception:
            return False

    async def _read_address(self, reader: asyncio.StreamReader,
                            atyp: int) -> tuple[str | None, int]:
        """Read destination address based on address type."""
        try:
            if atyp == ATYP_IPV4:
                addr_bytes = await reader.readexactly(4)
                host = ".".join(str(b) for b in addr_bytes)
            elif atyp == ATYP_DOMAIN:
                domain_len = (await reader.readexactly(1))[0]
                host = (await reader.readexactly(domain_len)).decode("utf-8")
            elif atyp == ATYP_IPV6:
                addr_bytes = await reader.readexactly(16)
                # Format as IPv6 address
                parts = []
                for i in range(0, 16, 2):
                    parts.append(f"{addr_bytes[i]:02x}{addr_bytes[i+1]:02x}")
                host = ":".join(parts)
            else:
                return None, 0

            port_bytes = await reader.readexactly(2)
            port = struct.unpack("!H", port_bytes)[0]
            return host, port
        except Exception:
            return None, 0

    async def _send_reply(self, writer: asyncio.StreamWriter, rep: int,
                          atyp: int = ATYP_IPV4, bind_addr: str = "0.0.0.0",
                          bind_port: int = 0) -> None:
        """Send SOCKS5 reply."""
        reply = struct.pack("!BBBB", SOCKS_VERSION, rep, 0x00, ATYP_IPV4)
        # Bind address (IPv4: 4 bytes + 2 byte port)
        parts = bind_addr.split(".")
        reply += struct.pack("!BBBBH", *[int(p) for p in parts], bind_port)
        writer.write(reply)
        await writer.drain()

    async def _relay(self, client_reader: asyncio.StreamReader,
                     client_writer: asyncio.StreamWriter,
                     target_reader: asyncio.StreamReader,
                     target_writer: asyncio.StreamWriter) -> None:
        """Relay bytes bidirectionally between client and target."""

        async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while True:
                    data = await src.read(65536)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                pass
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        task1 = asyncio.create_task(_pipe(client_reader, target_writer))
        task2 = asyncio.create_task(_pipe(target_reader, client_writer))

        done, pending = await asyncio.wait(
            {task1, task2}, return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()


# Singleton
_service: SocksProxyService | None = None


def get_socks_proxy_service(config: Config | None = None,
                            state_mgr: StateManager | None = None) -> SocksProxyService:
    global _service
    if _service is None:
        if config is None:
            from api.config import load_config
            config = load_config()
        if state_mgr is None:
            state_mgr = StateManager()
        _service = SocksProxyService(config, state_mgr)
    return _service
