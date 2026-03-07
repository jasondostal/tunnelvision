"""Tests for setup endpoint access gating — setup endpoints return 403 after setup is complete."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def setup_complete_client(app, mock_state):
    """Client where setup is already complete."""
    mock_state.setup_required = False
    app.state.state = mock_state
    return TestClient(app, )


@pytest.fixture
def setup_pending_client(app, mock_state):
    """Client where setup is still required."""
    mock_state.setup_required = True
    app.state.state = mock_state
    return TestClient(app, )


class TestSetupGate:
    """Mutating setup endpoints should be blocked after setup is complete."""

    def test_select_provider_blocked_after_setup(self, setup_complete_client):
        r = setup_complete_client.post("/api/v1/setup/provider", json={"provider": "mullvad"})
        assert r.status_code == 403
        assert "already complete" in r.json()["detail"].lower()

    def test_wireguard_upload_blocked_after_setup(self, setup_complete_client):
        r = setup_complete_client.post("/api/v1/setup/wireguard", json={"config": "[Interface]\nPrivateKey=abc\n[Peer]"})
        assert r.status_code == 403

    def test_openvpn_upload_blocked_after_setup(self, setup_complete_client):
        r = setup_complete_client.post("/api/v1/setup/openvpn", json={"config": "client\nremote vpn.example.com 1194"})
        assert r.status_code == 403

    def test_credentials_blocked_after_setup(self, setup_complete_client):
        r = setup_complete_client.post("/api/v1/setup/credentials", json={"provider": "mullvad"})
        assert r.status_code == 403

    def test_status_always_accessible(self, setup_complete_client):
        """GET /setup/status should work regardless of setup state."""
        r = setup_complete_client.get("/api/v1/setup/status")
        assert r.status_code == 200

    def test_providers_always_accessible(self, setup_complete_client):
        """GET /setup/providers should work regardless of setup state."""
        r = setup_complete_client.get("/api/v1/setup/providers")
        assert r.status_code == 200

    def test_select_provider_allowed_during_setup(self, setup_pending_client):
        """Provider selection works when setup is pending."""
        r = setup_pending_client.post("/api/v1/setup/provider", json={"provider": "custom"})
        assert r.status_code == 200


class TestOvpnDirectiveStripping:
    """OpenVPN config sanitization — unit test on the stripping function."""

    def test_dangerous_directives_stripped(self):
        """Dangerous directives are removed from OpenVPN configs."""
        from api.routes.setup import _strip_dangerous_ovpn_directives

        config = """client
remote vpn.example.com 1194
dev tun
script-security 2
up /tmp/evil.sh
down /tmp/evil2.sh
route-up /tmp/evil3.sh
auth-user-pass-verify /tmp/check.sh
tls-verify /tmp/verify.sh
"""
        result = _strip_dangerous_ovpn_directives(config)
        assert "script-security" not in result
        assert "up /tmp/evil.sh" not in result
        assert "down /tmp/evil2.sh" not in result
        assert "route-up" not in result
        assert "auth-user-pass-verify" not in result
        assert "tls-verify" not in result
        # Safe directives remain
        assert "client" in result
        assert "remote vpn.example.com 1194" in result
        assert "dev tun" in result

    def test_comments_preserved(self):
        """Comments are not stripped."""
        from api.routes.setup import _strip_dangerous_ovpn_directives

        config = "# This is a comment\nclient\nremote vpn.example.com 1194"
        result = _strip_dangerous_ovpn_directives(config)
        assert "# This is a comment" in result
