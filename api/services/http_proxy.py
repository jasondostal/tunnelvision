"""HTTP CONNECT proxy — RFC 7231 tunnel for routing clients through VPN.

Allows non-Docker clients (phones, laptops, IoT devices) to route traffic
through the VPN tunnel by configuring this as their HTTP proxy.

Lifecycle: started/stopped in FastAPI lifespan, same as watchdog/mqtt.
"""

import asyncio
import base64
import logging

from api.config import Config
from api.constants import ServiceState
from api.services.state import StateManager

logger = logging.getLogger(__name__)

_CONNECT_RESPONSE = b"HTTP/1.1 200 Connection Established\r\n\r\n"
_AUTH_REQUIRED = b"HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm=\"TunnelVision\"\r\n\r\n"
_BAD_REQUEST = b"HTTP/1.1 400 Bad Request\r\n\r\n"
_BAD_GATEWAY = b"HTTP/1.1 502 Bad Gateway\r\n\r\n"


class HttpProxyService:
    """HTTP CONNECT proxy server."""

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
        """Start the proxy server."""
        if not self.config.http_proxy_enabled:
            return
        asyncio.create_task(self._start())

    async def _start(self) -> None:
        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                "0.0.0.0",
                self.config.http_proxy_port,
            )
            self._state.write("http_proxy_state", ServiceState.RUNNING)
            logger.info(f"HTTP proxy listening on 0.0.0.0:{self.config.http_proxy_port}")
        except Exception as e:
            logger.error(f"HTTP proxy failed to start: {e}")
            self._state.write("http_proxy_state", ServiceState.ERROR)

    def stop(self) -> None:
        """Stop the proxy server."""
        if self._server:
            self._server.close()
            self._server = None
        self._state.write("http_proxy_state", ServiceState.DISABLED)
        logger.info("HTTP proxy stopped")

    def _check_auth(self, headers: dict[str, str]) -> bool:
        """Validate Proxy-Authorization header if credentials are configured."""
        user = self.config.http_proxy_user
        password = self.config.http_proxy_pass
        if not user and not password:
            return True  # No auth required

        auth = headers.get("proxy-authorization", "")
        if not auth.startswith("Basic "):
            return False

        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            provided_user, provided_pass = decoded.split(":", 1)
            return provided_user == user and provided_pass == password
        except Exception:
            return False

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        """Handle a single proxy connection."""
        self._connections += 1
        try:
            # Read the request line
            request_line = await asyncio.wait_for(reader.readline(), timeout=30)
            if not request_line:
                writer.close()
                return

            request_str = request_line.decode("utf-8", errors="replace").strip()
            parts = request_str.split()

            if len(parts) < 3 or parts[0] != "CONNECT":
                writer.write(_BAD_REQUEST)
                await writer.drain()
                writer.close()
                return

            # Parse host:port
            target = parts[1]
            if ":" in target:
                host, port_str = target.rsplit(":", 1)
                try:
                    port = int(port_str)
                except ValueError:
                    writer.write(_BAD_REQUEST)
                    await writer.drain()
                    writer.close()
                    return
            else:
                host = target
                port = 443  # Default HTTPS

            # Read headers
            headers: dict[str, str] = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=30)
                if line in (b"\r\n", b"\n", b""):
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if ":" in decoded:
                    key, value = decoded.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            # Check auth
            if not self._check_auth(headers):
                writer.write(_AUTH_REQUIRED)
                await writer.drain()
                writer.close()
                return

            # Connect to target
            try:
                target_reader, target_writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=30,
                )
            except Exception:
                writer.write(_BAD_GATEWAY)
                await writer.drain()
                writer.close()
                return

            # Send 200 to client
            writer.write(_CONNECT_RESPONSE)
            await writer.drain()

            # Relay bidirectionally
            await self._relay(reader, writer, target_reader, target_writer)

        except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            logger.debug(f"Proxy connection error: {e}")
        finally:
            self._connections -= 1
            try:
                writer.close()
            except Exception:
                pass

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

        # Wait for either direction to finish, then cancel the other
        done, pending = await asyncio.wait(
            {task1, task2}, return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()


# Singleton
_service: HttpProxyService | None = None


def get_http_proxy_service(config: Config | None = None,
                           state_mgr: StateManager | None = None) -> HttpProxyService:
    global _service
    if _service is None:
        if config is None:
            from api.config import load_config
            config = load_config()
        if state_mgr is None:
            state_mgr = StateManager()
        _service = HttpProxyService(config, state_mgr)
    return _service
