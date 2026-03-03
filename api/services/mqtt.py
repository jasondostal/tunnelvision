"""MQTT integration with Home Assistant auto-discovery.

Publishes VPN state on every health check cycle. On connect, sends
HA Discovery messages so entities appear automatically — zero config
on the HA side. Just point at your MQTT broker.

Uses Last Will and Testament (LWT) for availability tracking.
"""

import json
import logging
import os
import threading
from pathlib import Path

import paho.mqtt.client as mqtt

log = logging.getLogger("tunnelvision.mqtt")

STATE_DIR = Path("/var/run/tunnelvision")


class MQTTService:
    """Publishes TunnelVision state to MQTT with HA Discovery."""

    def __init__(self):
        self.enabled = os.getenv("MQTT_ENABLED", "false").lower() == "true"
        self.broker = os.getenv("MQTT_BROKER", "")
        self.port = int(os.getenv("MQTT_PORT", "1883"))
        self.user = os.getenv("MQTT_USER", "")
        self.password = os.getenv("MQTT_PASS", "")
        self.prefix = os.getenv("MQTT_TOPIC_PREFIX", "tunnelvision")
        self.discovery_prefix = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant")
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

        if self.user:
            self.client.username_pw_set(self.user, self.password)

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
        """Handle incoming commands from HA or other MQTT clients."""
        import subprocess
        command = msg.payload.decode().strip().lower()
        log.info(f"MQTT command received: {command}")

        commands = {
            "vpn_restart": ["POST", "/api/v1/vpn/restart"],
            "vpn_disconnect": ["POST", "/api/v1/vpn/disconnect"],
            "vpn_reconnect": ["POST", "/api/v1/vpn/reconnect"],
            "vpn_rotate": ["POST", "/api/v1/vpn/rotate"],
            "killswitch_enable": ["POST", "/api/v1/killswitch/enable"],
            "killswitch_disable": ["POST", "/api/v1/killswitch/disable"],
            "qbt_restart": ["POST", "/api/v1/qbt/restart"],
            "qbt_pause": ["POST", "/api/v1/qbt/pause"],
            "qbt_resume": ["POST", "/api/v1/qbt/resume"],
        }

        if command not in commands:
            log.warning(f"Unknown MQTT command: {command}")
            client.publish(f"{self.prefix}/command_result",
                          json.dumps({"success": False, "error": f"Unknown command: {command}"}))
            return

        method, path = commands[command]
        try:
            result = subprocess.run(
                ["curl", "-sf", "-X", method, f"http://localhost:8081{path}"],
                capture_output=True, text=True, timeout=30,
            )
            client.publish(f"{self.prefix}/command_result", result.stdout or '{"success": true}')
        except Exception as e:
            client.publish(f"{self.prefix}/command_result",
                          json.dumps({"success": False, "error": str(e)}))

        # Publish updated state immediately
        self.publish_state()

    def publish_state(self):
        """Publish current state to MQTT. Called by health monitor."""
        if not self._connected or not self.client:
            return

        state = self._read_all_state()

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

    def _read_all_state(self) -> dict:
        """Read all state files into a dict."""
        def _read(name: str, default: str = "") -> str:
            try:
                return (STATE_DIR / name).read_text().strip()
            except FileNotFoundError:
                return default

        return {
            "vpn_state": _read("vpn_state", "unknown"),
            "public_ip": _read("public_ip"),
            "country": _read("country"),
            "city": _read("city"),
            "organization": _read("organization"),
            "killswitch": _read("killswitch_state", "disabled"),
            "vpn_type": _read("vpn_type", "wireguard"),
            "rx_bytes": _read("rx_bytes", "0"),
            "tx_bytes": _read("tx_bytes", "0"),
            "healthy": _read("healthy", "true"),
        }

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

        # --- Buttons (HA 2024.2+ button platform via MQTT) ---
        for btn_id, btn_name, btn_icon, btn_cmd in [
            ("vpn_restart", "Restart VPN", "mdi:vpn", "vpn_restart"),
            ("vpn_rotate", "Rotate Server", "mdi:earth-arrow-right", "vpn_rotate"),
            ("vpn_disconnect", "Disconnect VPN", "mdi:vpn-off", "vpn_disconnect"),
            ("qbt_restart", "Restart qBittorrent", "mdi:restart", "qbt_restart"),
            ("qbt_pause", "Pause All Torrents", "mdi:pause-circle", "qbt_pause"),
            ("qbt_resume", "Resume All Torrents", "mdi:play-circle", "qbt_resume"),
        ]:
            self._discover("button", btn_id, {
                "name": btn_name,
                "command_topic": f"{self.prefix}/command",
                "payload_press": btn_cmd,
                "icon": btn_icon,
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


def get_mqtt_service() -> MQTTService:
    global _instance
    if _instance is None:
        _instance = MQTTService()
    return _instance
