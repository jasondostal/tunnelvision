"""MQTT integration with Home Assistant auto-discovery.

Publishes VPN state on every health check cycle. On connect, sends
HA Discovery messages so entities appear automatically — zero config
on the HA side. Just point at your MQTT broker.

Uses Last Will and Testament (LWT) for availability tracking.
"""

import json
import logging
from pathlib import Path

import paho.mqtt.client as mqtt

from api.config import Config
from api.services.state import StateManager

log = logging.getLogger("tunnelvision.mqtt")


class MQTTService:
    """Publishes TunnelVision state to MQTT with HA Discovery."""

    def __init__(self, config: Config, state_mgr: StateManager):
        self.config = config
        self.state = state_mgr
        self.enabled = config.mqtt_enabled
        self.broker = config.mqtt_broker
        self.port = config.mqtt_port
        self.prefix = config.mqtt_topic_prefix
        self.discovery_prefix = config.mqtt_discovery_prefix
        self.client: mqtt.Client | None = None
        self._connected = False

    def start(self):
        """Connect to MQTT broker and publish discovery messages."""
        if not self.enabled or not self.broker:
            return

        log.info(f"MQTT connecting to {self.broker}:{self.port}")

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="tunnelvision",
        )

        if self.config.mqtt_user:
            self.client.username_pw_set(self.config.mqtt_user, self.config.mqtt_pass)

        # Last Will — marks device offline if container dies
        self.client.will_set(
            f"{self.prefix}/available",
            payload="offline",
            qos=1,
            retain=True,
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            log.error(f"MQTT connection failed: {e}")

    def stop(self):
        """Disconnect gracefully."""
        if self.client and self._connected:
            self.client.publish(f"{self.prefix}/available", "offline", qos=1, retain=True)
            self.client.loop_stop()
            self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            log.info("MQTT connected")
            self._connected = True
            # Publish availability
            client.publish(f"{self.prefix}/available", "online", qos=1, retain=True)
            # Subscribe to commands
            client.subscribe(f"{self.prefix}/command")
            log.info(f"Subscribed to {self.prefix}/command")
            # Publish HA Discovery
            self._publish_discovery()
        else:
            log.error(f"MQTT connect failed: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._connected = False
        log.warning(f"MQTT disconnected: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Handle incoming commands — calls action functions directly."""
        from api.routes.control import (
            do_vpn_restart, do_vpn_disconnect,
            do_killswitch_enable, do_killswitch_disable,
            do_qbt_restart, do_qbt_pause, do_qbt_resume,
        )

        command = msg.payload.decode().strip().lower()
        log.info(f"MQTT command received: {command}")

        # Map commands to action functions
        commands: dict[str, callable] = {
            "vpn_restart": lambda: do_vpn_restart(self.state),
            "vpn_disconnect": lambda: do_vpn_disconnect(self.state),
            "killswitch_enable": lambda: do_killswitch_enable(),
            "killswitch_disable": lambda: do_killswitch_disable(self.state),
        }

        # qBittorrent commands only when enabled
        if self.config.qbt_enabled:
            commands.update({
                "qbt_restart": lambda: do_qbt_restart(self.config),
                "qbt_pause": lambda: do_qbt_pause(self.config),
                "qbt_resume": lambda: do_qbt_resume(self.config),
            })

        if command not in commands:
            log.warning(f"Unknown MQTT command: {command}")
            client.publish(f"{self.prefix}/command_result",
                          json.dumps({"success": False, "error": f"Unknown command: {command}"}))
            return

        try:
            result = commands[command]()
            client.publish(f"{self.prefix}/command_result", result.model_dump_json())
        except Exception as e:
            client.publish(f"{self.prefix}/command_result",
                          json.dumps({"success": False, "error": str(e)}))

        # Publish updated state immediately
        self.publish_state()

    def publish_state(self):
        """Publish current state to MQTT. Called by health monitor."""
        if not self._connected or not self.client:
            return

        state = self.state.snapshot()

        # Publish full state as JSON
        self.client.publish(
            f"{self.prefix}/state",
            json.dumps(state),
            qos=0,
            retain=True,
        )

        # Publish individual topics for simple automations
        for key, value in state.items():
            self.client.publish(
                f"{self.prefix}/{key}",
                str(value),
                qos=0,
                retain=True,
            )

    def _publish_discovery(self):
        """Publish HA MQTT Discovery messages for auto-entity creation."""
        if not self.client:
            return

        device = {
            "identifiers": ["tunnelvision"],
            "name": "TunnelVision",
            "manufacturer": "TunnelVision",
            "model": "VPN Container",
            "sw_version": "0.1.0",
        }

        availability = {
            "topic": f"{self.prefix}/available",
            "payload_available": "online",
            "payload_not_available": "offline",
        }

        # --- Binary Sensors ---
        self._discover("binary_sensor", "vpn", {
            "name": "VPN",
            "state_topic": f"{self.prefix}/vpn_state",
            "payload_on": "up",
            "payload_off": "down",
            "device_class": "connectivity",
            "icon": "mdi:vpn",
        }, device, availability)

        self._discover("binary_sensor", "killswitch", {
            "name": "Killswitch",
            "state_topic": f"{self.prefix}/killswitch",
            "payload_on": "active",
            "payload_off": "disabled",
            "icon": "mdi:shield-lock",
        }, device, availability)

        self._discover("binary_sensor", "healthy", {
            "name": "Health",
            "state_topic": f"{self.prefix}/healthy",
            "payload_on": "true",
            "payload_off": "false",
            "device_class": "problem",
            "value_template": "{{ 'OFF' if value == 'true' else 'ON' }}",
            "icon": "mdi:heart-pulse",
        }, device, availability)

        # --- Sensors ---
        self._discover("sensor", "public_ip", {
            "name": "Public IP",
            "state_topic": f"{self.prefix}/public_ip",
            "icon": "mdi:ip-network",
        }, device, availability)

        self._discover("sensor", "country", {
            "name": "Country",
            "state_topic": f"{self.prefix}/country",
            "icon": "mdi:earth",
        }, device, availability)

        self._discover("sensor", "city", {
            "name": "City",
            "state_topic": f"{self.prefix}/city",
            "icon": "mdi:city",
        }, device, availability)

        self._discover("sensor", "vpn_state", {
            "name": "VPN State",
            "state_topic": f"{self.prefix}/vpn_state",
            "icon": "mdi:vpn",
        }, device, availability)

        self._discover("sensor", "rx_bytes", {
            "name": "Downloaded",
            "state_topic": f"{self.prefix}/rx_bytes",
            "unit_of_measurement": "B",
            "device_class": "data_size",
            "state_class": "total_increasing",
            "icon": "mdi:download",
        }, device, availability)

        self._discover("sensor", "tx_bytes", {
            "name": "Uploaded",
            "state_topic": f"{self.prefix}/tx_bytes",
            "unit_of_measurement": "B",
            "device_class": "data_size",
            "state_class": "total_increasing",
            "icon": "mdi:upload",
        }, device, availability)

        # --- Buttons ---
        vpn_buttons = [
            ("vpn_restart", "Restart VPN", "mdi:vpn", "vpn_restart"),
            ("vpn_rotate", "Rotate Server", "mdi:earth-arrow-right", "vpn_rotate"),
            ("vpn_disconnect", "Disconnect VPN", "mdi:vpn-off", "vpn_disconnect"),
        ]

        qbt_buttons = [
            ("qbt_restart", "Restart qBittorrent", "mdi:restart", "qbt_restart"),
            ("qbt_pause", "Pause All Torrents", "mdi:pause-circle", "qbt_pause"),
            ("qbt_resume", "Resume All Torrents", "mdi:play-circle", "qbt_resume"),
        ]

        buttons = vpn_buttons
        if self.config.qbt_enabled:
            buttons += qbt_buttons

        for btn_id, btn_name, btn_icon, btn_cmd in buttons:
            self._discover("button", btn_id, {
                "name": btn_name,
                "command_topic": f"{self.prefix}/command",
                "payload_press": btn_cmd,
                "icon": btn_icon,
            }, device, availability)

        # --- Watchdog sensors ---
        self._discover("sensor", "watchdog_state", {
            "name": "Watchdog",
            "state_topic": f"{self.prefix}/watchdog_state",
            "icon": "mdi:shield-refresh",
        }, device, availability)

        self._discover("sensor", "active_config", {
            "name": "Active Config",
            "state_topic": f"{self.prefix}/active_config",
            "icon": "mdi:file-cog",
        }, device, availability)

        # --- Switch (killswitch toggle) ---
        self._discover("switch", "killswitch_toggle", {
            "name": "Killswitch",
            "state_topic": f"{self.prefix}/killswitch",
            "command_topic": f"{self.prefix}/command",
            "payload_on": "killswitch_enable",
            "payload_off": "killswitch_disable",
            "state_on": "active",
            "state_off": "disabled",
            "icon": "mdi:shield-lock",
        }, device, availability)

        log.info("HA Discovery messages published")

    def _discover(self, component: str, object_id: str, config: dict,
                  device: dict, availability: dict):
        """Publish a single HA Discovery message."""
        topic = f"{self.discovery_prefix}/{component}/tunnelvision/{object_id}/config"
        payload = {
            **config,
            "unique_id": f"tunnelvision_{object_id}",
            "object_id": f"tunnelvision_{object_id}",
            "device": device,
            "availability": availability,
        }
        self.client.publish(topic, json.dumps(payload), qos=1, retain=True)


# Singleton
_instance: MQTTService | None = None


def get_mqtt_service(config: Config | None = None, state_mgr: StateManager | None = None) -> MQTTService:
    global _instance
    if _instance is None:
        if config is None:
            from api.config import load_config
            config = load_config()
        if state_mgr is None:
            state_mgr = StateManager()
        _instance = MQTTService(config, state_mgr)
    return _instance
