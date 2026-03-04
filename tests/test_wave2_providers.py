"""Tests for Wave 2 providers: TorGuard, PrivateVPN, Perfect Privacy, CyberGhost."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTorGuardProvider:

    def test_name(self):
        from api.services.providers.torguard import TorGuardProvider
        assert TorGuardProvider().name == "torguard"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        from api.services.providers.torguard import TorGuardProvider
        provider = TorGuardProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "5.6.7.8",
            "country": "Sweden",
            "city": "Stockholm",
            "connection": {"org": "TorGuard"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "5.6.7.8"
        assert result.country == "Sweden"

    @pytest.mark.asyncio
    async def test_list_servers_returns_empty(self):
        from api.services.providers.torguard import TorGuardProvider
        assert await TorGuardProvider().list_servers() == []

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "torguard" in PROVIDERS

    def test_meta_no_server_list(self):
        from api.services.providers.torguard import TorGuardProvider
        from api.services.providers.base import SetupType
        provider = TorGuardProvider()
        assert provider.meta.setup_type == SetupType.PASTE
        assert provider.meta.supports_server_list is False


class TestPrivateVPNProvider:

    def test_name(self):
        from api.services.providers.privatevpn import PrivateVPNProvider
        assert PrivateVPNProvider().name == "privatevpn"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        from api.services.providers.privatevpn import PrivateVPNProvider
        provider = PrivateVPNProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "1.2.3.4",
            "country": "Sweden",
            "city": "Stockholm",
            "connection": {"org": "PrivateVPN"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "1.2.3.4"
        assert result.country == "Sweden"

    @pytest.mark.asyncio
    async def test_list_servers_returns_empty(self):
        from api.services.providers.privatevpn import PrivateVPNProvider
        assert await PrivateVPNProvider().list_servers() == []

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "privatevpn" in PROVIDERS


class TestPerfectPrivacyProvider:

    def test_name(self):
        from api.services.providers.perfectprivacy import PerfectPrivacyProvider
        assert PerfectPrivacyProvider().name == "perfectprivacy"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        from api.services.providers.perfectprivacy import PerfectPrivacyProvider
        provider = PerfectPrivacyProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "185.1.2.3",
            "country": "Germany",
            "city": "Hamburg",
            "connection": {"org": "Perfect Privacy"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "185.1.2.3"
        assert result.country == "Germany"

    def test_no_wireguard_support(self):
        from api.services.providers.perfectprivacy import PerfectPrivacyProvider
        provider = PerfectPrivacyProvider()
        assert provider.meta.supports_wireguard is False
        assert provider.meta.supports_openvpn is True

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "perfectprivacy" in PROVIDERS


class TestCyberGhostProvider:

    def test_name(self):
        from api.services.providers.cyberghost import CyberGhostProvider
        assert CyberGhostProvider().name == "cyberghost"

    @pytest.mark.asyncio
    async def test_check_connection_returns_check(self):
        from api.services.providers.cyberghost import CyberGhostProvider
        provider = CyberGhostProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "2.3.4.5",
            "country": "Romania",
            "city": "Bucharest",
            "connection": {"org": "CyberGhost"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "2.3.4.5"
        assert result.country == "Romania"

    def test_no_wireguard_support(self):
        from api.services.providers.cyberghost import CyberGhostProvider
        provider = CyberGhostProvider()
        assert provider.meta.supports_wireguard is False
        assert provider.meta.supports_openvpn is True

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "cyberghost" in PROVIDERS
