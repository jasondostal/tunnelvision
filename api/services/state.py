"""StateManager — single source of truth for runtime state files.

All /var/run/tunnelvision/* reads and writes go through here.
No more _read_state() helpers scattered across routes.
"""

from pathlib import Path

from api.constants import HealthState, STATE_DIR


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
    def forwarded_port(self, value: str | None) -> None:
        if value is None:
            self.delete("forwarded_port")
        else:
            self.write("forwarded_port", value)

    def delete_forwarded_port(self) -> None:
        self.forwarded_port = None

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
        return self.read("setup_required", HealthState.FALSE) == HealthState.TRUE

    @setup_required.setter
    def setup_required(self, value: bool) -> None:
        self.write("setup_required", HealthState.TRUE if value else HealthState.FALSE)

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

    # --- DNS ---

    @property
    def dns_state(self) -> str:
        return self.read("dns_state", "disabled")

    @property
    def dns_queries_total(self) -> str:
        return self.read("dns_queries_total", "0")

    @property
    def dns_cache_hits(self) -> str:
        return self.read("dns_cache_hits", "0")

    @property
    def dns_blocked_total(self) -> str:
        return self.read("dns_blocked_total", "0")

    # --- HTTP Proxy ---

    @property
    def http_proxy_state(self) -> str:
        return self.read("http_proxy_state", "disabled")

    # --- SOCKS Proxy ---

    @property
    def socks_proxy_state(self) -> str:
        return self.read("socks_proxy_state", "disabled")

    # --- Shadowsocks ---

    @property
    def shadowsocks_state(self) -> str:
        return self.read("shadowsocks_state", "disabled")

    # --- Watchdog ---

    @property
    def watchdog_state(self) -> str:
        return self.read("watchdog_state", "idle")

    @watchdog_state.setter
    def watchdog_state(self, value: str) -> None:
        self.write("watchdog_state", value)

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
            "watchdog_state": self.watchdog_state,
            "active_config": self.active_config,
            "dns_state": self.dns_state,
            "dns_queries_total": self.dns_queries_total,
            "dns_cache_hits": self.dns_cache_hits,
            "dns_blocked_total": self.dns_blocked_total,
            "http_proxy_state": self.http_proxy_state,
            "socks_proxy_state": self.socks_proxy_state,
            "shadowsocks_state": self.shadowsocks_state,
        }
