"""Tests for control plane action functions."""

from unittest.mock import MagicMock, patch

import pytest

from api.routes.control import (
    ActionResponse,
    do_vpn_disconnect,
    do_vpn_restart,
    do_killswitch_enable,
    do_killswitch_disable,
    do_qbt_restart,
)


@pytest.fixture
def state_mgr():
    mgr = MagicMock()
    mgr.vpn_type = "wireguard"
    mgr.vpn_state = "up"
    mgr.killswitch_state = "enabled"
    return mgr


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.qbt_enabled = True
    cfg.webui_port = 8080
    return cfg


class TestVpnDisconnect:
    @patch("api.routes.control._run", return_value=(True, ""))
    @patch("api.routes.control.broadcast")
    def test_wireguard_disconnect(self, mock_broadcast, mock_run, state_mgr):
        result = do_vpn_disconnect(state_mgr)
        assert result.success is True
        assert result.action == "vpn_disconnect"
        mock_run.assert_called_once_with(["wg-quick", "down", "wg0"])
        mock_broadcast.assert_called_once()

    @patch("api.routes.control._run", return_value=(True, ""))
    @patch("api.routes.control.broadcast")
    def test_openvpn_disconnect(self, mock_broadcast, mock_run, state_mgr):
        state_mgr.vpn_type = "openvpn"
        result = do_vpn_disconnect(state_mgr)
        assert result.success is True
        mock_run.assert_called_once_with(["killall", "openvpn"])

    @patch("api.routes.control._run", return_value=(False, "not running"))
    @patch("api.routes.control.broadcast")
    def test_disconnect_failure(self, mock_broadcast, mock_run, state_mgr):
        result = do_vpn_disconnect(state_mgr)
        assert result.success is False
        assert result.error == "not running"
        mock_broadcast.assert_not_called()


class TestVpnRestart:
    @patch("api.routes.control._run")
    @patch("api.routes.control.broadcast")
    def test_wireguard_restart(self, mock_broadcast, mock_run, state_mgr):
        mock_run.side_effect = [(True, ""), (True, "")]  # down, up
        result = do_vpn_restart(state_mgr)
        assert result.success is True
        assert result.action == "vpn_restart"
        assert mock_run.call_count == 2

    @patch("api.routes.control._run")
    @patch("api.routes.control.broadcast")
    def test_restart_failure(self, mock_broadcast, mock_run, state_mgr):
        mock_run.side_effect = [(True, ""), (False, "interface not found")]
        result = do_vpn_restart(state_mgr)
        assert result.success is False
        assert "interface not found" in result.error


class TestKillswitch:
    @patch("api.routes.control._run", return_value=(True, ""))
    def test_enable(self, mock_run):
        result = do_killswitch_enable()
        assert result.success is True
        assert result.action == "killswitch_enable"

    @patch("api.routes.control._run", return_value=(True, ""))
    def test_disable(self, mock_run, state_mgr):
        result = do_killswitch_disable(state_mgr)
        assert result.success is True
        assert result.action == "killswitch_disable"

    @patch("api.routes.control._run", return_value=(False, "permission denied"))
    def test_disable_failure(self, mock_run, state_mgr):
        result = do_killswitch_disable(state_mgr)
        assert result.success is False


class TestQbtRestart:
    @patch("api.routes.control._run", return_value=(True, ""))
    def test_restart(self, mock_run, config):
        result = do_qbt_restart(config)
        assert result.success is True

    def test_restart_disabled(self, config):
        config.qbt_enabled = False
        result = do_qbt_restart(config)
        assert result.success is False
        assert "disabled" in result.error
