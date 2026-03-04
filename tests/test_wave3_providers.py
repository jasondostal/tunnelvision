"""Tests for Wave 3 providers: Privado, PureVPN, VPNSecure, VPN Unlimited,
VyprVPN, FastestVPN, HideMyAss, SlickVPN, Giganews."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


GEO_RESPONSE = {
    "ip": "1.2.3.4",
    "country": "Switzerland",
    "city": "Zurich",
    "connection": {"org": "Test VPN"},
}


def _mock_client(response_data):
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_data
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


class TestPrivadoProvider:
    def test_name(self):
        from api.services.providers.privado import PrivadoProvider
        assert PrivadoProvider().name == "privado"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.privado import PrivadoProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await PrivadoProvider().check_connection()
        assert result.ip == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_list_servers_empty(self):
        from api.services.providers.privado import PrivadoProvider
        assert await PrivadoProvider().list_servers() == []

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "privado" in PROVIDERS


class TestPureVPNProvider:
    def test_name(self):
        from api.services.providers.purevpn import PureVPNProvider
        assert PureVPNProvider().name == "purevpn"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.purevpn import PureVPNProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await PureVPNProvider().check_connection()
        assert result.ip == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_list_servers_empty(self):
        from api.services.providers.purevpn import PureVPNProvider
        assert await PureVPNProvider().list_servers() == []

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "purevpn" in PROVIDERS


class TestVPNSecureProvider:
    def test_name(self):
        from api.services.providers.vpnsecure import VPNSecureProvider
        assert VPNSecureProvider().name == "vpnsecure"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.vpnsecure import VPNSecureProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await VPNSecureProvider().check_connection()
        assert result.ip == "1.2.3.4"

    def test_no_wireguard(self):
        from api.services.providers.vpnsecure import VPNSecureProvider
        p = VPNSecureProvider()
        assert p.meta.supports_wireguard is False
        assert p.meta.supports_openvpn is True

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "vpnsecure" in PROVIDERS


class TestVPNUnlimitedProvider:
    def test_name(self):
        from api.services.providers.vpnunlimited import VPNUnlimitedProvider
        assert VPNUnlimitedProvider().name == "vpnunlimited"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.vpnunlimited import VPNUnlimitedProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await VPNUnlimitedProvider().check_connection()
        assert result.ip == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_list_servers_empty(self):
        from api.services.providers.vpnunlimited import VPNUnlimitedProvider
        assert await VPNUnlimitedProvider().list_servers() == []

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "vpnunlimited" in PROVIDERS


class TestVyprVPNProvider:
    def test_name(self):
        from api.services.providers.vyprvpn import VyprVPNProvider
        assert VyprVPNProvider().name == "vyprvpn"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.vyprvpn import VyprVPNProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await VyprVPNProvider().check_connection()
        assert result.ip == "1.2.3.4"

    def test_no_wireguard(self):
        from api.services.providers.vyprvpn import VyprVPNProvider
        p = VyprVPNProvider()
        assert p.meta.supports_wireguard is False
        assert p.meta.supports_openvpn is True

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "vyprvpn" in PROVIDERS


class TestFastestVPNProvider:
    def test_name(self):
        from api.services.providers.fastestvpn import FastestVPNProvider
        assert FastestVPNProvider().name == "fastestvpn"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.fastestvpn import FastestVPNProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await FastestVPNProvider().check_connection()
        assert result.ip == "1.2.3.4"

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "fastestvpn" in PROVIDERS


class TestHideMyAssProvider:
    def test_name(self):
        from api.services.providers.hidemyass import HideMyAssProvider
        assert HideMyAssProvider().name == "hidemyass"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.hidemyass import HideMyAssProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await HideMyAssProvider().check_connection()
        assert result.ip == "1.2.3.4"

    def test_no_wireguard(self):
        from api.services.providers.hidemyass import HideMyAssProvider
        p = HideMyAssProvider()
        assert p.meta.supports_wireguard is False
        assert p.meta.supports_openvpn is True

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "hidemyass" in PROVIDERS


class TestSlickVPNProvider:
    def test_name(self):
        from api.services.providers.slickvpn import SlickVPNProvider
        assert SlickVPNProvider().name == "slickvpn"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.slickvpn import SlickVPNProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await SlickVPNProvider().check_connection()
        assert result.ip == "1.2.3.4"

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "slickvpn" in PROVIDERS


class TestGiganewsProvider:
    def test_name(self):
        from api.services.providers.giganews import GiganewsProvider
        assert GiganewsProvider().name == "giganews"

    @pytest.mark.asyncio
    async def test_check_connection(self):
        from api.services.providers.giganews import GiganewsProvider
        with patch("api.constants.httpx.AsyncClient", return_value=_mock_client(GEO_RESPONSE)):
            result = await GiganewsProvider().check_connection()
        assert result.ip == "1.2.3.4"

    def test_no_wireguard(self):
        from api.services.providers.giganews import GiganewsProvider
        p = GiganewsProvider()
        assert p.meta.supports_wireguard is False
        assert p.meta.supports_openvpn is True

    def test_registered(self):
        from api.services.vpn import PROVIDERS
        assert "giganews" in PROVIDERS
