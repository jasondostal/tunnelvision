"""Tests for WG_USERSPACE setting — userspace WireGuard fallback.

Validates the three-way sync (Config / CONFIGURABLE_FIELDS / SettingsUpdate)
and the auto-detection logic patterns used by init-vpn.sh.
"""

import os
from unittest.mock import patch


class TestWgUserspaceSettings:
    """Verify wg_userspace is registered everywhere it needs to be."""

    def test_field_in_configurable_fields(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert "wg_userspace" in CONFIGURABLE_FIELDS

    def test_env_var_name(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["wg_userspace"]["env"] == "WG_USERSPACE"

    def test_default_is_auto(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["wg_userspace"]["default"] == "auto"

    def test_not_secret(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["wg_userspace"]["secret"] is False

    def test_config_field_exists(self):
        from api.config import Config
        config = Config()
        assert config.wg_userspace == "auto"

    def test_config_reads_env(self):
        from api.config import Config
        with patch.dict(os.environ, {"WG_USERSPACE": "userspace"}, clear=False):
            config = Config()
        assert config.wg_userspace == "userspace"

    def test_config_kernel_mode(self):
        from api.config import Config
        with patch.dict(os.environ, {"WG_USERSPACE": "kernel"}, clear=False):
            config = Config()
        assert config.wg_userspace == "kernel"

    def test_settings_update_model_has_field(self):
        from api.routes.settings import SettingsUpdate
        update = SettingsUpdate(wg_userspace="userspace")
        assert update.wg_userspace == "userspace"

    def test_load_settings_returns_field(self, tmp_path):
        from api.services.settings import load_settings
        with patch.dict(os.environ, {"WG_USERSPACE": "userspace"}, clear=False), \
             patch("api.services.settings.SETTINGS_PATH", tmp_path / "nonexistent.yml"):
            settings = load_settings()
        assert settings["wg_userspace"] == "userspace"


class TestWgUserspaceDetectionLogic:
    """Verify the auto-detection logic patterns from init-vpn.sh.

    These test the decision logic without running the actual shell script.
    """

    VALID_MODES = {"auto", "kernel", "userspace"}

    def _resolve_implementation(self, wg_userspace: str, kernel_available: bool) -> str:
        """Replicate the init-vpn.sh decision logic."""
        if wg_userspace == "userspace":
            return "userspace"
        elif wg_userspace == "kernel":
            return "kernel"
        else:  # auto
            return "kernel" if kernel_available else "userspace"

    def test_explicit_userspace_always_userspace(self):
        assert self._resolve_implementation("userspace", kernel_available=True) == "userspace"
        assert self._resolve_implementation("userspace", kernel_available=False) == "userspace"

    def test_explicit_kernel_always_kernel(self):
        assert self._resolve_implementation("kernel", kernel_available=True) == "kernel"
        assert self._resolve_implementation("kernel", kernel_available=False) == "kernel"

    def test_auto_prefers_kernel_when_available(self):
        assert self._resolve_implementation("auto", kernel_available=True) == "kernel"

    def test_auto_falls_back_to_userspace(self):
        assert self._resolve_implementation("auto", kernel_available=False) == "userspace"

    def test_valid_modes(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        default = CONFIGURABLE_FIELDS["wg_userspace"]["default"]
        assert default in self.VALID_MODES
