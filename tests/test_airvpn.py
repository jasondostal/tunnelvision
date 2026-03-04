"""Tests for AirVPN provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.providers.airvpn import AirVPNProvider


class TestAirVPNProvider:

    def test_name(self):
        assert AirVPNProvider().name == "airvpn"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        provider = AirVPNProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "10.0.0.1",
            "country": "Switzerland",
            "city": "Zurich",
            "connection": {"org": "AirVPN"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "10.0.0.1"
        assert result.country == "Switzerland"

    @pytest.mark.asyncio
    async def test_list_servers_parses_api(self):
        provider = AirVPNProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "Servers": [
                {
                    "public_name": "Adhara",
                    "ip_addresses": ["185.1.2.3"],
                    "country_name": "Netherlands",
                    "country_code": "NL",
                    "city_name": "Amsterdam",
                    "health": 30,
                },
                {
                    "public_name": "Alphard",
                    "ip_addresses": ["93.4.5.6"],
                    "country_name": "Switzerland",
                    "country_code": "CH",
                    "city_name": "Zurich",
                    "health": 10,
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers()

        assert len(servers) == 2
        assert servers[0].hostname == "Adhara"
        assert servers[0].country_code == "NL"
        assert servers[0].ipv4 == "185.1.2.3"
        assert servers[0].load == 30
        assert servers[1].hostname == "Alphard"
        assert servers[1].city == "Zurich"

    @pytest.mark.asyncio
    async def test_get_account_info_no_key(self):
        provider = AirVPNProvider(config=None)
        result = await provider.get_account_info()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_account_info_with_key(self):
        config = MagicMock()
        config.airvpn_api_key = "testkey123"
        provider = AirVPNProvider(config=config)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": "OK", "user": {"expiry_days": 90}}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.get_account_info()

        assert result is not None
        assert result.active is True
        assert result.days_remaining == 90

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "airvpn" in PROVIDERS

    def test_meta_has_api_key_credential(self):
        provider = AirVPNProvider()
        keys = [c.key for c in provider.meta.credentials]
        assert "airvpn_api_key" in keys
        secret_fields = [c for c in provider.meta.credentials if c.key == "airvpn_api_key"]
        assert secret_fields[0].secret is True
        assert secret_fields[0].required is False
