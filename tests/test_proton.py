"""Tests for ProtonVPN provider (Phase 4)."""

import os
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from api.services.providers.proton import ProtonProvider, FEATURE_PORT_FORWARD


class TestProtonProvider:
    """Tests for ProtonVPN provider class."""

    def test_name(self):
        provider = ProtonProvider()
        assert provider.name == "proton"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        provider = ProtonProvider()
        # Mock httpx to avoid network calls
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "1.2.3.4",
            "country": "Switzerland",
            "city": "Zurich",
            "connection": {"org": "Proton AG"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "1.2.3.4"
        assert result.country == "Switzerland"

    @pytest.mark.asyncio
    async def test_list_servers_parses_api(self):
        provider = ProtonProvider()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "LogicalServers": [
                {
                    "Name": "CH#1",
                    "ExitCountry": "CH",
                    "City": "Zurich",
                    "Features": FEATURE_PORT_FORWARD,
                    "Tier": 2,
                    "Load": 45,
                    "Servers": [
                        {"EntryIP": "1.2.3.4", "ExitIP": "5.6.7.8"},
                    ],
                },
                {
                    "Name": "US#1",
                    "ExitCountry": "US",
                    "City": "New York",
                    "Features": 0,
                    "Tier": 1,
                    "Load": 80,
                    "Servers": [
                        {"EntryIP": "9.10.11.12", "ExitIP": "13.14.15.16"},
                    ],
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers()

        assert len(servers) == 2
        assert servers[0].hostname == "CH#1"
        assert servers[0].country_code == "CH"
        assert servers[0]._port_forward is True
        assert servers[1].hostname == "US#1"
        assert servers[1]._port_forward is False

    @pytest.mark.asyncio
    async def test_list_servers_filters_by_country(self):
        provider = ProtonProvider()
        provider._server_cache = []
        provider._cache_time = None

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "LogicalServers": [
                {
                    "Name": "CH#1", "ExitCountry": "CH", "City": "Zurich",
                    "Features": 0, "Tier": 2, "Load": 40,
                    "Servers": [{"EntryIP": "1.1.1.1", "ExitIP": "2.2.2.2"}],
                },
                {
                    "Name": "US#1", "ExitCountry": "US", "City": "NYC",
                    "Features": 0, "Tier": 1, "Load": 80,
                    "Servers": [{"EntryIP": "3.3.3.3", "ExitIP": "4.4.4.4"}],
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers(country="ch")

        assert len(servers) == 1
        assert servers[0].hostname == "CH#1"

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "proton" in PROVIDERS

    def test_settings_fields_exist(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert "proton_user" in CONFIGURABLE_FIELDS
        assert "proton_pass" in CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["proton_pass"]["secret"] is True

    def test_config_fields_exist(self):
        from api.config import Config
        config = Config()
        assert hasattr(config, "proton_user")
        assert hasattr(config, "proton_pass")
