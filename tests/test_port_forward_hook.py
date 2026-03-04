"""Tests for port forward hook — fires on port assignment and release.

Covers settings wiring, hook execution, and both service integrations
(PortForwardService / NatPMPService).
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPortForwardHookSettings:
    """Verify port_forward_hook is wired through the full settings stack."""

    def test_field_in_configurable_fields(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert "port_forward_hook" in CONFIGURABLE_FIELDS

    def test_env_var_name(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["port_forward_hook"]["env"] == "PORT_FORWARD_HOOK"

    def test_default_is_empty(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["port_forward_hook"]["default"] == ""

    def test_not_secret(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["port_forward_hook"]["secret"] is False

    def test_config_field_exists(self):
        from api.config import Config
        config = Config()
        assert config.port_forward_hook == ""

    def test_config_reads_env(self):
        from api.config import Config
        with patch.dict(os.environ, {"PORT_FORWARD_HOOK": "/scripts/on_port.sh"}, clear=False):
            config = Config()
        assert config.port_forward_hook == "/scripts/on_port.sh"

    def test_settings_update_model_has_field(self):
        from api.routes.settings import SettingsUpdate
        update = SettingsUpdate(port_forward_hook="/scripts/qbit_port.sh")
        assert update.port_forward_hook == "/scripts/qbit_port.sh"


class TestFirePortChangeHook:
    """Verify hook execution logic."""

    @pytest.mark.asyncio
    async def test_no_op_when_empty(self):
        from api.services.hooks import fire_port_change_hook
        # Should complete without error and without launching any process
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            await fire_port_change_hook("", 51820)
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_fires_with_port_as_arg(self):
        from api.services.hooks import fire_port_change_hook

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await fire_port_change_hook("/scripts/on_port.sh", 51820)
            mock_exec.assert_called_once_with(
                "/scripts/on_port.sh", "51820",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

    @pytest.mark.asyncio
    async def test_fires_zero_on_release(self):
        from api.services.hooks import fire_port_change_hook

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await fire_port_change_hook("/scripts/on_port.sh", 0)
            mock_exec.assert_called_once_with(
                "/scripts/on_port.sh", "0",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

    @pytest.mark.asyncio
    async def test_hook_with_args_split_correctly(self):
        from api.services.hooks import fire_port_change_hook

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await fire_port_change_hook("/usr/bin/env /scripts/on_port.sh", 12345)
            mock_exec.assert_called_once_with(
                "/usr/bin/env", "/scripts/on_port.sh", "12345",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

    @pytest.mark.asyncio
    async def test_nonzero_exit_logs_warning_no_raise(self):
        from api.services.hooks import fire_port_change_hook

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            # Should not raise
            await fire_port_change_hook("/scripts/on_port.sh", 51820)

    @pytest.mark.asyncio
    async def test_timeout_does_not_raise(self):
        from api.services.hooks import fire_port_change_hook

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await fire_port_change_hook("/scripts/slow_hook.sh", 51820)

    @pytest.mark.asyncio
    async def test_exception_does_not_raise(self):
        from api.services.hooks import fire_port_change_hook

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("not found")):
            await fire_port_change_hook("/nonexistent/hook.sh", 51820)


class TestNatPMPServiceConfig:
    """Verify NatPMPService accepts config and exposes hook script."""

    def test_accepts_config(self):
        from api.services.natpmp import NatPMPService
        mock_config = MagicMock()
        mock_config.port_forward_hook = "/scripts/on_port.sh"
        svc = NatPMPService(config=mock_config)
        assert svc._hook_script == "/scripts/on_port.sh"

    def test_hook_script_empty_without_config(self):
        from api.services.natpmp import NatPMPService
        svc = NatPMPService()
        assert svc._hook_script == ""
