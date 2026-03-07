"""Shared test fixtures for TunnelVision test suite."""

import types
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_config():
    """Minimal Config mock with common defaults."""
    config = MagicMock()
    config.api_key = None
    config.api_auth_required = False
    config.login_required = False
    config.admin_user = "admin"
    config.admin_pass = "password"
    config.auth_proxy_header = ""
    config.trusted_proxy_ips = ""
    config.qbt_enabled = True
    config.webui_port = 8080
    config.vpn_provider = "custom"
    config.vpn_type = "wireguard"
    config.killswitch_enabled = True
    return config


@pytest.fixture
def mock_state():
    """Minimal StateManager mock."""
    state = MagicMock()
    state.vpn_state = "up"
    state.vpn_type = "wireguard"
    state.killswitch_state = "enabled"
    state.setup_required = True
    state.setup_provider = None
    return state


@pytest.fixture
def app(mock_config, mock_state):
    """FastAPI test app with mocked state."""
    from api.main import app as real_app

    real_app.state.config = mock_config
    real_app.state.state = mock_state
    real_app.state.started_at = 0
    return real_app


@pytest.fixture
def client(app):
    """TestClient for the FastAPI app."""
    return TestClient(app, )
