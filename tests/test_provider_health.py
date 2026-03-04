"""Tests for GET /vpn/provider-health endpoint."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.state import StateManager

client = TestClient(app)


@pytest.fixture(autouse=True)
def _init_app_state(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    app.state.state = StateManager(state_dir=state_dir)
    app.state.config = MagicMock()
    app.state.config.vpn_provider = "custom"
    app.state.config.login_required = False
    app.state.config.api_auth_required = False
    app.state.config.api_key = ""


class TestProviderHealth:
    def test_provider_health_no_ping_url(self):
        """Custom provider has no HEALTH_PING_URL → api_reachable is null."""
        with patch("api.routes.provider.get_provider") as mock_get:
            provider = MagicMock()
            provider.HEALTH_PING_URL = None
            provider.meta.id = "custom"
            provider.meta.display_name = "Custom"
            provider.meta.supports_account_check = False
            provider._server_cache = None
            provider._cache_time = None
            mock_get.return_value = provider

            resp = client.get("/api/v1/vpn/provider-health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["api_reachable"] is None
        assert data["api_latency_ms"] is None
        assert data["provider_id"] == "custom"

    def test_provider_health_api_reachable(self):
        """When ping succeeds, api_reachable=True and latency is populated."""
        with patch("api.routes.provider.get_provider") as mock_get, \
             patch("api.routes.provider.http_client") as mock_ctx:
            provider = MagicMock()
            provider.HEALTH_PING_URL = "https://api.mullvad.net/"
            provider.meta.id = "mullvad"
            provider.meta.display_name = "Mullvad VPN"
            provider.meta.supports_account_check = False
            provider._server_cache = None
            provider._cache_time = None
            mock_get.return_value = provider

            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=MagicMock(status_code=200))
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = client.get("/api/v1/vpn/provider-health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["api_reachable"] is True
        assert isinstance(data["api_latency_ms"], int)
        assert data["api_latency_ms"] >= 0

    def test_provider_health_api_unreachable(self):
        """When ping raises, api_reachable=False."""
        with patch("api.routes.provider.get_provider") as mock_get, \
             patch("api.routes.provider.http_client") as mock_ctx:
            provider = MagicMock()
            provider.HEALTH_PING_URL = "https://api.mullvad.net/"
            provider.meta.id = "mullvad"
            provider.meta.display_name = "Mullvad VPN"
            provider.meta.supports_account_check = False
            provider._server_cache = None
            provider._cache_time = None
            mock_get.return_value = provider

            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=Exception("connection refused"))
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = client.get("/api/v1/vpn/provider-health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["api_reachable"] is False
        assert data["api_latency_ms"] is None

    def test_provider_health_with_cache(self):
        """Populated cache → server_count and cache_age_seconds populated."""
        cache_time = datetime.now(timezone.utc) - timedelta(hours=2)
        fake_servers = [MagicMock(), MagicMock(), MagicMock()]

        with patch("api.routes.provider.get_provider") as mock_get:
            provider = MagicMock()
            provider.HEALTH_PING_URL = None
            provider.meta.id = "mullvad"
            provider.meta.display_name = "Mullvad VPN"
            provider.meta.supports_account_check = False
            provider._server_cache = fake_servers
            provider._cache_time = cache_time
            mock_get.return_value = provider

            resp = client.get("/api/v1/vpn/provider-health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["server_count"] == 3
        assert data["cache_age_seconds"] is not None
        assert data["cache_age_seconds"] >= 7200  # 2h in seconds
        assert data["cache_fresh"] is False  # 2h > 1h TTL → stale

    def test_provider_health_no_cache(self):
        """No cache → server_count, cache_age, cache_fresh all null."""
        with patch("api.routes.provider.get_provider") as mock_get:
            provider = MagicMock()
            provider.HEALTH_PING_URL = None
            provider.meta.id = "custom"
            provider.meta.display_name = "Custom"
            provider.meta.supports_account_check = False
            provider._server_cache = None
            provider._cache_time = None
            mock_get.return_value = provider

            resp = client.get("/api/v1/vpn/provider-health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["server_count"] is None
        assert data["cache_age_seconds"] is None
        assert data["cache_fresh"] is None

    def test_provider_health_account_not_supported(self):
        """supports_account_check=False → no account call, account.available=False."""
        get_account_called = []

        with patch("api.routes.provider.get_provider") as mock_get:
            provider = MagicMock()
            provider.HEALTH_PING_URL = None
            provider.meta.id = "custom"
            provider.meta.display_name = "Custom"
            provider.meta.supports_account_check = False
            provider._server_cache = None
            provider._cache_time = None
            provider.get_account_info = AsyncMock(side_effect=lambda: get_account_called.append(1))
            mock_get.return_value = provider

            resp = client.get("/api/v1/vpn/provider-health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["account"]["available"] is False
        assert len(get_account_called) == 0  # never called

    def test_provider_health_with_account_info(self):
        """supports_account_check=True + account data → full account payload."""
        from api.services.providers.base import AccountInfo

        expires = datetime(2026, 12, 31, tzinfo=timezone.utc)
        account = AccountInfo(expires_at=expires, days_remaining=302, active=True)

        with patch("api.routes.provider.get_provider") as mock_get:
            provider = MagicMock()
            provider.HEALTH_PING_URL = None
            provider.meta.id = "mullvad"
            provider.meta.display_name = "Mullvad VPN"
            provider.meta.supports_account_check = True
            provider._server_cache = None
            provider._cache_time = None
            provider.get_account_info = AsyncMock(return_value=account)
            mock_get.return_value = provider

            resp = client.get("/api/v1/vpn/provider-health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["account"]["available"] is True
        assert data["account"]["active"] is True
        assert data["account"]["days_remaining"] == 302
        assert "2026-12-31" in data["account"]["expires_at"]
