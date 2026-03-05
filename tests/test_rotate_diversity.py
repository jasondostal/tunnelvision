"""Tests for rotate_server country diversity.

Ensures that when no country filter is set, rotate picks from a random country
rather than always landing on the globally highest-scoring one.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes.connect import ConnectResponse
from api.services.providers.base import ServerInfo
from api.services.state import StateManager

client = TestClient(app)


def _server(hostname: str, country: str, city: str = "City") -> ServerInfo:
    return ServerInfo(hostname=hostname, country=country, city=city, public_key="key")


@pytest.fixture(autouse=True)
def _app_state(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    app.state.state = StateManager(state_dir=state_dir)
    cfg = MagicMock()
    cfg.vpn_provider = "mullvad"
    cfg.vpn_country = ""
    cfg.vpn_city = ""
    cfg.api_auth_required = False
    cfg.login_required = False
    app.state.config = cfg


@pytest.fixture(autouse=True)
def _patch_history():
    with patch("api.routes.connect.log_event"):
        yield


class TestRotateCountryDiversity:
    def test_no_filter_avoids_current_country(self):
        """With no country filter, rotate must not pick the current server's country."""
        servers = [
            _server("ch1.example.com", "Switzerland"),
            _server("ch2.example.com", "Switzerland"),
            _server("de1.example.com", "Germany"),
            _server("us1.example.com", "United States"),
        ]
        app.state.state.vpn_server_hostname = "ch1.example.com"

        mock_provider = MagicMock()
        mock_provider.meta.supports_server_list = True
        mock_provider.list_servers = AsyncMock(return_value=servers)

        captured = []

        async def fake_connect(body, request):
            captured.append(body)
            return ConnectResponse(success=True, hostname="de1.example.com", country="Germany")

        with patch("api.routes.connect.get_provider", return_value=mock_provider), \
             patch("api.routes.connect.connect_to_server", new=AsyncMock(side_effect=fake_connect)), \
             patch("api.services.settings.load_settings", return_value={}):
            resp = client.post("/api/v1/vpn/rotate")

        assert resp.status_code == 200
        assert len(captured) == 1
        assert captured[0].country != "Switzerland"
        assert captured[0].country in {"Germany", "United States"}

    def test_no_filter_diverse_over_many_calls(self):
        """Over many rotations, multiple countries should appear — not just one."""
        servers = [
            _server("ch1.example.com", "Switzerland"),
            _server("de1.example.com", "Germany"),
            _server("us1.example.com", "United States"),
            _server("nl1.example.com", "Netherlands"),
        ]
        # Start with no current server — all countries eligible
        app.state.state.vpn_server_hostname = ""

        mock_provider = MagicMock()
        mock_provider.meta.supports_server_list = True
        mock_provider.list_servers = AsyncMock(return_value=servers)

        seen_countries = set()

        async def fake_connect(body, request):
            seen_countries.add(body.country)
            return ConnectResponse(success=True)

        with patch("api.routes.connect.get_provider", return_value=mock_provider), \
             patch("api.routes.connect.connect_to_server", new=AsyncMock(side_effect=fake_connect)), \
             patch("api.services.settings.load_settings", return_value={}):
            for _ in range(40):
                client.post("/api/v1/vpn/rotate")

        assert len(seen_countries) > 1, (
            f"Expected multiple countries over 40 rotations, only got: {seen_countries}"
        )

    def test_country_filter_respected(self):
        """With a country filter set, rotate stays within that country (no random country)."""
        app.state.state.vpn_server_hostname = "ch1.example.com"
        app.state.config.vpn_country = "ch"

        mock_provider = MagicMock()
        mock_provider.meta.supports_server_list = True

        captured = []

        async def fake_connect(body, request):
            captured.append(body)
            return ConnectResponse(success=True, hostname="ch2.example.com", country="Switzerland")

        with patch("api.routes.connect.get_provider", return_value=mock_provider), \
             patch("api.routes.connect.connect_to_server", new=AsyncMock(side_effect=fake_connect)), \
             patch("api.services.settings.load_settings", return_value={"vpn_country": "ch"}):
            resp = client.post("/api/v1/vpn/rotate")

        assert resp.status_code == 200
        assert captured[0].country == "ch"
        # list_servers should NOT have been called — no country-picking needed
        mock_provider.list_servers.assert_not_called()

    def test_city_filter_respected(self):
        """With a city filter set (no country), rotate also skips country-picking."""
        app.state.state.vpn_server_hostname = "ch-zrh1.example.com"
        app.state.config.vpn_city = "Zurich"

        mock_provider = MagicMock()
        mock_provider.meta.supports_server_list = True

        captured = []

        async def fake_connect(body, request):
            captured.append(body)
            return ConnectResponse(success=True)

        with patch("api.routes.connect.get_provider", return_value=mock_provider), \
             patch("api.routes.connect.connect_to_server", new=AsyncMock(side_effect=fake_connect)), \
             patch("api.services.settings.load_settings", return_value={"vpn_city": "Zurich"}):
            resp = client.post("/api/v1/vpn/rotate")

        assert resp.status_code == 200
        assert captured[0].city == "Zurich"
        mock_provider.list_servers.assert_not_called()

    def test_single_country_pool_falls_back_gracefully(self):
        """When all servers share the current country, no country is excluded — still works."""
        servers = [
            _server("ch1.example.com", "Switzerland"),
            _server("ch2.example.com", "Switzerland"),
        ]
        app.state.state.vpn_server_hostname = "ch1.example.com"

        mock_provider = MagicMock()
        mock_provider.meta.supports_server_list = True
        mock_provider.list_servers = AsyncMock(return_value=servers)

        captured = []

        async def fake_connect(body, request):
            captured.append(body)
            return ConnectResponse(success=True, hostname="ch2.example.com", country="Switzerland")

        with patch("api.routes.connect.get_provider", return_value=mock_provider), \
             patch("api.routes.connect.connect_to_server", new=AsyncMock(side_effect=fake_connect)), \
             patch("api.services.settings.load_settings", return_value={}):
            resp = client.post("/api/v1/vpn/rotate")

        assert resp.status_code == 200
        assert len(captured) == 1
        # Falls back to unfiltered: country=None, hostname still excluded
        assert captured[0].country is None
        assert captured[0].exclude_hostname == "ch1.example.com"

    def test_unknown_current_hostname_all_countries_eligible(self):
        """If current hostname isn't in the server list, all countries are candidates."""
        servers = [
            _server("ch1.example.com", "Switzerland"),
            _server("de1.example.com", "Germany"),
        ]
        app.state.state.vpn_server_hostname = "stale.unknown.com"

        mock_provider = MagicMock()
        mock_provider.meta.supports_server_list = True
        mock_provider.list_servers = AsyncMock(return_value=servers)

        captured = []

        async def fake_connect(body, request):
            captured.append(body)
            return ConnectResponse(success=True)

        with patch("api.routes.connect.get_provider", return_value=mock_provider), \
             patch("api.routes.connect.connect_to_server", new=AsyncMock(side_effect=fake_connect)), \
             patch("api.services.settings.load_settings", return_value={}):
            resp = client.post("/api/v1/vpn/rotate")

        assert resp.status_code == 200
        assert captured[0].country in {"Switzerland", "Germany"}

    def test_config_file_provider_unaffected(self):
        """Config-file providers (no server list) are not touched by country logic."""
        mock_provider = MagicMock()
        mock_provider.meta.supports_server_list = False

        captured = []

        async def fake_connect(body, request):
            captured.append(body)
            return ConnectResponse(success=True)

        with patch("api.routes.connect.get_provider", return_value=mock_provider), \
             patch("api.routes.connect.connect_to_server", new=AsyncMock(side_effect=fake_connect)), \
             patch("api.services.settings.load_settings", return_value={}):
            resp = client.post("/api/v1/vpn/rotate")

        assert resp.status_code == 200
        mock_provider.list_servers.assert_not_called()
        assert captured[0].country is None
