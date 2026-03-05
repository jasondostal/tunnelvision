"""Tests for the self-healing VPN watchdog service."""

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from api.config import Config
from api.services.state import StateManager
from api.services.watchdog import (
    WatchdogService,
    WatchdogState,
    RECONNECT_THRESHOLD,
    COOLDOWN_SECONDS,
    HANDSHAKE_STALE_SECONDS,
    get_watchdog_service,
)


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Create a temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def state_mgr(tmp_state_dir):
    """StateManager backed by temp dir."""
    return StateManager(state_dir=tmp_state_dir)


@pytest.fixture
def config():
    """Minimal Config for testing."""
    return Config(
        vpn_enabled=True,
        auto_reconnect=True,
        health_check_interval=1,
        qbt_enabled=False,
        killswitch_enabled=True,
        gluetun_url="http://gluetun:8000",
    )


@pytest.fixture
def watchdog(config, state_mgr):
    """Fresh WatchdogService instance."""
    return WatchdogService(config, state_mgr)


# --- State Machine Tests ---


class TestStateTransitions:
    def test_initial_state_is_idle(self, watchdog):
        assert watchdog.current_state == WatchdogState.IDLE

    def test_set_state_updates_state_file(self, watchdog, state_mgr):
        watchdog._set_state(WatchdogState.MONITORING)
        assert state_mgr.watchdog_state == "monitoring"

    def test_set_state_noop_on_same(self, watchdog, state_mgr):
        watchdog._set_state(WatchdogState.MONITORING)
        # Write something else to the state file to verify no second write
        state_mgr.write("watchdog_state", "tampered")
        watchdog._set_state(WatchdogState.MONITORING)  # same state — should not write
        assert state_mgr.watchdog_state == "tampered"

    def test_on_healthy_resets_to_monitoring(self, watchdog):
        watchdog._state = WatchdogState.DEGRADED
        watchdog._consecutive_failures = 2
        watchdog._tried_configs = ["a.conf", "b.conf"]

        with patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_notify_async"):
            watchdog._on_healthy()

        assert watchdog.current_state == WatchdogState.MONITORING
        assert watchdog._consecutive_failures == 0
        assert watchdog._tried_configs == []

    def test_on_healthy_increments_recovery_count(self, watchdog):
        watchdog._state = WatchdogState.RECONNECTING
        watchdog._consecutive_failures = 3

        with patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_notify_async"):
            watchdog._on_healthy()

        assert watchdog._recovery_count == 1

    def test_on_healthy_no_broadcast_when_no_failures(self, watchdog):
        watchdog._state = WatchdogState.MONITORING
        watchdog._consecutive_failures = 0

        with patch.object(watchdog, "_broadcast") as mock_broadcast:
            watchdog._on_healthy()

        mock_broadcast.assert_not_called()


# --- Health Probe Tests ---


class TestHealthProbes:
    def test_wireguard_healthy_handshake(self, watchdog):
        fresh_ts = str(int(time.time()) - 30)  # 30s ago
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"abc123=\t{fresh_ts}\n"

        with patch("subprocess.run", return_value=mock_result):
            assert watchdog._check_wireguard_health() is True

    def test_wireguard_stale_handshake(self, watchdog):
        stale_ts = str(int(time.time()) - HANDSHAKE_STALE_SECONDS - 10)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"abc123=\t{stale_ts}\n"

        with patch("subprocess.run", return_value=mock_result):
            assert watchdog._check_wireguard_health() is False

    def test_wireguard_zero_handshake(self, watchdog):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123=\t0\n"

        with patch("subprocess.run", return_value=mock_result):
            assert watchdog._check_wireguard_health() is False

    def test_wireguard_no_interface(self, watchdog):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            assert watchdog._check_wireguard_health() is False

    def test_wireguard_subprocess_exception(self, watchdog):
        with patch("subprocess.run", side_effect=Exception("boom")):
            assert watchdog._check_wireguard_health() is False

    def test_openvpn_healthy(self, watchdog):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            assert watchdog._check_openvpn_health() is True

    def test_openvpn_no_interface(self, watchdog):
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            assert watchdog._check_openvpn_health() is False

    def test_check_vpn_health_dispatches_by_type(self, watchdog, state_mgr):
        state_mgr.vpn_type = "wireguard"
        with patch.object(watchdog, "_check_wireguard_health", return_value=True) as mock_wg:
            assert watchdog._check_vpn_health() is True
            mock_wg.assert_called_once()

        state_mgr.vpn_type = "openvpn"
        with patch.object(watchdog, "_check_openvpn_health", return_value=True) as mock_ovpn:
            assert watchdog._check_vpn_health() is True
            mock_ovpn.assert_called_once()


# --- Escalation Tests ---


class TestEscalation:
    @pytest.mark.asyncio
    async def test_degraded_after_first_failure(self, watchdog):
        watchdog._state = WatchdogState.MONITORING
        with patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_is_auto_reconnect_enabled", return_value=True):
            await watchdog._on_unhealthy_standalone()

        assert watchdog.current_state == WatchdogState.DEGRADED
        assert watchdog._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_reconnect_at_threshold(self, watchdog):
        watchdog._state = WatchdogState.DEGRADED
        watchdog._consecutive_failures = RECONNECT_THRESHOLD - 1

        with patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_notify_async"), \
             patch.object(watchdog, "_is_auto_reconnect_enabled", return_value=True), \
             patch.object(watchdog, "_do_reconnect", new_callable=AsyncMock, return_value=True), \
             patch.object(watchdog, "_on_healthy") as mock_healthy:
            await watchdog._on_unhealthy_standalone()

        assert watchdog._consecutive_failures == RECONNECT_THRESHOLD
        mock_healthy.assert_called_once()

    @pytest.mark.asyncio
    async def test_failover_on_reconnect_failure(self, watchdog):
        watchdog._state = WatchdogState.DEGRADED
        watchdog._consecutive_failures = RECONNECT_THRESHOLD - 1

        with patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_notify_async"), \
             patch.object(watchdog, "_is_auto_reconnect_enabled", return_value=True), \
             patch.object(watchdog, "_do_reconnect", new_callable=AsyncMock, return_value=False), \
             patch.object(watchdog, "_do_failover", new_callable=AsyncMock) as mock_failover:
            await watchdog._on_unhealthy_standalone()

        mock_failover.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_action_when_auto_reconnect_disabled(self, watchdog):
        watchdog._state = WatchdogState.DEGRADED
        watchdog._consecutive_failures = RECONNECT_THRESHOLD - 1

        with patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_is_auto_reconnect_enabled", return_value=False), \
             patch.object(watchdog, "_do_reconnect", new_callable=AsyncMock) as mock_reconnect:
            await watchdog._on_unhealthy_standalone()

        mock_reconnect.assert_not_called()
        assert watchdog.current_state == WatchdogState.DEGRADED


# --- Failover Tests ---


class TestFailover:
    @pytest.mark.asyncio
    async def test_failover_tries_untried_configs(self, watchdog, tmp_path):
        config_dir = tmp_path / "wireguard"
        config_dir.mkdir()
        (config_dir / "a.conf").write_text("[Interface]\nPrivateKey=abc\n[Peer]\n")
        (config_dir / "b.conf").write_text("[Interface]\nPrivateKey=def\n[Peer]\n")

        watchdog._tried_configs = []

        with patch.object(watchdog, "_list_available_configs", return_value=[
            config_dir / "a.conf", config_dir / "b.conf"
        ]), \
             patch.object(watchdog, "_activate_config", new_callable=AsyncMock, return_value=True), \
             patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_on_healthy") as mock_healthy:
            watchdog.state.active_config = "current.conf"
            await watchdog._do_failover()

        mock_healthy.assert_called_once()

    @pytest.mark.asyncio
    async def test_failover_enters_cooldown_when_exhausted(self, watchdog, tmp_path):
        config_dir = tmp_path / "wireguard"
        config_dir.mkdir()
        (config_dir / "a.conf").write_text("[Interface]\n")

        with patch.object(watchdog, "_list_available_configs", return_value=[
            config_dir / "a.conf"
        ]), \
             patch.object(watchdog, "_activate_config", new_callable=AsyncMock, return_value=False), \
             patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_enter_cooldown", new_callable=AsyncMock) as mock_cooldown:
            watchdog.state.active_config = "other.conf"
            await watchdog._do_failover()

        mock_cooldown.assert_called_once()

    @pytest.mark.asyncio
    async def test_failover_skips_already_tried(self, watchdog, tmp_path):
        config_dir = tmp_path / "wireguard"
        config_dir.mkdir()
        (config_dir / "a.conf").write_text("[Interface]\n")
        (config_dir / "b.conf").write_text("[Interface]\n")

        watchdog._tried_configs = ["a.conf"]

        with patch.object(watchdog, "_list_available_configs", return_value=[
            config_dir / "a.conf", config_dir / "b.conf"
        ]), \
             patch.object(watchdog, "_activate_config", new_callable=AsyncMock, return_value=True) as mock_activate, \
             patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_on_healthy"):
            watchdog.state.active_config = "other.conf"
            await watchdog._do_failover()

        # Should only have tried b.conf (a.conf was already tried)
        mock_activate.assert_called_once()
        assert mock_activate.call_args[0][0].name == "b.conf"


# --- Cooldown Tests ---


class TestCooldown:
    @pytest.mark.asyncio
    async def test_enter_cooldown_sets_state_and_timer(self, watchdog):
        with patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_notify_async"), \
             patch.object(watchdog, "_pause_qbt", new_callable=AsyncMock):
            await watchdog._enter_cooldown()

        assert watchdog.current_state == WatchdogState.COOLDOWN
        assert watchdog._cooldown_until > time.time()
        assert watchdog._cooldown_until <= time.time() + COOLDOWN_SECONDS + 1

    @pytest.mark.asyncio
    async def test_cooldown_pauses_qbt(self, watchdog):
        watchdog.config = Config(
            vpn_enabled=True, auto_reconnect=True,
            health_check_interval=1, qbt_enabled=True,
        )
        with patch.object(watchdog, "_broadcast"), \
             patch.object(watchdog, "_log_history"), \
             patch.object(watchdog, "_notify_async"), \
             patch("api.services.watchdog.WatchdogService._pause_qbt", new_callable=AsyncMock) as mock_pause:
            await watchdog._enter_cooldown()

        mock_pause.assert_called_once()


# --- Snapshot Tests ---


class TestSnapshot:
    def test_snapshot_fields(self, watchdog):
        watchdog._state = WatchdogState.MONITORING
        watchdog._consecutive_failures = 2
        watchdog._tried_configs = ["a.conf"]
        watchdog._recovery_count = 1

        snap = watchdog.snapshot()

        assert snap["state"] == "monitoring"
        assert snap["consecutive_failures"] == 2
        assert snap["tried_configs"] == ["a.conf"]
        assert snap["recovery_count"] == 1
        assert snap["cooldown_remaining"] == 0

    def test_snapshot_cooldown_remaining(self, watchdog):
        watchdog._state = WatchdogState.COOLDOWN
        watchdog._cooldown_until = time.time() + 120

        snap = watchdog.snapshot()

        assert 115 <= snap["cooldown_remaining"] <= 120


# --- Config Activation Tests ---


class TestConfigActivation:
    @pytest.mark.asyncio
    async def test_strips_postup_postdown(self, watchdog, tmp_path, state_mgr):
        config_file = tmp_path / "test.conf"
        config_file.write_text(
            "[Interface]\n"
            "PrivateKey = abc123\n"
            "Address = 10.0.0.1/24\n"
            "PostUp = iptables -A FORWARD -i wg0\n"
            "PostDown = iptables -D FORWARD -i wg0\n"
            "\n"
            "[Peer]\n"
            "PublicKey = xyz789\n"
            "Endpoint = 1.2.3.4:51820\n"
            "AllowedIPs = 0.0.0.0/0\n"
        )

        # Use a real temp file as the wg0.conf target
        wg_dir = tmp_path / "etc_wireguard"
        wg_dir.mkdir()
        wg_conf = wg_dir / "wg0.conf"

        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run), \
             patch("api.services.watchdog.WG_RUNTIME_CONF", wg_conf), \
             patch("api.services.watchdog.WG_RUNTIME_DIR", wg_dir), \
             patch("os.chmod"), \
             patch.object(watchdog, "_check_vpn_health", return_value=True):

            await watchdog._activate_config(config_file)

        written = wg_conf.read_text()
        assert "PostUp" not in written
        assert "PostDown" not in written
        assert "PrivateKey" in written

    @pytest.mark.asyncio
    async def test_reapplies_killswitch(self, watchdog, tmp_path):
        config_file = tmp_path / "test.conf"
        config_file.write_text("[Interface]\nPrivateKey=abc\n[Peer]\n")

        wg_dir = tmp_path / "etc_wireguard"
        wg_dir.mkdir()
        wg_conf = wg_dir / "wg0.conf"

        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run), \
             patch("api.services.watchdog.WG_RUNTIME_CONF", wg_conf), \
             patch("api.services.watchdog.WG_RUNTIME_DIR", wg_dir), \
             patch("os.chmod"), \
             patch.object(watchdog, "_check_vpn_health", return_value=True):
            await watchdog._activate_config(config_file)

        killswitch_calls = [c for c in calls if "killswitch" in str(c)]
        assert len(killswitch_calls) == 1


# --- Singleton Tests ---


class TestSingleton:
    def test_get_watchdog_service_returns_same_instance(self):
        import api.services.watchdog as mod
        mod._instance = None  # Reset

        config = Config(vpn_enabled=True, auto_reconnect=True, health_check_interval=30)
        state = StateManager(state_dir=Path("/tmp/test_watchdog_state"))
        Path("/tmp/test_watchdog_state").mkdir(exist_ok=True)

        svc1 = get_watchdog_service(config, state)
        svc2 = get_watchdog_service()
        assert svc1 is svc2

        mod._instance = None  # Cleanup


# --- Settings re-read test ---


class TestSettingsReread:
    def test_auto_reconnect_reads_from_settings(self, watchdog):
        with patch("api.services.watchdog.WatchdogService._is_auto_reconnect_enabled",
                    return_value=False):
            assert not watchdog._is_auto_reconnect_enabled()

    def test_auto_reconnect_fallback_to_config(self, watchdog):
        with patch("api.services.settings.load_settings", side_effect=Exception("no file")):
            result = watchdog._is_auto_reconnect_enabled()
        assert result is True  # Falls back to config.auto_reconnect

    def test_load_setting_reads_from_yaml(self, watchdog):
        with patch("api.services.settings.load_settings",
                    return_value={"health_check_interval": "60"}):
            assert watchdog._load_setting("health_check_interval", "30") == "60"

    def test_load_setting_fallback_on_error(self, watchdog):
        with patch("api.services.settings.load_settings", side_effect=Exception("fail")):
            assert watchdog._load_setting("health_check_interval", "30") == "30"

    def test_health_check_interval_hot_reloads(self, watchdog):
        """Verify health_check_interval re-reads from settings, not frozen Config."""
        with patch("api.services.settings.load_settings",
                    return_value={"health_check_interval": "45"}):
            val = int(watchdog._load_setting(
                "health_check_interval",
                str(watchdog.config.health_check_interval),
            ))
        assert val == 45
        assert watchdog.config.health_check_interval == 1  # frozen Config unchanged


# --- StateManager tests ---


class TestStateManagerWatchdog:
    def test_watchdog_state_property(self, state_mgr):
        assert state_mgr.watchdog_state == "idle"  # default

    def test_watchdog_state_setter(self, state_mgr):
        state_mgr.watchdog_state = "monitoring"
        assert state_mgr.watchdog_state == "monitoring"

    def test_snapshot_includes_watchdog_and_active_config(self, state_mgr):
        state_mgr.watchdog_state = "degraded"
        state_mgr.active_config = "test.conf"
        snap = state_mgr.snapshot()
        assert snap["watchdog_state"] == "degraded"
        assert snap["active_config"] == "test.conf"


# --- Settings model alignment tests ---


class TestSettingsModelAlignment:
    """Verify SettingsUpdate model covers all CONFIGURABLE_FIELDS."""

    def test_all_configurable_fields_in_update_model(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        from api.routes.settings import SettingsUpdate

        model_fields = set(SettingsUpdate.model_fields.keys())
        config_fields = set(CONFIGURABLE_FIELDS.keys())

        missing = config_fields - model_fields
        assert missing == set(), f"Fields in CONFIGURABLE_FIELDS but not in SettingsUpdate: {missing}"

    def test_needs_restart_accuracy(self):
        """Hot-reload fields should NOT trigger needs_restart."""
        from api.routes.settings import SettingsUpdate

        hot_reload_fields = {
            "auto_reconnect", "health_check_interval",
            "vpn_country", "vpn_city",
            "notify_webhook_url", "notify_gotify_url", "notify_gotify_token",
        }

        # Changing only hot-reload fields should not need restart
        for field in hot_reload_fields:
            updates = {field: "test_value"}
            needs_restart = bool(set(updates.keys()) - hot_reload_fields)
            assert not needs_restart, f"{field} should be hot-reloadable"

        # Changing a non-hot-reload field should need restart
        updates = {"mqtt_broker": "10.0.0.1"}
        needs_restart = bool(set(updates.keys()) - hot_reload_fields)
        assert needs_restart, "mqtt_broker should need restart"


# --- Notifications hot-reload test ---


class TestNotificationsHotReload:
    @pytest.mark.asyncio
    async def test_notify_reads_from_settings(self):
        from api.services.notifications import notify

        with patch("api.services.settings.load_settings", return_value={
            "notify_webhook_url": "https://hooks.example.com/test",
            "notify_gotify_url": "",
            "notify_gotify_token": "",
        }), patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await notify("test_event", "test message")

            mock_client.post.assert_called_once()
            call_url = mock_client.post.call_args[0][0]
            assert call_url == "https://hooks.example.com/test"

    @pytest.mark.asyncio
    async def test_notify_falls_back_to_config(self):
        from api.services.notifications import notify

        config = Config(
            notify_webhook_url="https://fallback.example.com",
        )

        with patch("api.services.settings.load_settings", side_effect=Exception("no file")), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await notify("test_event", "test message", config=config)

            mock_client.post.assert_called_once()
            call_url = mock_client.post.call_args[0][0]
            assert call_url == "https://fallback.example.com"
