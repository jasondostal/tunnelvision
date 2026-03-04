"""Tests for HTTP CONNECT proxy (Phase 5)."""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.http_proxy import HttpProxyService
from api.services.state import StateManager


def _make_config(**overrides):
    """Create a mock Config with HTTP proxy defaults."""
    defaults = {
        "http_proxy_enabled": True,
        "http_proxy_port": 18888,
        "http_proxy_user": "",
        "http_proxy_pass": "",
    }
    defaults.update(overrides)
    config = MagicMock()
    for k, v in defaults.items():
        setattr(config, k, v)
    return config


class TestHttpProxyService:
    """Tests for HttpProxyService lifecycle."""

    def test_initial_state(self):
        svc = HttpProxyService(_make_config())
        assert svc.active is False
        assert svc.connections == 0

    def test_stop_when_not_started(self, tmp_path):
        state = StateManager(tmp_path)
        svc = HttpProxyService(_make_config(), state_mgr=state)
        svc.stop()  # Should not raise
        assert svc.active is False

    def test_start_disabled(self):
        config = _make_config(http_proxy_enabled=False)
        svc = HttpProxyService(config)
        svc.start()  # Should be a no-op
        assert svc._server is None


class TestProxyAuth:
    """Tests for proxy authentication."""

    def test_no_auth_required(self):
        svc = HttpProxyService(_make_config(http_proxy_user="", http_proxy_pass=""))
        assert svc._check_auth({}) is True

    def test_auth_required_valid(self):
        svc = HttpProxyService(_make_config(http_proxy_user="admin", http_proxy_pass="secret"))
        creds = base64.b64encode(b"admin:secret").decode()
        assert svc._check_auth({"proxy-authorization": f"Basic {creds}"}) is True

    def test_auth_required_invalid(self):
        svc = HttpProxyService(_make_config(http_proxy_user="admin", http_proxy_pass="secret"))
        creds = base64.b64encode(b"admin:wrong").decode()
        assert svc._check_auth({"proxy-authorization": f"Basic {creds}"}) is False

    def test_auth_missing_header(self):
        svc = HttpProxyService(_make_config(http_proxy_user="admin", http_proxy_pass="secret"))
        assert svc._check_auth({}) is False

    def test_auth_malformed_header(self):
        svc = HttpProxyService(_make_config(http_proxy_user="admin", http_proxy_pass="secret"))
        assert svc._check_auth({"proxy-authorization": "Bearer token"}) is False

    def test_auth_invalid_base64(self):
        svc = HttpProxyService(_make_config(http_proxy_user="admin", http_proxy_pass="secret"))
        assert svc._check_auth({"proxy-authorization": "Basic !!invalid!!"}) is False

    def test_auth_user_only(self):
        """Auth with only user set (no password)."""
        svc = HttpProxyService(_make_config(http_proxy_user="admin", http_proxy_pass=""))
        creds = base64.b64encode(b"admin:").decode()
        assert svc._check_auth({"proxy-authorization": f"Basic {creds}"}) is True

    def test_auth_password_with_colon(self):
        """Password containing colons should work (split on first colon only)."""
        svc = HttpProxyService(_make_config(http_proxy_user="user", http_proxy_pass="pass:with:colons"))
        creds = base64.b64encode(b"user:pass:with:colons").decode()
        assert svc._check_auth({"proxy-authorization": f"Basic {creds}"}) is True


class TestProxyConnection:
    """Tests for CONNECT request handling."""

    @pytest.mark.asyncio
    async def test_handle_connect_bad_method(self):
        """Non-CONNECT method should get 400."""
        svc = HttpProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        reader.readline = AsyncMock(side_effect=[
            b"GET http://example.com/ HTTP/1.1\r\n",
            b"\r\n",
        ])

        await svc._handle_client(reader, writer)
        writer.write.assert_called_with(b"HTTP/1.1 400 Bad Request\r\n\r\n")

    @pytest.mark.asyncio
    async def test_handle_connect_empty_request(self):
        """Empty request line should close connection."""
        svc = HttpProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        reader.readline = AsyncMock(return_value=b"")

        await svc._handle_client(reader, writer)
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_handle_connect_auth_failure(self):
        """Missing auth should get 407."""
        svc = HttpProxyService(_make_config(http_proxy_user="admin", http_proxy_pass="secret"))
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        reader.readline = AsyncMock(side_effect=[
            b"CONNECT example.com:443 HTTP/1.1\r\n",
            b"Host: example.com:443\r\n",
            b"\r\n",
        ])

        await svc._handle_client(reader, writer)
        writer.write.assert_called_with(
            b"HTTP/1.1 407 Proxy Authentication Required\r\n"
            b"Proxy-Authenticate: Basic realm=\"TunnelVision\"\r\n\r\n"
        )

    @pytest.mark.asyncio
    async def test_handle_connect_success(self):
        """Successful CONNECT should relay data."""
        svc = HttpProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        reader.readline = AsyncMock(side_effect=[
            b"CONNECT example.com:443 HTTP/1.1\r\n",
            b"Host: example.com:443\r\n",
            b"\r\n",
        ])

        target_reader = AsyncMock()
        target_writer = AsyncMock()
        target_writer.close = MagicMock()
        # Target reads return empty immediately (connection closed)
        target_reader.read = AsyncMock(return_value=b"")
        reader.read = AsyncMock(return_value=b"")

        with patch("asyncio.open_connection", return_value=(target_reader, target_writer)):
            await svc._handle_client(reader, writer)

        # Should have sent 200 Connection Established
        writer.write.assert_any_call(b"HTTP/1.1 200 Connection Established\r\n\r\n")

    @pytest.mark.asyncio
    async def test_handle_connect_target_unreachable(self):
        """Unreachable target should get 502."""
        svc = HttpProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        reader.readline = AsyncMock(side_effect=[
            b"CONNECT unreachable.invalid:443 HTTP/1.1\r\n",
            b"\r\n",
        ])

        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
            await svc._handle_client(reader, writer)

        writer.write.assert_called_with(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")

    @pytest.mark.asyncio
    async def test_default_port_443(self):
        """CONNECT without port should default to 443."""
        svc = HttpProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        reader.readline = AsyncMock(side_effect=[
            b"CONNECT example.com HTTP/1.1\r\n",
            b"\r\n",
        ])

        target_reader = AsyncMock()
        target_writer = AsyncMock()
        target_writer.close = MagicMock()
        target_reader.read = AsyncMock(return_value=b"")
        reader.read = AsyncMock(return_value=b"")

        with patch("asyncio.open_connection", return_value=(target_reader, target_writer)) as mock_conn:
            await svc._handle_client(reader, writer)

        mock_conn.assert_called_once()
        # Verify it connected to port 443
        call_args = mock_conn.call_args
        assert call_args[0] == ("example.com", 443)

    @pytest.mark.asyncio
    async def test_connection_counter(self):
        """Connection counter should increment/decrement."""
        svc = HttpProxyService(_make_config())
        assert svc.connections == 0

        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()
        reader.readline = AsyncMock(return_value=b"")

        await svc._handle_client(reader, writer)
        # After handling (empty request = immediate close), counter back to 0
        assert svc.connections == 0


class TestSingleton:
    """Test singleton pattern."""

    def test_get_service_returns_same_instance(self):
        from api.services import http_proxy
        # Reset singleton
        http_proxy._service = None
        config = _make_config()
        svc1 = http_proxy.get_http_proxy_service(config)
        svc2 = http_proxy.get_http_proxy_service()
        assert svc1 is svc2
        # Clean up
        http_proxy._service = None
