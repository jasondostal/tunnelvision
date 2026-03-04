"""StateManager — single source of truth for runtime state files.

All /var/run/tunnelvision/* reads and writes go through here.
No more _read_state() helpers scattered across routes.
"""

from pathlib import Path


STATE_DIR = Path("/var/run/tunnelvision")


class StateManager:
    """Typed accessors for runtime state under /var/run/tunnelvision/."""

    def __init__(self, state_dir: Path = STATE_DIR):
        self._dir = state_dir

    def read(self, key: str, default: str = "") -> str:
        """Read a state file. Returns default if missing."""
        try:
            return (self._dir / key).read_text().strip()
        except FileNotFoundError:
            return default

    def write(self, key: str, value: str) -> None:
        """Write a state file."""
        (self._dir / key).write_text(value)

    def delete(self, key: str) -> None:
        """Delete a state file if it exists."""
        try:
            (self._dir / key).unlink()
        except FileNotFoundError:
            pass

    # --- VPN ---

    @property
    def vpn_state(self) -> str:
        return self.read("vpn_state", "unknown")

    @vpn_state.setter
    def vpn_state(self, value: str) -> None:
        self.write("vpn_state", value)

    @property
    def vpn_type(self) -> str:
        return self.read("vpn_type", "wireguard")

    @vpn_type.setter
    def vpn_type(self, value: str) -> None:
        self.write("vpn_type", value)

    @property
    def vpn_interface(self) -> str:
        return self.read("vpn_interface", "wg0")

    @property
    def vpn_ip(self) -> str:
        return self.read("vpn_ip")

    @property
    def vpn_endpoint(self) -> str:
        return self.read("vpn_endpoint")

    @property
    def vpn_started_at(self) -> str:
        return self.read("vpn_started_at")

    @property
    def vpn_server_hostname(self) -> str:
        return self.read("vpn_server_hostname")

    @vpn_server_hostname.setter
    def vpn_server_hostname(self, value: str) -> None:
        self.write("vpn_server_hostname", value)

    @property
    def last_handshake(self) -> str:
        return self.read("last_handshake")

    @property
    def public_ip(self) -> str:
        return self.read("public_ip")

    @property
    def country(self) -> str:
        return self.read("country")

    @property
    def city(self) -> str:
        return self.read("city")

    @property
    def organization(self) -> str:
        return self.read("organization")

    @property
    def rx_bytes(self) -> str:
        return self.read("rx_bytes", "0")

    @property
    def tx_bytes(self) -> str:
        return self.read("tx_bytes", "0")

    @property
    def forwarded_port(self) -> str:
        return self.read("forwarded_port")

    @forwarded_port.setter
    def forwarded_port(self, value: str) -> None:
        self.write("forwarded_port", value)

    def delete_forwarded_port(self) -> None:
        self.delete("forwarded_port")

    # --- Killswitch ---

    @property
    def killswitch_state(self) -> str:
        return self.read("killswitch_state", "disabled")

    @killswitch_state.setter
    def killswitch_state(self, value: str) -> None:
        self.write("killswitch_state", value)

    # --- Health ---

    @property
    def healthy(self) -> str:
        return self.read("healthy", "true")

    # --- Setup ---

    @property
    def setup_required(self) -> bool:
        return self.read("setup_required", "false") == "true"

    @setup_required.setter
    def setup_required(self, value: bool) -> None:
        self.write("setup_required", "true" if value else "false")

    @property
    def setup_provider(self) -> str:
        return self.read("setup_provider")

    @setup_provider.setter
    def setup_provider(self, value: str) -> None:
        self.write("setup_provider", value)

    # --- Connection tracking ---

    @property
    def active_config(self) -> str:
        return self.read("active_config")

    @active_config.setter
    def active_config(self, value: str) -> None:
        self.write("active_config", value)

    # --- Snapshot (for MQTT / bulk reads) ---

    def snapshot(self) -> dict[str, str]:
        """Read all state into a dict. Used by MQTT publish_state."""
        return {
            "vpn_state": self.vpn_state,
            "public_ip": self.public_ip,
            "country": self.country,
            "city": self.city,
            "organization": self.organization,
            "killswitch": self.killswitch_state,
            "vpn_type": self.vpn_type,
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "healthy": self.healthy,
        }
