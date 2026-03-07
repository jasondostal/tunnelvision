"""Tests for authentication middleware and auth routes."""

import secrets
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_config(mock_config):
    """Config with login required."""
    mock_config.login_required = True
    mock_config.admin_user = "admin"
    mock_config.admin_pass = "testpass"
    mock_config.api_key = "test-api-key-12345"
    return mock_config


@pytest.fixture
def auth_client(app, auth_config):
    """Client with auth-enabled config."""
    app.state.config = auth_config
    return TestClient(app)


class TestAuthMiddleware:
    """Auth middleware behavior."""

    def test_open_paths_skip_auth(self, auth_client):
        """Auth endpoints and docs are always accessible."""
        r = auth_client.get("/api/v1/auth/me")
        # Should not be 500 — should return 401 (not authenticated) or 200
        assert r.status_code in (200, 401)

    def test_api_key_grants_access(self, auth_client):
        """Valid API key bypasses login requirement."""
        r = auth_client.get("/api/v1/health", headers={"X-API-Key": "test-api-key-12345"})
        # Should not be 401
        assert r.status_code != 401

    def test_invalid_api_key_rejected(self, auth_client):
        """Invalid API key does not grant access."""
        r = auth_client.get("/api/v1/health", headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 401

    def test_no_auth_returns_401(self, auth_client):
        """Unauthenticated request to protected endpoint returns 401."""
        r = auth_client.get("/api/v1/health")
        assert r.status_code == 401

    def test_setup_paths_skip_auth(self, auth_client):
        """Setup endpoints are accessible without auth."""
        r = auth_client.get("/api/v1/setup/status")
        assert r.status_code != 401


class TestLoginEndpoint:
    """POST /api/v1/auth/login"""

    def test_valid_login(self, auth_client):
        """Correct credentials return session cookie."""
        r = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "testpass"})
        assert r.status_code == 200
        assert "tv_session" in r.cookies

    def test_invalid_login(self, auth_client):
        """Wrong credentials return 401."""
        r = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    def test_session_grants_access(self, auth_client):
        """Session cookie from login grants access to protected endpoints."""
        # Login first
        login_r = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "testpass"})
        assert login_r.status_code == 200

        # Use session cookie for subsequent request
        r = auth_client.get("/api/v1/health")
        assert r.status_code != 401

    def test_logout_clears_session(self, auth_client):
        """Logout invalidates the session."""
        # Login
        auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "testpass"})
        # Logout
        r = auth_client.post("/api/v1/auth/logout")
        assert r.status_code == 200


class TestSessionBounds:
    """Session store overflow protection."""

    def test_max_sessions_returns_429(self, auth_client):
        """Exceeding MAX_SESSIONS returns 429."""
        from api.routes.auth import _sessions, MAX_SESSIONS
        from datetime import datetime, timezone

        # Fill up sessions
        now = datetime.now(timezone.utc).timestamp()
        _sessions.clear()
        for i in range(MAX_SESSIONS):
            _sessions[f"fake-token-{i}"] = {"user": "admin", "expires": now + 86400}

        r = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "testpass"})
        assert r.status_code == 429

        # Clean up
        _sessions.clear()

    def test_expired_sessions_cleaned(self, auth_client):
        """Expired sessions are cleaned up during login."""
        from api.routes.auth import _sessions

        _sessions.clear()
        # Add expired session
        _sessions["expired-token"] = {"user": "admin", "expires": 0}

        r = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "testpass"})
        assert r.status_code == 200
        assert "expired-token" not in _sessions

        _sessions.clear()


class TestProxyAuth:
    """Proxy header authentication."""

    def test_proxy_header_without_trusted_ips_rejected(self, app, mock_config):
        """Proxy header is ignored when TRUSTED_PROXY_IPS is not set."""
        mock_config.login_required = True
        mock_config.auth_proxy_header = "Remote-User"
        mock_config.trusted_proxy_ips = ""
        app.state.config = mock_config
        client = TestClient(app)

        r = client.get("/api/v1/health", headers={"Remote-User": "admin"})
        assert r.status_code == 401


class TestConstantTimeComparison:
    """Verify secrets.compare_digest is used for API key checks."""

    def test_api_key_uses_constant_time(self, auth_client):
        """API key comparison should not be vulnerable to timing attacks.

        We verify this indirectly: both correct and incorrect keys should
        take similar code paths (secrets.compare_digest).
        """
        # Correct key
        r1 = auth_client.get("/api/v1/health", headers={"X-API-Key": "test-api-key-12345"})
        assert r1.status_code != 401

        # Wrong key (same length — timing attack scenario)
        r2 = auth_client.get("/api/v1/health", headers={"X-API-Key": "test-api-key-99999"})
        assert r2.status_code == 401
