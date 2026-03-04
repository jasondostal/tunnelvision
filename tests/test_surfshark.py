"""Tests for Surfshark provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.providers.surfshark import SurfsharkProvider


class TestSurfsharkProvider:

    def test_name(self):
        assert SurfsharkProvider().name == "surfshark"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        provider = SurfsharkProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "45.76.77.88",
            "country": "United States",
            "city": "Los Angeles",
            "connection": {"org": "Surfshark B.V."},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "45.76.77.88"
        assert result.country == "United States"

    @pytest.mark.asyncio
    async def test_list_servers_parses_api(self):
        provider = SurfsharkProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "connectionName": "de-ber.prod.surfshark.com",
                "country": "Germany",
                "countryCode": "DE",
                "location": "Berlin",
                "ip": "1.2.3.4",
                "load": 55,
            },
            {
                "connectionName": "us-nyc.prod.surfshark.com",
                "country": "United States",
                "countryCode": "US",
                "location": "New York City",
                "ip": "5.6.7.8",
                "load": 30,
            },
        ]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers()

        assert len(servers) == 2
        assert servers[0].hostname == "de-ber.prod.surfshark.com"
        assert servers[0].country_code == "DE"
        assert servers[0].city == "Berlin"
        assert servers[0].load == 55
        assert servers[1].hostname == "us-nyc.prod.surfshark.com"

    def test_list_servers_skips_empty_hostname(self):
        from api.services.providers.surfshark import SurfsharkProvider as P
        import asyncio

        provider = P()
        raw = [
            {"connectionName": "", "country": "US", "countryCode": "US"},
            {"connectionName": "us-nyc.prod.surfshark.com", "country": "US", "countryCode": "US"},
        ]

        async def run():
            mock_resp = MagicMock()
            mock_resp.json.return_value = raw
            mock_resp.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
                return await provider.list_servers()

        servers = asyncio.get_event_loop().run_until_complete(run())
        assert len(servers) == 1

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "surfshark" in PROVIDERS

    def test_meta_is_paste_type(self):
        from api.services.providers.base import SetupType
        provider = SurfsharkProvider()
        assert provider.meta.setup_type == SetupType.PASTE
        assert provider.meta.credentials == []
