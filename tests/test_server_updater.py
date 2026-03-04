"""Tests for server list auto-updater and richer server filters."""

import os
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# ServerFilter
# =============================================================================

class TestServerFilter:
    """Verify ServerFilter dataclass and _filter_servers logic."""

    def _make_servers(self):
        from api.services.providers.base import ServerInfo
        return [
            ServerInfo(hostname="us-001", country="United States", country_code="us",
                       city="New York", city_code="nyc", owned=True, p2p=True,
                       streaming=False, port_forward=True, secure_core=False,
                       multihop=False, load=30),
            ServerInfo(hostname="de-001", country="Germany", country_code="de",
                       city="Frankfurt", city_code="fra", owned=False, p2p=True,
                       streaming=True, port_forward=False, secure_core=True,
                       multihop=False, load=80),
            ServerInfo(hostname="se-001", country="Sweden", country_code="se",
                       city="Stockholm", city_code="sto", owned=True, p2p=False,
                       streaming=True, port_forward=True, secure_core=False,
                       multihop=True, load=10),
        ]

    def _filter(self, servers, **kwargs):
        from api.services.providers.base import ServerFilter, VPNProvider
        from api.services.providers.mullvad import MullvadProvider
        f = ServerFilter(**kwargs)
        return MullvadProvider._filter_servers(servers, f)

    def test_no_filter_returns_all(self):
        servers = self._make_servers()
        result = self._filter(servers)
        assert len(result) == 3

    def test_filter_by_country_code(self):
        servers = self._make_servers()
        result = self._filter(servers, country="de")
        assert len(result) == 1
        assert result[0].hostname == "de-001"

    def test_filter_by_country_name_case_insensitive(self):
        servers = self._make_servers()
        result = self._filter(servers, country="sweden")
        assert len(result) == 1
        assert result[0].hostname == "se-001"

    def test_filter_by_city(self):
        servers = self._make_servers()
        result = self._filter(servers, city="frankfurt")
        assert len(result) == 1
        assert result[0].hostname == "de-001"

    def test_filter_owned_only(self):
        servers = self._make_servers()
        result = self._filter(servers, owned_only=True)
        assert len(result) == 2
        assert all(s.owned for s in result)

    def test_filter_p2p(self):
        servers = self._make_servers()
        result = self._filter(servers, p2p=True)
        assert len(result) == 2
        result_no_p2p = self._filter(servers, p2p=False)
        assert len(result_no_p2p) == 1

    def test_filter_streaming(self):
        servers = self._make_servers()
        result = self._filter(servers, streaming=True)
        assert len(result) == 2

    def test_filter_port_forward(self):
        servers = self._make_servers()
        result = self._filter(servers, port_forward=True)
        assert len(result) == 2

    def test_filter_secure_core(self):
        servers = self._make_servers()
        result = self._filter(servers, secure_core=True)
        assert len(result) == 1
        assert result[0].hostname == "de-001"

    def test_filter_multihop(self):
        servers = self._make_servers()
        result = self._filter(servers, multihop=True)
        assert len(result) == 1
        assert result[0].hostname == "se-001"

    def test_filter_max_load(self):
        servers = self._make_servers()
        result = self._filter(servers, max_load=50)
        assert len(result) == 2
        assert all(s.load <= 50 for s in result)

    def test_filter_combines(self):
        servers = self._make_servers()
        result = self._filter(servers, country="us", port_forward=True, max_load=50)
        assert len(result) == 1
        assert result[0].hostname == "us-001"

    def test_filter_no_match_returns_empty(self):
        servers = self._make_servers()
        result = self._filter(servers, country="jp")
        assert result == []

    def test_null_filter_skips_none_fields(self):
        """None filter fields should not filter anything."""
        from api.services.providers.base import ServerFilter
        f = ServerFilter(owned_only=None, p2p=None)
        # None means "don't filter by this" — all servers pass
        servers = self._make_servers()
        from api.services.providers.mullvad import MullvadProvider
        result = MullvadProvider._filter_servers(servers, f)
        assert len(result) == 3


# =============================================================================
# Settings wiring
# =============================================================================

class TestServerUpdaterSettings:
    """Verify auto-updater settings are wired through the full stack."""

    def test_auto_update_in_configurable_fields(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert "server_list_auto_update" in CONFIGURABLE_FIELDS
        assert "server_list_update_interval" in CONFIGURABLE_FIELDS

    def test_defaults(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        from api.constants import PROVIDER_CACHE_TTL
        assert CONFIGURABLE_FIELDS["server_list_auto_update"]["default"] == "true"
        assert CONFIGURABLE_FIELDS["server_list_update_interval"]["default"] == str(PROVIDER_CACHE_TTL)

    def test_config_fields_exist(self):
        from api.config import Config
        config = Config()
        assert config.server_list_auto_update is True
        assert config.server_list_update_interval > 0

    def test_config_reads_env(self):
        from api.config import Config
        with patch.dict(os.environ, {
            "SERVER_LIST_AUTO_UPDATE": "false",
            "SERVER_LIST_UPDATE_INTERVAL": "1800",
        }, clear=False):
            config = Config()
        assert config.server_list_auto_update is False
        assert config.server_list_update_interval == 1800

    def test_settings_update_model_has_fields(self):
        from api.routes.settings import SettingsUpdate
        update = SettingsUpdate(server_list_auto_update="false", server_list_update_interval="1800")
        assert update.server_list_auto_update == "false"
        assert update.server_list_update_interval == "1800"


# =============================================================================
# ServerListUpdater behavior
# =============================================================================

class TestServerListUpdater:
    """Verify updater lifecycle and behavior."""

    def test_disabled_when_config_says_false(self):
        from api.services.server_updater import ServerListUpdater
        config = MagicMock()
        config.server_list_auto_update = False
        updater = ServerListUpdater(config=config)
        assert not updater._enabled

    def test_enabled_by_default(self):
        from api.services.server_updater import ServerListUpdater
        updater = ServerListUpdater()
        assert updater._enabled

    def test_interval_from_config(self):
        from api.services.server_updater import ServerListUpdater
        config = MagicMock()
        config.server_list_update_interval = 1800
        updater = ServerListUpdater(config=config)
        assert updater._interval == 1800

    def test_interval_default_is_provider_cache_ttl(self):
        from api.services.server_updater import ServerListUpdater
        from api.constants import PROVIDER_CACHE_TTL
        updater = ServerListUpdater()
        assert updater._interval == PROVIDER_CACHE_TTL

    def test_not_active_before_start(self):
        from api.services.server_updater import ServerListUpdater
        updater = ServerListUpdater()
        assert not updater.active
