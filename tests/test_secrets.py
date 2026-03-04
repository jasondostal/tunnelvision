"""Tests for Docker secrets support (Phase 1).

Tests _read_secret_file(), load_settings() secret precedence, and _secret_or_env() in Config.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestReadSecretFile:
    """Tests for _read_secret_file() in settings.py."""

    def test_reads_existing_file(self, tmp_path):
        from api.services.settings import _read_secret_file

        secret_file = tmp_path / "my_secret"
        secret_file.write_text("s3cret_value\n")

        with patch.dict(os.environ, {"API_KEY_SECRETFILE": str(secret_file)}):
            result = _read_secret_file("API_KEY")
        assert result == "s3cret_value"

    def test_strips_whitespace(self, tmp_path):
        from api.services.settings import _read_secret_file

        secret_file = tmp_path / "secret"
        secret_file.write_text("  password123  \n\n")

        with patch.dict(os.environ, {"MQTT_PASS_SECRETFILE": str(secret_file)}):
            result = _read_secret_file("MQTT_PASS")
        assert result == "password123"

    def test_returns_none_when_env_not_set(self):
        from api.services.settings import _read_secret_file

        with patch.dict(os.environ, {}, clear=True):
            result = _read_secret_file("NONEXISTENT")
        assert result is None

    def test_returns_none_when_file_missing(self):
        from api.services.settings import _read_secret_file

        with patch.dict(os.environ, {"API_KEY_SECRETFILE": "/nonexistent/path"}):
            result = _read_secret_file("API_KEY")
        assert result is None

    def test_returns_none_when_env_is_empty(self):
        from api.services.settings import _read_secret_file

        with patch.dict(os.environ, {"API_KEY_SECRETFILE": ""}):
            result = _read_secret_file("API_KEY")
        assert result is None


class TestLoadSettingsSecretPrecedence:
    """Precedence: YAML > secret file > env var > default."""

    def test_yaml_wins_over_secret_file(self, tmp_path):
        from api.services.settings import load_settings, SETTINGS_PATH

        secret_file = tmp_path / "secret"
        secret_file.write_text("from_secret")

        yaml_file = tmp_path / "tunnelvision.yml"
        yaml_file.write_text("api_key: from_yaml\n")

        env = {"API_KEY_SECRETFILE": str(secret_file), "API_KEY": "from_env"}
        with patch.dict(os.environ, env, clear=False), \
             patch("api.services.settings.SETTINGS_PATH", yaml_file):
            settings = load_settings()
        assert settings["api_key"] == "from_yaml"

    def test_secret_file_wins_over_env(self, tmp_path):
        from api.services.settings import load_settings

        secret_file = tmp_path / "secret"
        secret_file.write_text("from_secret")

        yaml_file = tmp_path / "nonexistent.yml"  # No YAML file

        env = {"API_KEY_SECRETFILE": str(secret_file), "API_KEY": "from_env"}
        with patch.dict(os.environ, env, clear=False), \
             patch("api.services.settings.SETTINGS_PATH", yaml_file):
            settings = load_settings()
        assert settings["api_key"] == "from_secret"

    def test_env_used_when_no_secret_file(self, tmp_path):
        from api.services.settings import load_settings

        yaml_file = tmp_path / "nonexistent.yml"
        env = {"API_KEY": "from_env"}
        with patch.dict(os.environ, env, clear=False), \
             patch("api.services.settings.SETTINGS_PATH", yaml_file):
            settings = load_settings()
        assert settings["api_key"] == "from_env"

    def test_non_secret_fields_ignore_secretfile(self, tmp_path):
        """Non-secret fields should NOT check _SECRETFILE."""
        from api.services.settings import load_settings

        secret_file = tmp_path / "secret"
        secret_file.write_text("should_not_be_used")

        yaml_file = tmp_path / "nonexistent.yml"
        env = {
            "VPN_PROVIDER_SECRETFILE": str(secret_file),
            "VPN_PROVIDER": "mullvad",
        }
        with patch.dict(os.environ, env, clear=False), \
             patch("api.services.settings.SETTINGS_PATH", yaml_file):
            settings = load_settings()
        assert settings["vpn_provider"] == "mullvad"


class TestSecretOrEnv:
    """Tests for _secret_or_env() in config.py."""

    def test_reads_secret_file(self, tmp_path):
        from api.config import _secret_or_env

        secret_file = tmp_path / "secret"
        secret_file.write_text("secret_value\n")

        with patch.dict(os.environ, {"TEST_KEY_SECRETFILE": str(secret_file)}):
            result = _secret_or_env("TEST_KEY", "default")
        assert result == "secret_value"

    def test_falls_back_to_env(self):
        from api.config import _secret_or_env

        with patch.dict(os.environ, {"TEST_KEY": "env_value"}, clear=False):
            result = _secret_or_env("TEST_KEY", "default")
        assert result == "env_value"

    def test_falls_back_to_default(self):
        from api.config import _secret_or_env

        env_clear = {k: v for k, v in os.environ.items()
                     if k not in ("TEST_KEY", "TEST_KEY_SECRETFILE")}
        with patch.dict(os.environ, env_clear, clear=True):
            result = _secret_or_env("TEST_KEY", "default")
        assert result == "default"

    def test_secret_file_wins_over_env(self, tmp_path):
        from api.config import _secret_or_env

        secret_file = tmp_path / "secret"
        secret_file.write_text("from_secret")

        env = {"TEST_KEY_SECRETFILE": str(secret_file), "TEST_KEY": "from_env"}
        with patch.dict(os.environ, env, clear=False):
            result = _secret_or_env("TEST_KEY", "default")
        assert result == "from_secret"

    def test_config_uses_secret_or_env_for_secret_fields(self, tmp_path):
        """Verify Config dataclass picks up secret files for known secret fields."""
        from api.config import Config

        secret_file = tmp_path / "api_key_secret"
        secret_file.write_text("secret_api_key")

        env = {"API_KEY_SECRETFILE": str(secret_file)}
        with patch.dict(os.environ, env, clear=False):
            config = Config()
        assert config.api_key == "secret_api_key"
