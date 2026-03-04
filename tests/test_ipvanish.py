"""Tests for IPVanish provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.providers.ipvanish import IPVanishProvider


class TestIPVanishProvider:

    def test_name(self):
        assert IPVanishProvider().name == "ipvanish"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        provider = IPVanishProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "104.1.2.3",
            "country": "United States",
            "city": "Atlanta",
            "connection": {"org": "IPVanish"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "104.1.2.3"
        assert result.country == "United States"

    @pytest.mark.asyncio
    async def test_list_servers_parses_geojson(self):
        provider = IPVanishProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-84.388, 33.749]},
                    "properties": {
                        "hostname": "atl-a01.ipvanish.com",
                        "title": "Atlanta",
                        "countryCode": "US",
                        "capacity": 42,
                        "online": True,
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [4.9, 52.37]},
                    "properties": {
                        "hostname": "ams-a01.ipvanish.com",
                        "title": "Amsterdam",
                        "countryCode": "NL",
                        "capacity": 15,
                        "online": True,
                    },
                },
            ],
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers()

        assert len(servers) == 2
        assert servers[0].hostname == "atl-a01.ipvanish.com"
        assert servers[0].country_code == "US"
        assert servers[0].load == 42
        assert servers[1].hostname == "ams-a01.ipvanish.com"
        assert servers[1].country_code == "NL"

    @pytest.mark.asyncio
    async def test_list_servers_skips_empty_hostname(self):
        provider = IPVanishProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "features": [
                {"properties": {"hostname": "", "countryCode": "US", "capacity": 10}},
                {"properties": {"hostname": "atl-a01.ipvanish.com", "countryCode": "US", "capacity": 10}},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers()

        assert len(servers) == 1

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "ipvanish" in PROVIDERS

    def test_meta_has_server_list(self):
        from api.services.providers.base import SetupType
        provider = IPVanishProvider()
        assert provider.meta.setup_type == SetupType.PASTE
        assert provider.meta.supports_server_list is True
