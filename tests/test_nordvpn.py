"""Tests for NordVPN provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.providers.nordvpn import NordVPNProvider


class TestNordVPNProvider:

    def test_name(self):
        assert NordVPNProvider().name == "nordvpn"

    @pytest.mark.asyncio
    async def test_check_connection_primary(self):
        provider = NordVPNProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ip": "1.2.3.4",
            "country": "United States",
            "isp": {"name": "NordVPN"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "1.2.3.4"
        assert result.country == "United States"
        assert result.is_vpn_ip is True

    @pytest.mark.asyncio
    async def test_check_connection_fallback(self):
        """Falls back to geo-IP when primary endpoint fails."""
        provider = NordVPNProvider()

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("primary down")
            resp = MagicMock()
            resp.json.return_value = {"ip": "5.6.7.8", "country": "Germany", "city": "Frankfurt"}
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = mock_get

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            result = await provider.check_connection()

        assert result.ip == "5.6.7.8"
        assert result.country == "Germany"

    @pytest.mark.asyncio
    async def test_list_servers_parses_api(self):
        provider = NordVPNProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "hostname": "us1234.nordvpn.com",
                "station": "1.2.3.4",
                "status": "online",
                "load": 45,
                "locations": [{
                    "country": {
                        "name": "United States",
                        "code": "US",
                        "city": {"name": "Dallas", "dns_name": "dallas"},
                    }
                }],
                "technologies": [{
                    "identifier": "wireguard_udp",
                    "metadata": [{"name": "public_key", "value": "pubkey123="}],
                }],
                "categories": [{"name": "Standard VPN servers"}],
            },
            {
                "hostname": "us-p2p.nordvpn.com",
                "station": "2.3.4.5",
                "status": "online",
                "load": 20,
                "locations": [{
                    "country": {
                        "name": "United States",
                        "code": "US",
                        "city": {"name": "New York", "dns_name": "nyc"},
                    }
                }],
                "technologies": [{
                    "identifier": "wireguard_udp",
                    "metadata": [{"name": "public_key", "value": "pubkey456="}],
                }],
                "categories": [{"name": "P2P"}],
            },
            {
                "hostname": "offline.nordvpn.com",
                "station": "9.9.9.9",
                "status": "offline",
                "load": 0,
                "locations": [{"country": {"name": "US", "code": "US", "city": {}}}],
                "technologies": [{
                    "identifier": "wireguard_udp",
                    "metadata": [{"name": "public_key", "value": "pubkey789="}],
                }],
                "categories": [],
            },
            {
                "hostname": "no-wg.nordvpn.com",
                "station": "10.10.10.10",
                "status": "online",
                "load": 10,
                "locations": [{"country": {"name": "US", "code": "US", "city": {}}}],
                "technologies": [{"identifier": "openvpn_tcp", "metadata": []}],
                "categories": [],
            },
        ]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers()

        # offline and non-WG servers are excluded
        assert len(servers) == 2
        assert servers[0].hostname == "us1234.nordvpn.com"
        assert servers[0].public_key == "pubkey123="
        assert servers[0].country_code == "US"
        assert servers[0].city == "Dallas"
        assert servers[0].load == 45
        assert servers[0].p2p is False

        assert servers[1].hostname == "us-p2p.nordvpn.com"
        assert servers[1].p2p is True

    @pytest.mark.asyncio
    async def test_list_servers_double_vpn_is_multihop(self):
        provider = NordVPNProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{
            "hostname": "us-dv.nordvpn.com",
            "station": "1.1.1.1",
            "status": "online",
            "load": 30,
            "locations": [{"country": {"name": "US", "code": "US", "city": {}}}],
            "technologies": [{
                "identifier": "wireguard_udp",
                "metadata": [{"name": "public_key", "value": "key="}],
            }],
            "categories": [{"name": "Double VPN"}],
        }]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("api.constants.httpx.AsyncClient", return_value=mock_client):
            servers = await provider.list_servers()

        assert len(servers) == 1
        assert servers[0].multihop is True

    def test_provider_registered(self):
        from api.services.vpn import PROVIDERS
        assert "nordvpn" in PROVIDERS

    def test_meta_is_account_type(self):
        from api.services.providers.base import SetupType
        provider = NordVPNProvider()
        assert provider.meta.setup_type == SetupType.ACCOUNT
        assert provider.meta.supports_server_list is True
