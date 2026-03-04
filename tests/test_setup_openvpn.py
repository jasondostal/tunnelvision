"""Tests for OpenVPN setup wizard endpoints."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.constants import OPENVPN_CONF_PATH, OPENVPN_CREDS_PATH, WG_CONF_PATH
from api.services.state import StateManager

VALID_OVPN = """\
client
dev tun
proto udp
remote vpn.example.com 1194
resolv-retry infinite
nobind
persist-key
persist-tun
<ca>
-----BEGIN CERTIFICATE-----
FAKE
-----END CERTIFICATE-----
</ca>
"""

client = TestClient(app)


@pytest.fixture(autouse=True)
def _init_app_state(tmp_path):
    """Ensure app.state.state is populated for endpoints that need it."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    app.state.state = StateManager(state_dir=state_dir)


class TestUploadOpenVPNConfig:
    def test_valid_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("api.routes.setup.OPENVPN_DIR", tmp_path)
        monkeypatch.setattr("api.routes.setup.OPENVPN_CONF_PATH", tmp_path / "provider.ovpn")
        monkeypatch.setattr("api.routes.setup.OPENVPN_CREDS_PATH", tmp_path / "credentials.txt")

        resp = client.post("/api/v1/setup/openvpn", json={"config": VALID_OVPN})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["next"] == "needs_verify"
        assert (tmp_path / "provider.ovpn").exists()

    def test_rejects_wireguard_config(self):
        wg_config = "[Interface]\nPrivateKey = abc\nAddress = 10.0.0.1/32\n\n[Peer]\nPublicKey = xyz\n"
        resp = client.post("/api/v1/setup/openvpn", json={"config": wg_config})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "WireGuard" in data["error"]

    def test_rejects_missing_directives(self):
        resp = client.post("/api/v1/setup/openvpn", json={"config": "dev tun\nproto udp\n"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "remote" in data["error"] or "client" in data["error"]

    def test_with_credentials(self, tmp_path, monkeypatch):
        monkeypatch.setattr("api.routes.setup.OPENVPN_DIR", tmp_path)
        monkeypatch.setattr("api.routes.setup.OPENVPN_CONF_PATH", tmp_path / "provider.ovpn")
        creds_path = tmp_path / "credentials.txt"
        monkeypatch.setattr("api.routes.setup.OPENVPN_CREDS_PATH", creds_path)

        resp = client.post("/api/v1/setup/openvpn", json={
            "config": VALID_OVPN,
            "username": "myuser",
            "password": "mypass",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert creds_path.exists()
        lines = creds_path.read_text().splitlines()
        assert lines[0] == "myuser"
        assert lines[1] == "mypass"

    def test_without_credentials_no_creds_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("api.routes.setup.OPENVPN_DIR", tmp_path)
        monkeypatch.setattr("api.routes.setup.OPENVPN_CONF_PATH", tmp_path / "provider.ovpn")
        creds_path = tmp_path / "credentials.txt"
        monkeypatch.setattr("api.routes.setup.OPENVPN_CREDS_PATH", creds_path)

        resp = client.post("/api/v1/setup/openvpn", json={"config": VALID_OVPN})
        assert resp.json()["success"] is True
        assert not creds_path.exists()


class TestSetupComplete:
    def test_accepts_openvpn_config(self, tmp_path, monkeypatch):
        ovpn_conf = tmp_path / "provider.ovpn"
        ovpn_conf.write_text(VALID_OVPN)
        monkeypatch.setattr("api.routes.setup.OPENVPN_CONF_PATH", ovpn_conf)
        monkeypatch.setattr("api.routes.setup.WG_CONF_PATH", tmp_path / "wg0.conf")  # doesn't exist

        mock_save = MagicMock()
        mock_subprocess = MagicMock()
        mock_subprocess.return_value = MagicMock(returncode=0)

        with patch("api.routes.setup.save_settings", mock_save), \
             patch("api.routes.setup.subprocess.run", mock_subprocess):
            resp = client.post("/api/v1/setup/complete")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # Should have saved vpn_type=openvpn
        saved = mock_save.call_args[0][0]
        assert saved.get("vpn_type") == "openvpn"

    def test_rejects_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("api.routes.setup.OPENVPN_CONF_PATH", tmp_path / "provider.ovpn")
        monkeypatch.setattr("api.routes.setup.WG_CONF_PATH", tmp_path / "wg0.conf")

        resp = client.post("/api/v1/setup/complete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "openvpn" in data["error"].lower() or "wireguard" in data["error"].lower()


class TestSetupStatus:
    def test_has_config_with_openvpn(self, tmp_path, monkeypatch):
        ovpn_conf = tmp_path / "provider.ovpn"
        ovpn_conf.write_text(VALID_OVPN)
        monkeypatch.setattr("api.routes.setup.OPENVPN_CONF_PATH", ovpn_conf)
        monkeypatch.setattr("api.routes.setup.WG_CONF_PATH", tmp_path / "wg0.conf")

        resp = client.get("/api/v1/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_config"] is True
