"""Tests for Windscribe provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.providers.windscribe import WindscribeProvider


class TestWindscribeProvider:

    def test_name(self):
        assert WindscribeProvider().name == "windscribe"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        provider = WindscribeProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "1.2.3.4",
            "country": "Netherlands",
            "city": "Amsterdam",
            "connection": {"org": "Windscribe"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "1.2.3.4"
        assert result.country == "Netherlands"

    @pytest.mark.asyncio
    async def test_list_servers_parses_api(self):
        provider = WindscribeProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "info": [
                    {
                        "name": "US East",
                        "country_code": "US",
                        "p2p": 1,
                        "nodes": [
                            {"hostname": "ewr-001.whiskergalaxy.com", "weight": 100},
                            {"hostname": "ewr-002.whiskergalaxy.com", "weight": 100},
                        ],
                    },
                    {
                        "name": "Netherlands",
                        "country_code": "NL",
                        "p2p": 0,
                        "nodes": [
                            {"hostname": "ams-001.whiskergalaxy.com", "weight": 100},
                        ],
                    },
                ],
                "version": 42,
            }
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers()

        assert len(servers) == 3
        assert servers[0].hostname == "ewr-001.whiskergalaxy.com"
        assert servers[0].country_code == "US"
        assert servers[0].p2p is True
        assert servers[2].hostname == "ams-001.whiskergalaxy.com"
        assert servers[2].country_code == "NL"
        assert servers[2].p2p is False

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "windscribe" in PROVIDERS

    def test_meta_is_paste_type(self):
        from api.services.providers.base import SetupType
        provider = WindscribeProvider()
        assert provider.meta.setup_type == SetupType.PASTE
        assert provider.meta.supports_server_list is True
        assert provider.meta.credentials == []
