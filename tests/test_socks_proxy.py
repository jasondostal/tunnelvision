"""Tests for SOCKS5 proxy, Shadowsocks encryption, and Shadowsocks server."""

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.socks_proxy import (
    SocksProxyService, SOCKS_VERSION, AUTH_NONE, AUTH_USERPASS,
    AUTH_NO_ACCEPTABLE, CMD_CONNECT, ATYP_IPV4, ATYP_DOMAIN, ATYP_IPV6,
    REP_SUCCESS, REP_CONNECTION_REFUSED,
)
from api.services.shadowsocks import (
    AEADCipher, derive_key, _evp_bytes_to_key, create_encryptor,
    create_decryptor, CIPHERS, TAG_SIZE, MAX_PAYLOAD,
    ShadowsocksService, _parse_address, ATYP_IPV4 as SS_ATYP_IPV4,
    ATYP_DOMAIN as SS_ATYP_DOMAIN, ATYP_IPV6 as SS_ATYP_IPV6,
)
from api.services.state import StateManager


def _make_config(**overrides):
    defaults = {
        "socks_proxy_enabled": True,
        "socks_proxy_port": 11080,
        "socks_proxy_user": "",
        "socks_proxy_pass": "",
        "shadowsocks_enabled": False,
        "shadowsocks_password": "",
        "shadowsocks_cipher": "aes-256-gcm",
    }
    defaults.update(overrides)
    config = MagicMock()
    for k, v in defaults.items():
        setattr(config, k, v)
    return config


class TestSocksProxyLifecycle:
    """Tests for SOCKS5 proxy service lifecycle."""

    def test_initial_state(self):
        svc = SocksProxyService(_make_config())
        assert svc.active is False
        assert svc.connections == 0

    def test_start_disabled(self):
        svc = SocksProxyService(_make_config(socks_proxy_enabled=False))
        svc.start()
        assert svc._server is None

    def test_stop_when_not_started(self, tmp_path):
        state = StateManager(tmp_path)
        svc = SocksProxyService(_make_config(), state_mgr=state)
        svc.stop()
        assert svc.active is False


class TestSocksHandshake:
    """Tests for SOCKS5 handshake and auth negotiation."""

    @pytest.mark.asyncio
    async def test_wrong_version(self):
        """Non-SOCKS5 version should close connection."""
        svc = SocksProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        # SOCKS4 version
        reader.readexactly = AsyncMock(side_effect=[
            struct.pack("!BB", 0x04, 1),  # Wrong version
        ])

        await svc._handle_client(reader, writer)
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_no_auth_method_accepted(self):
        """If auth required but client doesn't offer it, reject."""
        svc = SocksProxyService(_make_config(socks_proxy_user="admin", socks_proxy_pass="pass"))
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        reader.readexactly = AsyncMock(side_effect=[
            struct.pack("!BB", SOCKS_VERSION, 1),  # 1 method
            bytes([AUTH_NONE]),  # Only offers no-auth
        ])

        await svc._handle_client(reader, writer)
        # Should send NO ACCEPTABLE METHODS
        writer.write.assert_any_call(struct.pack("!BB", SOCKS_VERSION, AUTH_NO_ACCEPTABLE))

    @pytest.mark.asyncio
    async def test_auth_success(self):
        """Successful username/password auth."""
        svc = SocksProxyService(_make_config(socks_proxy_user="user", socks_proxy_pass="pass"))
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        user_bytes = b"user"
        pass_bytes = b"pass"

        read_sequence = [
            struct.pack("!BB", SOCKS_VERSION, 1),  # Method negotiation
            bytes([AUTH_USERPASS]),
            # Auth sub-negotiation
            bytes([0x01]),  # Sub-version
            bytes([len(user_bytes)]),
            user_bytes,
            bytes([len(pass_bytes)]),
            pass_bytes,
            # CONNECT request to 1.2.3.4:80
            struct.pack("!BBBB", SOCKS_VERSION, CMD_CONNECT, 0, ATYP_IPV4),
            bytes([1, 2, 3, 4]),
            struct.pack("!H", 80),
        ]
        reader.readexactly = AsyncMock(side_effect=read_sequence)

        target_reader = AsyncMock()
        target_writer = AsyncMock()
        target_writer.close = MagicMock()
        target_reader.read = AsyncMock(return_value=b"")
        reader.read = AsyncMock(return_value=b"")

        with patch("asyncio.open_connection", return_value=(target_reader, target_writer)):
            await svc._handle_client(reader, writer)

        # Auth success response
        writer.write.assert_any_call(b"\x01\x00")

    @pytest.mark.asyncio
    async def test_auth_failure(self):
        """Wrong credentials should reject."""
        svc = SocksProxyService(_make_config(socks_proxy_user="user", socks_proxy_pass="pass"))
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        read_sequence = [
            struct.pack("!BB", SOCKS_VERSION, 1),
            bytes([AUTH_USERPASS]),
            bytes([0x01]),  # Sub-version
            bytes([4]),  # Username length
            b"user",
            bytes([5]),  # Password length
            b"wrong",
        ]
        reader.readexactly = AsyncMock(side_effect=read_sequence)

        await svc._handle_client(reader, writer)
        # Auth failure response
        writer.write.assert_any_call(b"\x01\x01")


class TestSocksConnect:
    """Tests for SOCKS5 CONNECT command."""

    @pytest.mark.asyncio
    async def test_connect_ipv4(self):
        """CONNECT to IPv4 address."""
        svc = SocksProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        read_sequence = [
            struct.pack("!BB", SOCKS_VERSION, 1),
            bytes([AUTH_NONE]),
            struct.pack("!BBBB", SOCKS_VERSION, CMD_CONNECT, 0, ATYP_IPV4),
            bytes([93, 184, 216, 34]),  # 93.184.216.34
            struct.pack("!H", 443),
        ]
        reader.readexactly = AsyncMock(side_effect=read_sequence)

        target_reader = AsyncMock()
        target_writer = AsyncMock()
        target_writer.close = MagicMock()
        target_reader.read = AsyncMock(return_value=b"")
        reader.read = AsyncMock(return_value=b"")

        with patch("asyncio.open_connection", return_value=(target_reader, target_writer)) as mock_conn:
            await svc._handle_client(reader, writer)

        mock_conn.assert_called_once()
        assert mock_conn.call_args[0] == ("93.184.216.34", 443)

    @pytest.mark.asyncio
    async def test_connect_domain(self):
        """CONNECT to domain name."""
        svc = SocksProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        domain = b"example.com"
        read_sequence = [
            struct.pack("!BB", SOCKS_VERSION, 1),
            bytes([AUTH_NONE]),
            struct.pack("!BBBB", SOCKS_VERSION, CMD_CONNECT, 0, ATYP_DOMAIN),
            bytes([len(domain)]),
            domain,
            struct.pack("!H", 443),
        ]
        reader.readexactly = AsyncMock(side_effect=read_sequence)

        target_reader = AsyncMock()
        target_writer = AsyncMock()
        target_writer.close = MagicMock()
        target_reader.read = AsyncMock(return_value=b"")
        reader.read = AsyncMock(return_value=b"")

        with patch("asyncio.open_connection", return_value=(target_reader, target_writer)) as mock_conn:
            await svc._handle_client(reader, writer)

        mock_conn.assert_called_once()
        assert mock_conn.call_args[0] == ("example.com", 443)

    @pytest.mark.asyncio
    async def test_connect_ipv6(self):
        """CONNECT to IPv6 address."""
        svc = SocksProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        # ::1 as 16 bytes
        ipv6_bytes = b"\x00" * 15 + b"\x01"
        read_sequence = [
            struct.pack("!BB", SOCKS_VERSION, 1),
            bytes([AUTH_NONE]),
            struct.pack("!BBBB", SOCKS_VERSION, CMD_CONNECT, 0, ATYP_IPV6),
            ipv6_bytes,
            struct.pack("!H", 8080),
        ]
        reader.readexactly = AsyncMock(side_effect=read_sequence)

        target_reader = AsyncMock()
        target_writer = AsyncMock()
        target_writer.close = MagicMock()
        target_reader.read = AsyncMock(return_value=b"")
        reader.read = AsyncMock(return_value=b"")

        with patch("asyncio.open_connection", return_value=(target_reader, target_writer)) as mock_conn:
            await svc._handle_client(reader, writer)

        mock_conn.assert_called_once()
        assert mock_conn.call_args[0][1] == 8080

    @pytest.mark.asyncio
    async def test_connect_refused(self):
        """Unreachable target should get connection refused reply."""
        svc = SocksProxyService(_make_config())
        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        read_sequence = [
            struct.pack("!BB", SOCKS_VERSION, 1),
            bytes([AUTH_NONE]),
            struct.pack("!BBBB", SOCKS_VERSION, CMD_CONNECT, 0, ATYP_IPV4),
            bytes([127, 0, 0, 1]),
            struct.pack("!H", 1),
        ]
        reader.readexactly = AsyncMock(side_effect=read_sequence)

        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
            await svc._handle_client(reader, writer)

        # Check for connection refused reply (REP=0x05)
        calls = [c[0][0] for c in writer.write.call_args_list]
        # Last write should be the reply with REP_CONNECTION_REFUSED
        found = False
        for data in calls:
            if len(data) >= 2 and data[0] == SOCKS_VERSION and data[1] == REP_CONNECTION_REFUSED:
                found = True
                break
        assert found, f"Expected connection refused reply, got: {calls}"


class TestSocksAddressParsing:
    """Test address type parsing logic."""

    @pytest.mark.asyncio
    async def test_read_ipv4(self):
        svc = SocksProxyService(_make_config())
        reader = AsyncMock()
        reader.readexactly = AsyncMock(side_effect=[
            bytes([10, 0, 0, 1]),
            struct.pack("!H", 8080),
        ])
        host, port = await svc._read_address(reader, ATYP_IPV4)
        assert host == "10.0.0.1"
        assert port == 8080

    @pytest.mark.asyncio
    async def test_read_domain(self):
        svc = SocksProxyService(_make_config())
        domain = b"test.example.com"
        reader = AsyncMock()
        reader.readexactly = AsyncMock(side_effect=[
            bytes([len(domain)]),
            domain,
            struct.pack("!H", 443),
        ])
        host, port = await svc._read_address(reader, ATYP_DOMAIN)
        assert host == "test.example.com"
        assert port == 443

    @pytest.mark.asyncio
    async def test_unsupported_atyp(self):
        svc = SocksProxyService(_make_config())
        reader = AsyncMock()
        host, port = await svc._read_address(reader, 0xFF)
        assert host is None


class TestShadowsocksEncryption:
    """Tests for Shadowsocks AEAD encryption."""

    def test_evp_bytes_to_key(self):
        """EVP_BytesToKey should produce deterministic key."""
        key = _evp_bytes_to_key(b"password", 32)
        assert len(key) == 32
        # Same password produces same key
        assert _evp_bytes_to_key(b"password", 32) == key
        # Different password produces different key
        assert _evp_bytes_to_key(b"different", 32) != key

    def test_derive_key(self):
        """HKDF key derivation should produce correct-size key."""
        salt = b"\x00" * 32
        key = derive_key("password", salt, 32)
        assert len(key) == 32

    def test_aes_256_gcm_round_trip(self):
        """Encrypt then decrypt with AES-256-GCM should produce original data."""
        password = "test-password"
        plaintext = b"Hello, Shadowsocks!"

        enc = create_encryptor("aes-256-gcm", password)
        encrypted = enc.encrypt_chunk(plaintext)

        dec = create_decryptor("aes-256-gcm", password, enc.salt)
        # Encrypted = [encrypted_length(2+TAG)][encrypted_payload(len+TAG)]
        length_data = encrypted[:2 + TAG_SIZE]
        payload_len = dec.decrypt_length(length_data)
        assert payload_len == len(plaintext)

        payload_data = encrypted[2 + TAG_SIZE:]
        decrypted = dec.decrypt_payload(payload_data)
        assert decrypted == plaintext

    def test_chacha20_round_trip(self):
        """Encrypt then decrypt with ChaCha20-Poly1305."""
        password = "chacha-pass"
        plaintext = b"ChaCha20 test data"

        enc = create_encryptor("chacha20-ietf-poly1305", password)
        encrypted = enc.encrypt_chunk(plaintext)

        dec = create_decryptor("chacha20-ietf-poly1305", password, enc.salt)
        length_data = encrypted[:2 + TAG_SIZE]
        payload_len = dec.decrypt_length(length_data)
        assert payload_len == len(plaintext)

        payload_data = encrypted[2 + TAG_SIZE:]
        decrypted = dec.decrypt_payload(payload_data)
        assert decrypted == plaintext

    def test_multiple_chunks(self):
        """Multiple chunks should each encrypt/decrypt correctly."""
        password = "multi-chunk"
        chunks = [b"chunk one", b"chunk two", b"chunk three"]

        enc = create_encryptor("aes-256-gcm", password)
        encrypted_chunks = [enc.encrypt_chunk(c) for c in chunks]

        dec = create_decryptor("aes-256-gcm", password, enc.salt)
        for i, enc_data in enumerate(encrypted_chunks):
            length_data = enc_data[:2 + TAG_SIZE]
            payload_len = dec.decrypt_length(length_data)
            payload_data = enc_data[2 + TAG_SIZE:]
            decrypted = dec.decrypt_payload(payload_data)
            assert decrypted == chunks[i]

    def test_unsupported_cipher(self):
        """Unsupported cipher should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported cipher"):
            AEADCipher("des-56-ecb", "password")

    def test_max_payload_enforced(self):
        """Payload larger than MAX_PAYLOAD should raise."""
        enc = create_encryptor("aes-256-gcm", "password")
        with pytest.raises(ValueError, match="Payload too large"):
            enc.encrypt_chunk(b"\x00" * (MAX_PAYLOAD + 1))

    def test_different_passwords_fail(self):
        """Decrypting with wrong password should fail."""
        enc = create_encryptor("aes-256-gcm", "correct")
        encrypted = enc.encrypt_chunk(b"secret data")

        dec = create_decryptor("aes-256-gcm", "wrong", enc.salt)
        with pytest.raises(Exception):  # cryptography raises InvalidTag
            dec.decrypt_length(encrypted[:2 + TAG_SIZE])


class TestSocksSingleton:
    """Test singleton pattern."""

    def test_get_service_returns_same_instance(self):
        from api.services import socks_proxy
        socks_proxy._service = None
        config = _make_config()
        svc1 = socks_proxy.get_socks_proxy_service(config)
        svc2 = socks_proxy.get_socks_proxy_service()
        assert svc1 is svc2
        socks_proxy._service = None


# =============================================================================
# Shadowsocks server tests
# =============================================================================


def _make_ss_config(**overrides):
    defaults = {
        "shadowsocks_enabled": True,
        "shadowsocks_port": 18388,
        "shadowsocks_password": "test-password",
        "shadowsocks_cipher": "aes-256-gcm",
    }
    defaults.update(overrides)
    config = MagicMock()
    for k, v in defaults.items():
        setattr(config, k, v)
    return config


class TestShadowsocksParseAddress:
    """Tests for Shadowsocks target address parsing."""

    def test_parse_ipv4(self):
        data = bytes([SS_ATYP_IPV4, 93, 184, 216, 34]) + struct.pack("!H", 443)
        host, port, consumed = _parse_address(data)
        assert host == "93.184.216.34"
        assert port == 443
        assert consumed == 7

    def test_parse_domain(self):
        domain = b"example.com"
        data = bytes([SS_ATYP_DOMAIN, len(domain)]) + domain + struct.pack("!H", 80)
        host, port, consumed = _parse_address(data)
        assert host == "example.com"
        assert port == 80
        assert consumed == 4 + len(domain)

    def test_parse_ipv6(self):
        ipv6_bytes = b"\x00" * 15 + b"\x01"
        data = bytes([SS_ATYP_IPV6]) + ipv6_bytes + struct.pack("!H", 8080)
        host, port, consumed = _parse_address(data)
        assert port == 8080
        assert consumed == 19

    def test_parse_unsupported_atyp(self):
        with pytest.raises(ValueError, match="Unsupported address type"):
            _parse_address(bytes([0xFF, 0, 0, 0]))

    def test_parse_with_trailing_data(self):
        """Extra data after address should be reported via consumed count."""
        data = bytes([SS_ATYP_IPV4, 10, 0, 0, 1]) + struct.pack("!H", 80) + b"extra"
        host, port, consumed = _parse_address(data)
        assert host == "10.0.0.1"
        assert port == 80
        assert consumed == 7
        assert data[consumed:] == b"extra"


class TestShadowsocksServiceLifecycle:
    """Tests for Shadowsocks service lifecycle."""

    def test_initial_state(self):
        svc = ShadowsocksService(_make_ss_config())
        assert svc.active is False
        assert svc.connections == 0

    def test_start_disabled(self):
        svc = ShadowsocksService(_make_ss_config(shadowsocks_enabled=False))
        svc.start()
        assert svc._server is None

    def test_start_no_password(self):
        svc = ShadowsocksService(_make_ss_config(shadowsocks_password=""))
        svc.start()
        assert svc._server is None

    def test_stop_when_not_started(self, tmp_path):
        state = StateManager(tmp_path)
        svc = ShadowsocksService(_make_ss_config(), state_mgr=state)
        svc.stop()
        assert svc.active is False


class TestShadowsocksConnection:
    """Tests for Shadowsocks connection handling."""

    @pytest.mark.asyncio
    async def test_full_connection_flow(self):
        """Test complete: salt → address → connect → relay."""
        config = _make_ss_config()
        svc = ShadowsocksService(config)
        cipher_name = config.shadowsocks_cipher
        password = config.shadowsocks_password
        key_size = CIPHERS[cipher_name]["key_size"]

        # Build the client-side encrypted payload
        encryptor = create_encryptor(cipher_name, password)
        # Target: 93.184.216.34:443
        address_payload = bytes([SS_ATYP_IPV4, 93, 184, 216, 34]) + struct.pack("!H", 443)
        encrypted_address = encryptor.encrypt_chunk(address_payload)

        # The data the "client" sends: salt + encrypted address chunk
        client_data = encryptor.salt + encrypted_address

        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        # Set up reader to return: salt, then encrypted length, then encrypted payload
        # Then EOF on the relay
        read_pos = 0
        read_data = client_data

        async def mock_readexactly(n):
            nonlocal read_pos
            if read_pos >= len(read_data):
                raise asyncio.IncompleteReadError(b"", n)
            result = read_data[read_pos:read_pos + n]
            read_pos += n
            return result

        reader.readexactly = mock_readexactly

        target_reader = AsyncMock()
        target_writer = AsyncMock()
        target_writer.close = MagicMock()
        target_writer.write = MagicMock()
        target_writer.drain = AsyncMock()
        target_reader.read = AsyncMock(return_value=b"")
        reader.read = AsyncMock(return_value=b"")

        with patch("asyncio.open_connection", return_value=(target_reader, target_writer)) as mock_conn:
            await svc._handle_client(reader, writer)

        # Verify connected to the right target
        mock_conn.assert_called_once()
        assert mock_conn.call_args[0] == ("93.184.216.34", 443)

        # Verify server sent its salt back (key_size bytes)
        first_write = writer.write.call_args_list[0][0][0]
        assert len(first_write) == key_size

    @pytest.mark.asyncio
    async def test_domain_address(self):
        """Test connection to domain name target."""
        config = _make_ss_config()
        svc = ShadowsocksService(config)
        cipher_name = config.shadowsocks_cipher
        password = config.shadowsocks_password
        key_size = CIPHERS[cipher_name]["key_size"]

        encryptor = create_encryptor(cipher_name, password)
        domain = b"example.com"
        address_payload = bytes([SS_ATYP_DOMAIN, len(domain)]) + domain + struct.pack("!H", 80)
        encrypted_address = encryptor.encrypt_chunk(address_payload)

        client_data = encryptor.salt + encrypted_address
        read_pos = 0

        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        async def mock_readexactly(n):
            nonlocal read_pos
            if read_pos >= len(client_data):
                raise asyncio.IncompleteReadError(b"", n)
            result = client_data[read_pos:read_pos + n]
            read_pos += n
            return result

        reader.readexactly = mock_readexactly

        target_reader = AsyncMock()
        target_writer = AsyncMock()
        target_writer.close = MagicMock()
        target_writer.write = MagicMock()
        target_writer.drain = AsyncMock()
        target_reader.read = AsyncMock(return_value=b"")
        reader.read = AsyncMock(return_value=b"")

        with patch("asyncio.open_connection", return_value=(target_reader, target_writer)) as mock_conn:
            await svc._handle_client(reader, writer)

        mock_conn.assert_called_once()
        assert mock_conn.call_args[0] == ("example.com", 80)

    @pytest.mark.asyncio
    async def test_connection_refused(self):
        """Connection failure should be handled gracefully."""
        config = _make_ss_config()
        svc = ShadowsocksService(config)
        cipher_name = config.shadowsocks_cipher
        password = config.shadowsocks_password

        encryptor = create_encryptor(cipher_name, password)
        address_payload = bytes([SS_ATYP_IPV4, 127, 0, 0, 1]) + struct.pack("!H", 1)
        encrypted_address = encryptor.encrypt_chunk(address_payload)
        client_data = encryptor.salt + encrypted_address
        read_pos = 0

        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        async def mock_readexactly(n):
            nonlocal read_pos
            if read_pos >= len(client_data):
                raise asyncio.IncompleteReadError(b"", n)
            result = client_data[read_pos:read_pos + n]
            read_pos += n
            return result

        reader.readexactly = mock_readexactly

        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
            await svc._handle_client(reader, writer)

        # Should not crash, connection count returns to 0
        assert svc.connections == 0

    @pytest.mark.asyncio
    async def test_invalid_salt_handled(self):
        """Truncated salt should be handled gracefully."""
        config = _make_ss_config()
        svc = ShadowsocksService(config)

        reader = AsyncMock()
        writer = AsyncMock()
        writer.close = MagicMock()

        # Send truncated data — EOF before full salt
        reader.readexactly = AsyncMock(
            side_effect=asyncio.IncompleteReadError(b"\x00" * 5, 32)
        )

        await svc._handle_client(reader, writer)
        assert svc.connections == 0


class TestShadowsocksConfigWiring:
    """Test Shadowsocks config/settings wiring."""

    def test_shadowsocks_port_in_configurable_fields(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert "shadowsocks_port" in CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["shadowsocks_port"]["env"] == "SHADOWSOCKS_PORT"

    def test_shadowsocks_enabled_in_configurable_fields(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert "shadowsocks_enabled" in CONFIGURABLE_FIELDS

    def test_shadowsocks_password_is_secret(self):
        from api.services.settings import CONFIGURABLE_FIELDS
        assert CONFIGURABLE_FIELDS["shadowsocks_password"]["secret"] is True

    def test_shadowsocks_port_default(self):
        from api.constants import SHADOWSOCKS_PORT
        assert SHADOWSOCKS_PORT == 8388


class TestShadowsocksSingleton:
    """Test singleton pattern."""

    def test_get_service_returns_same_instance(self):
        from api.services import shadowsocks
        shadowsocks._service = None
        config = _make_ss_config()
        svc1 = shadowsocks.get_shadowsocks_service(config)
        svc2 = shadowsocks.get_shadowsocks_service()
        assert svc1 is svc2
        shadowsocks._service = None
