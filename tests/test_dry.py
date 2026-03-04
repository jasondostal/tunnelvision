"""DRY violation detection — prevents hardcoded magic values from creeping back.

These tests act as architectural guardrails. They grep the codebase for patterns
that violate our single-source-of-truth principle. If a test here fails, it means
someone introduced a hardcoded value that should come from api/constants.py.
"""

import glob
import re


# Files that ARE the source of truth — exempt from checks
EXEMPT_FILES = {
    "api/constants.py",
}

# Proxy services use raw asyncio socket timeouts (TCP protocol-level),
# not our HTTP/subprocess timeout tiers
SOCKET_TIMEOUT_EXEMPT = {
    "api/services/http_proxy.py",
    "api/services/socks_proxy.py",
    "api/services/shadowsocks.py",
}


def _source_files(subdir: str = "api", exclude: set[str] | None = None) -> list[tuple[str, str]]:
    """Return (path, source) tuples for all .py files under subdir."""
    exclude = (exclude or set()) | EXEMPT_FILES
    results = []
    for path in sorted(glob.glob(f"{subdir}/**/*.py", recursive=True)):
        if any(path.endswith(ex) or ex in path for ex in exclude):
            continue
        with open(path) as f:
            results.append((path, f.read()))
    return results


# ── httpx ────────────────────────────────────────────────────────────────────

class TestNoRawHttpx:
    """All httpx usage should go through http_client() from constants."""

    def test_no_raw_async_client(self):
        for path, source in _source_files():
            assert "httpx.AsyncClient" not in source, (
                f"{path} uses raw httpx.AsyncClient — use http_client() from api.constants"
            )

    def test_no_direct_httpx_import(self):
        """Only constants.py should import httpx directly."""
        for path, source in _source_files():
            if "import httpx" in source:
                # Allow `from api.constants import http_client` but not `import httpx`
                lines = [l.strip() for l in source.splitlines() if "import httpx" in l]
                for line in lines:
                    assert line != "import httpx", (
                        f"{path} imports httpx directly — use http_client() from api.constants"
                    )


# ── Subprocess timeouts ──────────────────────────────────────────────────────

class TestNoHardcodedSubprocessTimeouts:
    """Subprocess timeouts should use SUBPROCESS_TIMEOUT_* constants."""

    # Matches timeout=5, timeout=10, timeout=15, timeout=30 (integer literals)
    TIMEOUT_RE = re.compile(r"\btimeout\s*=\s*(\d+)\s*[,\)]")

    def test_no_bare_integer_timeouts(self):
        for path, source in _source_files(exclude=SOCKET_TIMEOUT_EXEMPT):
            if "subprocess" not in source:
                continue
            for i, line in enumerate(source.splitlines(), 1):
                match = self.TIMEOUT_RE.search(line)
                if match and "SUBPROCESS_TIMEOUT" not in line:
                    assert False, (
                        f"{path}:{i} has hardcoded subprocess timeout={match.group(1)} "
                        f"— use SUBPROCESS_TIMEOUT_* from api.constants"
                    )


# ── State strings ────────────────────────────────────────────────────────────

class TestNoHardcodedStateStrings:
    """Route and service files should use state enums, not raw string comparisons."""

    # Patterns that indicate raw state string comparisons.
    # Each entry: (regex_pattern, human-readable replacement suggestion)
    # Patterns are designed to catch state comparisons while ignoring:
    #   - Boolean config parsing: .lower() == "true"
    #   - External API responses: gluetun_status == "running" (protocol contract)
    BANNED_PATTERNS = [
        (re.compile(r'(?<!gluetun_status\s)== "up"'), "VpnState.UP"),
        (re.compile(r'== "down"'), "VpnState.DOWN"),
        (re.compile(r'== "active"'), "KillswitchState.ACTIVE"),
        (re.compile(r'(?<!\.lower\(\)\s)== "disabled"'), "ServiceState.DISABLED / KillswitchState.DISABLED"),
        # Exempt gluetun API response checks: gluetun_status == "running", data.get("status") == "running"
        (re.compile(r'(?<!gluetun_status\s)(?<!\.lower\(\)\s)(?<!"status"\)\s)== "running"'), "ServiceState.RUNNING"),
        # Only match == "true"/"false" that are NOT preceded by .lower() (boolean config parsing)
        (re.compile(r'(?<!\.lower\(\)\s)== "true"'), "HealthState.TRUE"),
        (re.compile(r'(?<!\.lower\(\)\s)== "false"'), "HealthState.FALSE"),
    ]

    # MQTT publishes HA protocol strings — external interface contracts, not internal state
    STATE_STRING_EXEMPT = {
        "api/services/mqtt.py",
        "tests/",
    }

    def _check_file(self, path: str, source: str):
        for line_no, line in enumerate(source.splitlines(), 1):
            for pattern, replacement in self.BANNED_PATTERNS:
                if pattern.search(line):
                    assert False, (
                        f"{path}:{line_no} uses raw state string — use {replacement} from api.constants\n"
                        f"  line: {line.strip()}"
                    )

    def test_no_raw_state_comparisons_in_routes(self):
        for path, source in _source_files("api/routes"):
            self._check_file(path, source)

    def test_no_raw_state_comparisons_in_services(self):
        for path, source in _source_files("api/services", exclude=self.STATE_STRING_EXEMPT):
            self._check_file(path, source)


# ── Path constants ───────────────────────────────────────────────────────────

class TestNoHardcodedPaths:
    """Filesystem paths should come from constants, not be hardcoded."""

    BANNED_PATHS = [
        '"/config/wireguard"',
        '"/config/openvpn"',
        '"/config/wireguard/wg0.conf"',
        '"/config/tunnelvision.yml"',
        '"/var/run/tunnelvision"',
    ]

    def test_no_hardcoded_config_paths(self):
        for path, source in _source_files():
            for banned in self.BANNED_PATHS:
                assert banned not in source, (
                    f"{path} has hardcoded path {banned} — use constant from api.constants"
                )


# ── Port defaults ────────────────────────────────────────────────────────────

class TestNoHardcodedPortDefaults:
    """Port defaults should come from constants, not be scattered across files."""

    # Only check files that define defaults — not runtime usage like f"localhost:{config.port}"
    PORT_DEFAULT_RE = re.compile(r'default\s*[:=]\s*["\']?(8080|8081|8888|1080|1883|8000)["\']?')

    def test_no_hardcoded_port_defaults(self):
        for path, source in _source_files():
            for i, line in enumerate(source.splitlines(), 1):
                match = self.PORT_DEFAULT_RE.search(line)
                if match:
                    port = match.group(1)
                    assert False, (
                        f"{path}:{i} has hardcoded port default {port} "
                        f"— use constant from api.constants"
                    )


# ── Settings ↔ Model alignment ──────────────────────────────────────────────

class TestSettingsAlignment:
    """CONFIGURABLE_FIELDS, SettingsUpdate, and Config must stay in sync."""

    def test_all_configurable_fields_in_update_model(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        from api.routes.settings import SettingsUpdate

        model_fields = set(SettingsUpdate.model_fields.keys())
        config_fields = set(CONFIGURABLE_FIELDS.keys())
        missing = config_fields - model_fields
        assert missing == set(), (
            f"Fields in CONFIGURABLE_FIELDS but not in SettingsUpdate: {missing}"
        )

    def test_all_configurable_fields_in_config(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        from api.config import Config

        # Config uses dataclass fields
        import dataclasses
        config_attrs = {f.name for f in dataclasses.fields(Config)}
        settings_fields = set(CONFIGURABLE_FIELDS.keys())

        # Some settings don't map 1:1 to Config fields
        known_mappings = {
            "killswitch_enabled",  # maps to vpn_enabled logic
            "vpn_dns",             # setup-only field, written to WG config, not runtime Config
        }
        check_fields = settings_fields - known_mappings
        missing = check_fields - config_attrs
        assert missing == set(), (
            f"Fields in CONFIGURABLE_FIELDS but not in Config dataclass: {missing}"
        )

    def test_secret_fields_use_secret_or_env(self):
        """Fields marked secret: True should use _secret_or_env in Config."""
        from api.services.settings import CONFIGURABLE_FIELDS
        import inspect
        from api import config as config_module

        source = inspect.getsource(config_module)
        secret_fields = [k for k, v in CONFIGURABLE_FIELDS.items() if v.get("secret")]

        for field in secret_fields:
            env_name = CONFIGURABLE_FIELDS[field]["env"]
            # Check that _secret_or_env is called with this field's env var name
            assert env_name in source, (
                f"Secret field '{field}' (env={env_name}) not found in config.py — "
                f"should use _secret_or_env(\"{env_name}\", ...)"
            )


# ── WireGuard symlink dedup ─────────────────────────────────────────────────

class TestNoWgSymlinkDuplication:
    """WireGuard symlink logic should only exist in activate_wg_config()."""

    def test_no_manual_wg_symlink(self):
        for path, source in _source_files():
            if "symlink_to" in source and "wg0" in source:
                assert False, (
                    f"{path} has manual WireGuard symlink logic "
                    f"— use activate_wg_config() from api.constants"
                )
