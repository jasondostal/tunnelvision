"""Self-healing VPN watchdog — auto-reconnect with multi-config failover.

State machine:
  IDLE → MONITORING → DEGRADED (1-2 failures) → RECONNECTING (3rd failure)
    → FAILING_OVER (reconnect failed, try next config) → COOLDOWN (all exhausted)
    → back to MONITORING

Integrates with: SSE (broadcast), MQTT (state publish), history (log_event),
notifications (notify), and the control plane (do_vpn_restart, do_qbt_pause/resume).
"""

import asyncio
import logging
import subprocess
import time
from pathlib import Path

from api.config import Config
from api.constants import (
    SCRIPT_INIT_VPN,
    SUBPROCESS_TIMEOUT_DEFAULT,
    SUBPROCESS_TIMEOUT_LONG,
    SUBPROCESS_TIMEOUT_QUICK,
    SUBPROCESS_TIMEOUT_VPN,
    TIMEOUT_QUICK,
    WatchdogState,
    bring_up_wireguard_file,
    http_client,
    list_config_files,
)
from api.services.state import StateManager

log = logging.getLogger("tunnelvision.watchdog")


class WatchdogService:
    """Background watchdog that monitors VPN health and auto-reconnects."""

    def __init__(self, config: Config, state_mgr: StateManager):
        self.config = config
        self.state = state_mgr
        self._state = WatchdogState.IDLE
        self._task: asyncio.Task | None = None
        self._consecutive_failures = 0
        self._tried_configs: list[str] = []
        self._cooldown_until = 0.0
        self._last_check = 0.0
        self._recovery_count = 0

    @property
    def current_state(self) -> WatchdogState:
        return self._state

    def _set_state(self, new_state: WatchdogState) -> None:
        if new_state == self._state:
            return
        old = self._state
        self._state = new_state
        self.state.watchdog_state = new_state.value
        log.info(f"Watchdog: {old.value} → {new_state.value}")

    def snapshot(self) -> dict:
        """Current watchdog state for API responses."""
        return {
            "state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "tried_configs": list(self._tried_configs),
            "recovery_count": self._recovery_count,
            "auto_reconnect": self._is_auto_reconnect_enabled(),
            "cooldown_remaining": max(0, int(self._cooldown_until - time.time()))
                if self._state == WatchdogState.COOLDOWN else 0,
        }

    def start(self) -> None:
        """Start the watchdog background loop."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="watchdog")
        log.info("Watchdog started")

    def stop(self) -> None:
        """Stop the watchdog."""
        if self._task:
            self._task.cancel()
            self._task = None
        self._set_state(WatchdogState.IDLE)
        log.info("Watchdog stopped")

    def _load_setting(self, key: str, default: str = "") -> str:
        """Re-read a single setting from YAML — hot-reloadable without restart."""
        try:
            from api.services.settings import load_settings
            return str(load_settings().get(key, default))
        except Exception:
            return default

    def _is_auto_reconnect_enabled(self) -> bool:
        """Re-read auto_reconnect from settings each call — togglable without restart."""
        return self._load_setting("auto_reconnect", "true").lower() == "true"

    def _is_sidecar_mode(self) -> bool:
        """Check if we're running in sidecar mode (gluetun manages VPN)."""
        return self.config.vpn_provider == "gluetun"

    async def _run(self) -> None:
        """Main watchdog loop."""
        # Wait for initial VPN setup to complete
        await asyncio.sleep(10)

        if not self.config.vpn_enabled:
            self._set_state(WatchdogState.IDLE)
            log.info("VPN disabled — watchdog idle")
            return

        self._set_state(WatchdogState.MONITORING)

        while True:
            try:
                try:
                    interval = int(self._load_setting(
                        "health_check_interval",
                        str(self.config.health_check_interval),
                    ))
                except (ValueError, TypeError):
                    interval = self.config.health_check_interval
                await asyncio.sleep(interval)
                self._last_check = time.time()

                # Handle cooldown
                if self._state == WatchdogState.COOLDOWN:
                    if time.time() >= self._cooldown_until:
                        log.info("Cooldown expired — resetting and retrying")
                        self._tried_configs.clear()
                        self._consecutive_failures = 0
                        self._set_state(WatchdogState.MONITORING)
                        # Resume qBit if it was paused
                        await self._resume_qbt()
                    continue

                # Sidecar mode: read-only monitoring (can't reconnect gluetun)
                if self._is_sidecar_mode():
                    healthy = await self._check_sidecar_health()
                    if healthy:
                        self._on_healthy()
                    else:
                        self._on_unhealthy()
                    continue

                # Standalone mode: full health check + reconnect
                healthy = self._check_vpn_health()
                if healthy:
                    self._on_healthy()
                else:
                    await self._on_unhealthy_standalone()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Watchdog tick error: {e}")
                await asyncio.sleep(5)

    def _check_vpn_health(self) -> bool:
        """Check VPN tunnel health. Returns True if healthy."""
        vpn_type = self.state.vpn_type

        if vpn_type == "wireguard":
            return self._check_wireguard_health()
        elif vpn_type == "openvpn":
            return self._check_openvpn_health()
        return False

    def _check_wireguard_health(self) -> bool:
        """WireGuard: check interface exists and handshake is fresh."""
        try:
            result = subprocess.run(
                ["wg", "show", "wg0", "latest-handshakes"],
                capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_QUICK,
            )
            if result.returncode != 0:
                return False

            # Parse handshake timestamp
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        handshake_ts = int(parts[1])
                    except ValueError:
                        return False
                    if handshake_ts == 0:
                        return False
                    age = int(time.time()) - handshake_ts
                    stale = int(self._load_setting("handshake_stale_seconds", str(self.config.handshake_stale_seconds)))
                    return age < stale
            return False
        except Exception:
            return False

    def _check_openvpn_health(self) -> bool:
        """OpenVPN: check tun0 interface exists."""
        try:
            result = subprocess.run(
                ["ip", "link", "show", "tun0"],
                capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK,
            )
            return result.returncode == 0
        except Exception:
            return False

    async def _check_sidecar_health(self) -> bool:
        """Sidecar: check gluetun API (read-only, can't reconnect)."""
        try:
            async with http_client(timeout=TIMEOUT_QUICK) as client:
                headers = {}
                if self.config.gluetun_api_key:
                    headers["X-API-Key"] = self.config.gluetun_api_key
                resp = await client.get(
                    f"{self.config.gluetun_url}/v1/openvpn/status",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("status") == "running"
        except Exception:
            pass
        return False

    def _on_healthy(self) -> None:
        """VPN is healthy — reset failure counters."""
        if self._consecutive_failures > 0:
            log.info(f"VPN recovered after {self._consecutive_failures} failures")
            self._recovery_count += 1
            self._broadcast("watchdog_recovered", {
                "failures_before_recovery": self._consecutive_failures,
                "recovery_count": self._recovery_count,
            })
            self._log_history("watchdog_recovered", {
                "failures": self._consecutive_failures,
            })
            self._notify_async(
                "vpn_recovered",
                f"VPN recovered after {self._consecutive_failures} failed checks",
            )
        self._consecutive_failures = 0
        self._tried_configs.clear()
        if self._state != WatchdogState.MONITORING:
            self._set_state(WatchdogState.MONITORING)

    def _on_unhealthy(self) -> None:
        """VPN unhealthy in sidecar mode — can only observe."""
        self._consecutive_failures += 1
        threshold = int(self._load_setting("reconnect_threshold", str(self.config.reconnect_threshold)))
        if self._consecutive_failures >= threshold:
            self._set_state(WatchdogState.DEGRADED)
            self._broadcast("watchdog_degraded", {
                "consecutive_failures": self._consecutive_failures,
                "mode": "sidecar",
                "message": "VPN appears down — gluetun manages reconnection",
            })
        elif self._consecutive_failures > 0:
            self._set_state(WatchdogState.DEGRADED)

    async def _on_unhealthy_standalone(self) -> None:
        """VPN unhealthy in standalone mode — escalate through state machine."""
        self._consecutive_failures += 1
        threshold = int(self._load_setting("reconnect_threshold", str(self.config.reconnect_threshold)))
        log.warning(f"VPN health check failed ({self._consecutive_failures}/{threshold})")

        if self._consecutive_failures < threshold:
            self._set_state(WatchdogState.DEGRADED)
            self._broadcast("watchdog_degraded", {
                "consecutive_failures": self._consecutive_failures,
                "threshold": threshold,
            })
            return

        # Check if auto-reconnect is enabled (re-read each time)
        if not self._is_auto_reconnect_enabled():
            log.info("Auto-reconnect disabled — not acting")
            self._broadcast("watchdog_degraded", {
                "consecutive_failures": self._consecutive_failures,
                "auto_reconnect": False,
                "message": "Auto-reconnect disabled",
            })
            return

        # Threshold reached — try reconnect
        self._set_state(WatchdogState.RECONNECTING)
        self._broadcast("watchdog_reconnecting", {
            "consecutive_failures": self._consecutive_failures,
        })
        self._log_history("watchdog_reconnect_attempt", {
            "failures": self._consecutive_failures,
        })
        self._notify_async(
            "vpn_reconnecting",
            f"VPN down for {self._consecutive_failures} checks — attempting reconnect",
        )

        success = await self._do_reconnect()
        if success:
            log.info("Reconnect succeeded")
            self._on_healthy()
            return

        # Reconnect failed — try failover to next config
        log.warning("Reconnect failed — attempting failover")
        await self._do_failover()

    async def _do_reconnect(self) -> bool:
        """Attempt to restart VPN using current config."""
        try:
            from api.routes.control import do_vpn_restart
            result = do_vpn_restart(self.state)
            if result.success:
                # Give the tunnel a moment to establish
                await asyncio.sleep(5)
                return self._check_vpn_health()
            return False
        except Exception as e:
            log.error(f"Reconnect error: {e}")
            return False

    async def _do_failover(self) -> None:
        """Cycle through available configs until one works or all exhausted."""
        self._set_state(WatchdogState.FAILING_OVER)

        configs = self._list_available_configs()
        active = self.state.active_config

        # Filter out already-tried configs
        untried = [c for c in configs if c.name not in self._tried_configs and c.name != active]

        if not untried:
            log.warning("All configs exhausted — entering cooldown")
            await self._enter_cooldown()
            return

        for config_file in untried:
            self._tried_configs.append(config_file.name)
            log.info(f"Failover: trying {config_file.name}")
            self._broadcast("watchdog_failover", {
                "config": config_file.name,
                "tried": list(self._tried_configs),
                "remaining": len(untried) - len(self._tried_configs),
            })
            self._log_history("watchdog_failover", {
                "config": config_file.name,
            })

            success = await self._activate_config(config_file)
            if success:
                log.info(f"Failover to {config_file.name} succeeded")
                self._on_healthy()
                return

        # All configs failed
        log.warning("All failover configs failed — entering cooldown")
        await self._enter_cooldown()

    async def _activate_config(self, config_file: Path) -> bool:
        """Switch to a different VPN config file and connect."""
        vpn_type = "openvpn" if config_file.suffix == ".ovpn" else "wireguard"

        try:
            if vpn_type == "wireguard":
                ok, err = bring_up_wireguard_file(config_file, killswitch_enabled=self.config.killswitch_enabled)
                if not ok:
                    log.error(f"wg-quick up failed: {err}")
                    return False
            elif vpn_type == "openvpn":
                subprocess.run(["killall", "openvpn"], capture_output=True, timeout=SUBPROCESS_TIMEOUT_QUICK)
                await asyncio.sleep(2)
                result = subprocess.run(
                    [str(SCRIPT_INIT_VPN)],
                    capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_VPN,
                )
                if result.returncode != 0:
                    return False

            # Update state
            self.state.vpn_type = vpn_type
            self.state.active_config = config_file.name

            # Verify the tunnel is actually working
            await asyncio.sleep(5)
            return self._check_vpn_health()

        except Exception as e:
            log.error(f"Config activation failed for {config_file.name}: {e}")
            return False

    async def _enter_cooldown(self) -> None:
        """All configs exhausted — pause qBit, notify, wait."""
        self._set_state(WatchdogState.COOLDOWN)
        cooldown = int(self._load_setting("cooldown_seconds", str(self.config.cooldown_seconds)))
        self._cooldown_until = time.time() + cooldown

        self._broadcast("watchdog_cooldown", {
            "duration_seconds": cooldown,
            "tried_configs": list(self._tried_configs),
        })
        self._log_history("watchdog_cooldown", {
            "duration": cooldown,
            "tried": list(self._tried_configs),
        })
        self._notify_async(
            "vpn_cooldown",
            f"All VPN configs failed — pausing torrents, retrying in {cooldown // 60}min",
        )

        # Pause qBittorrent to prevent leaks
        await self._pause_qbt()

    async def _pause_qbt(self) -> None:
        """Pause qBittorrent torrents."""
        if not self.config.qbt_enabled:
            return
        try:
            from api.routes.control import do_qbt_pause
            await do_qbt_pause(self.config)
        except Exception as e:
            log.error(f"Failed to pause qBittorrent: {e}")

    async def _resume_qbt(self) -> None:
        """Resume qBittorrent torrents."""
        if not self.config.qbt_enabled:
            return
        try:
            from api.routes.control import do_qbt_resume
            await do_qbt_resume(self.config)
        except Exception as e:
            log.error(f"Failed to resume qBittorrent: {e}")

    def _list_available_configs(self) -> list[Path]:
        """Find all VPN config files available for failover."""
        return list_config_files()

    def _broadcast(self, event: str, data: dict) -> None:
        """Push SSE event to connected clients."""
        try:
            from api.routes.events import broadcast
            broadcast(event, data)
        except Exception:
            pass

    def _log_history(self, event: str, details: dict) -> None:
        """Log to connection history."""
        try:
            from api.services.history import log_event
            log_event(event, details)
        except Exception:
            pass

    def _notify_async(self, event: str, message: str) -> None:
        """Fire notification webhook (non-blocking)."""
        try:
            from api.services.notifications import notify
            asyncio.create_task(notify(event, message, config=self.config))
        except Exception:
            pass

    def _publish_mqtt(self) -> None:
        """Publish state to MQTT."""
        try:
            from api.services.mqtt import get_mqtt_service
            get_mqtt_service().publish_state()
        except Exception:
            pass


# Singleton
_instance: WatchdogService | None = None


def get_watchdog_service(config: Config | None = None, state_mgr: StateManager | None = None) -> WatchdogService:
    global _instance
    if _instance is None:
        if config is None:
            from api.config import load_config
            config = load_config()
        if state_mgr is None:
            state_mgr = StateManager()
        _instance = WatchdogService(config, state_mgr)
    return _instance
