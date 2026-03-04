"""Tests for ExpressVPN provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.providers.expressvpn import ExpressVPNProvider


class TestExpressVPNProvider:

    def test_name(self):
        assert ExpressVPNProvider().name == "expressvpn"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        provider = ExpressVPNProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "2.2.2.2",
            "country": "United Kingdom",
            "city": "London",
            "connection": {"org": "ExpressVPN"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "2.2.2.2"
        assert result.country == "United Kingdom"

    @pytest.mark.asyncio
    async def test_check_connection_handles_failure(self):
        provider = ExpressVPNProvider()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("network error"))

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == ""
        assert result.checked_at is not None

    @pytest.mark.asyncio
    async def test_list_servers_returns_empty(self):
        provider = ExpressVPNProvider()
        servers = await provider.list_servers()
        assert servers == []

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "expressvpn" in PROVIDERS

    def test_meta_is_paste_no_server_list(self):
        from api.services.providers.base import SetupType
        provider = ExpressVPNProvider()
        assert provider.meta.setup_type == SetupType.PASTE
        assert provider.meta.supports_server_list is False
        assert provider.meta.credentials == []
