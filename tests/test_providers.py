"""Parametrized provider tests — every provider gets the same assertions.

Ensures all providers implement the required interface correctly,
declare complete metadata, and produce valid ServerInfo objects.
"""

import pytest

from api.services.providers.base import (
    CredentialField,
    PeerConfig,
    ProviderMeta,
    ServerInfo,
    SetupType,
    VPNProvider,
)
from api.services.vpn import PROVIDERS, get_all_provider_meta


# All discovered provider classes, keyed by their meta.id
PROVIDER_IDS = list(PROVIDERS.keys())


def _make_instance(provider_id: str) -> VPNProvider:
    """Instantiate a provider with no config (for metadata-only checks)."""
    cls = PROVIDERS[provider_id]
    return cls()


# ── Discovery ────────────────────────────────────────────────────────────────

class TestProviderDiscovery:
    """Auto-discovery finds all expected providers."""

    def test_known_providers_registered(self):
        expected = {
            "mullvad", "ivpn", "pia", "proton", "custom", "gluetun",
            "nordvpn", "windscribe", "airvpn", "surfshark", "expressvpn",
            "ipvanish", "torguard", "privatevpn", "perfectprivacy", "cyberghost",
            "privado", "purevpn", "vpnsecure", "vpnunlimited", "vyprvpn",
            "fastestvpn", "hidemyass", "slickvpn", "giganews",
        }
        assert expected == set(PROVIDER_IDS)

    def test_no_duplicate_ids(self):
        """Each provider meta.id must be unique."""
        ids = []
        for cls in PROVIDERS.values():
            instance = _make_instance(list(PROVIDERS.keys())[list(PROVIDERS.values()).index(cls)])
            ids.append(instance.meta.id)
        assert len(ids) == len(set(ids)), f"Duplicate provider IDs: {ids}"


# ── Metadata completeness ────────────────────────────────────────────────────

@pytest.mark.parametrize("provider_id", PROVIDER_IDS)
class TestProviderMeta:
    """Every provider must declare complete, valid metadata."""

    def test_has_meta(self, provider_id):
        provider = _make_instance(provider_id)
        meta = provider.meta
        assert isinstance(meta, ProviderMeta)

    def test_meta_id_matches_name(self, provider_id):
        provider = _make_instance(provider_id)
        assert provider.meta.id == provider.name

    def test_meta_has_display_name(self, provider_id):
        provider = _make_instance(provider_id)
        assert provider.meta.display_name, "display_name must not be empty"

    def test_meta_has_description(self, provider_id):
        provider = _make_instance(provider_id)
        assert provider.meta.description, "description must not be empty"

    def test_meta_setup_type_valid(self, provider_id):
        provider = _make_instance(provider_id)
        assert isinstance(provider.meta.setup_type, SetupType)

    def test_meta_credentials_are_credential_fields(self, provider_id):
        provider = _make_instance(provider_id)
        for cred in provider.meta.credentials:
            assert isinstance(cred, CredentialField)
            assert cred.key, "credential key must not be empty"
            assert cred.label, "credential label must not be empty"
            assert cred.field_type in ("text", "password", "textarea"), (
                f"Invalid field_type: {cred.field_type}"
            )

    def test_secret_credentials_use_password_type(self, provider_id):
        """Secret fields should use password field type for UI masking."""
        provider = _make_instance(provider_id)
        for cred in provider.meta.credentials:
            if cred.secret:
                assert cred.field_type == "password", (
                    f"Credential '{cred.key}' is secret but uses field_type='{cred.field_type}' "
                    f"instead of 'password'"
                )

    def test_filter_capabilities_valid(self, provider_id):
        valid_caps = {"country", "city", "owned_only", "streaming", "p2p", "port_forward", "secure_core", "multihop"}
        provider = _make_instance(provider_id)
        caps = set(provider.meta.filter_capabilities)
        invalid = caps - valid_caps
        assert not invalid, f"Invalid filter capabilities: {invalid}"


# ── Interface compliance ──────────────────────────────────────────────────────

@pytest.mark.parametrize("provider_id", PROVIDER_IDS)
class TestProviderInterface:
    """Every provider implements the required VPNProvider methods."""

    def test_is_vpn_provider(self, provider_id):
        provider = _make_instance(provider_id)
        assert isinstance(provider, VPNProvider)

    def test_has_name(self, provider_id):
        provider = _make_instance(provider_id)
        assert provider.name == provider_id

    def test_has_check_connection(self, provider_id):
        provider = _make_instance(provider_id)
        assert callable(getattr(provider, "check_connection", None))

    def test_has_list_servers(self, provider_id):
        provider = _make_instance(provider_id)
        assert callable(getattr(provider, "list_servers", None))

    def test_server_list_providers_have_fetch(self, provider_id):
        """Providers with supports_server_list should override _fetch_servers."""
        provider = _make_instance(provider_id)
        if provider.meta.supports_server_list:
            # Should override _fetch_servers (not use the base empty list)
            assert type(provider)._fetch_servers is not VPNProvider._fetch_servers, (
                f"Provider {provider_id} declares supports_server_list=True "
                f"but doesn't override _fetch_servers()"
            )

    def test_server_list_providers_have_resolve_connect(self, provider_id):
        """Providers with supports_server_list should support the connect pipeline."""
        provider = _make_instance(provider_id)
        if provider.meta.supports_server_list:
            assert callable(getattr(provider, "resolve_connect", None))


# ── Provider API metadata (for setup wizard) ──────────────────────────────────

class TestProviderMetaAPI:
    """get_all_provider_meta() returns valid data for the setup wizard."""

    def test_returns_list(self):
        meta_list = get_all_provider_meta()
        assert isinstance(meta_list, list)
        assert len(meta_list) == len(PROVIDERS)

    def test_each_entry_has_required_fields(self):
        for entry in get_all_provider_meta():
            assert "id" in entry
            assert "name" in entry
            assert "description" in entry
            assert "setup_type" in entry
            assert "credentials" in entry

    def test_setup_type_values(self):
        valid = {t.value for t in SetupType}
        for entry in get_all_provider_meta():
            assert entry["setup_type"] in valid, (
                f"Provider {entry['id']} has invalid setup_type: {entry['setup_type']}"
            )

    def test_credential_entries_complete(self):
        for entry in get_all_provider_meta():
            for cred in entry["credentials"]:
                assert "key" in cred
                assert "label" in cred
                assert "field_type" in cred
                assert "required" in cred
                assert "secret" in cred


# ── ServerInfo integrity ──────────────────────────────────────────────────────

class TestServerInfoDefaults:
    """ServerInfo dataclass has sane defaults."""

    def test_default_values(self):
        s = ServerInfo()
        assert s.hostname == ""
        assert s.ipv4 == ""
        assert s.public_key == ""
        assert s.port == 51820
        assert s.port_forward is False
        assert s.load == 0
        assert s.extra == {}

    def test_typed_fields_not_dynamic(self):
        """All server attributes should be typed fields, not dynamic."""
        s = ServerInfo(hostname="test", ipv4="1.2.3.4", port_forward=True)
        assert s.hostname == "test"
        assert s.ipv4 == "1.2.3.4"
        assert s.port_forward is True
        # No dynamic attributes should exist
        with pytest.raises(TypeError):
            ServerInfo(nonexistent_field="bad")  # type: ignore[call-arg]


# ── PeerConfig integrity ──────────────────────────────────────────────────────

class TestPeerConfig:
    """PeerConfig dataclass for the unified connect pipeline."""

    def test_basic_creation(self):
        peer = PeerConfig(
            private_key="key", address="10.0.0.1/32", dns="1.1.1.1",
            public_key="pubkey", endpoint="1.2.3.4",
        )
        assert peer.private_key == "key"
        assert peer.port == 51820  # default
        assert peer.extra == {}    # default

    def test_with_extras(self):
        peer = PeerConfig(
            private_key="key", address="10.0.0.1/32", dns="1.1.1.1",
            public_key="pubkey", endpoint="1.2.3.4", port=1337,
            extra={"token": "abc", "server_vip": "5.6.7.8"},
        )
        assert peer.port == 1337
        assert peer.extra["token"] == "abc"
