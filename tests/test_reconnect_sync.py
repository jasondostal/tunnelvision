"""Tests for wg0.conf sync in _reconnect_vpn.

Regression for: rotate/connect writing new config to /config/wireguard/wg0.conf
but wg-quick reading stale /etc/wireguard/wg0.conf — tunnel never switched servers.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_fake_run(call_order=None):
    def fake_run(cmd, **kwargs):
        if call_order is not None:
            if "up" in cmd:
                call_order.append("wg-quick-up")
            elif "down" in cmd:
                call_order.append("wg-quick-down")
            elif "killall" in cmd:
                call_order.append("killall-openvpn")
        r = MagicMock()
        r.returncode = 0
        r.stderr = ""
        return r
    return fake_run


@pytest.fixture()
def wg_conf(tmp_path):
    conf = tmp_path / "wg0.conf"
    conf.write_text(
        "[Interface]\nPrivateKey = test\nAddress = 10.0.0.1/32\n\n"
        "[Peer]\nPublicKey = abc\nEndpoint = 1.2.3.4:51820\nAllowedIPs = 0.0.0.0/0\n"
    )
    return conf


@pytest.fixture(autouse=True)
def _patch_history():
    """Prevent history module from touching /config."""
    with patch("api.routes.connect.log_event"):
        yield


class TestReconnectWgSync:
    @pytest.mark.asyncio
    async def test_wg_conf_synced_to_etc_wireguard(self, wg_conf):
        """_reconnect_vpn copies WG_CONF_PATH to /etc/wireguard/wg0.conf before wg-quick up."""
        synced_content = []

        with patch("api.routes.connect.WG_CONF_PATH", wg_conf), \
             patch("shutil.copy2", side_effect=lambda s, d: synced_content.append(Path(s).read_text())), \
             patch("os.chmod"), \
             patch("pathlib.Path.mkdir"), \
             patch("subprocess.run", side_effect=_make_fake_run()):
            from api.routes.connect import _reconnect_vpn
            result = await _reconnect_vpn("wireguard")

        assert result.success is True
        assert len(synced_content) == 1
        assert "1.2.3.4:51820" in synced_content[0]

    @pytest.mark.asyncio
    async def test_wg_conf_synced_before_wg_quick_up(self, wg_conf):
        """Copy must happen before wg-quick up, not after."""
        call_order = []

        with patch("api.routes.connect.WG_CONF_PATH", wg_conf), \
             patch("shutil.copy2", side_effect=lambda *a: call_order.append("copy")), \
             patch("os.chmod"), \
             patch("pathlib.Path.mkdir"), \
             patch("subprocess.run", side_effect=_make_fake_run(call_order)):
            from api.routes.connect import _reconnect_vpn
            await _reconnect_vpn("wireguard")

        assert "copy" in call_order
        assert "wg-quick-up" in call_order
        assert call_order.index("copy") < call_order.index("wg-quick-up")

    @pytest.mark.asyncio
    async def test_no_sync_if_conf_missing(self, tmp_path):
        """If WG_CONF_PATH doesn't exist, skip copy — don't crash."""
        missing = tmp_path / "nonexistent.conf"
        copy_called = []

        with patch("api.routes.connect.WG_CONF_PATH", missing), \
             patch("shutil.copy2", side_effect=lambda *a: copy_called.append(1)), \
             patch("subprocess.run", side_effect=_make_fake_run()):
            from api.routes.connect import _reconnect_vpn
            result = await _reconnect_vpn("wireguard")

        assert result.success is True
        assert len(copy_called) == 0

    @pytest.mark.asyncio
    async def test_openvpn_reconnect_no_wg_sync(self, wg_conf):
        """OpenVPN reconnect path doesn't touch /etc/wireguard/."""
        copy_called = []

        with patch("api.routes.connect.WG_CONF_PATH", wg_conf), \
             patch("shutil.copy2", side_effect=lambda *a: copy_called.append(1)), \
             patch("subprocess.run", side_effect=_make_fake_run()):
            from api.routes.connect import _reconnect_vpn
            result = await _reconnect_vpn("openvpn")

        assert len(copy_called) == 0
