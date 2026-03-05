"""Shadowsocks AEAD server — encrypts TCP streams through the VPN tunnel.

Supports:
- aes-256-gcm (default)
- chacha20-ietf-poly1305

Protocol (AEAD):
  Client → Server: [salt][encrypted chunks...]
  Server → Client: [salt][encrypted chunks...]
  First decrypted chunk from client = [ATYP][address][port] (target)

Uses the standard Shadowsocks key derivation (HKDF-SHA1) and AEAD
framing: [encrypted_length][length_tag][encrypted_payload][payload_tag].

Lifecycle: started/stopped in FastAPI lifespan, same as HTTP/SOCKS5 proxies.
"""

import asyncio
import hashlib
import logging
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

# AEAD tag size is 16 bytes for both AES-GCM and ChaCha20-Poly1305
TAG_SIZE = 16
NONCE_SIZE = 12  # 96 bits for both ciphers
MAX_PAYLOAD = 0x3FFF  # 16383 bytes per chunk

CIPHERS = {
    "aes-256-gcm": {"key_size": 32, "cls": AESGCM},
    "chacha20-ietf-poly1305": {"key_size": 32, "cls": ChaCha20Poly1305},
}


def derive_key(password: str, salt: bytes, key_size: int = 32) -> bytes:
    """Derive encryption key using HKDF-SHA1 (Shadowsocks standard)."""
    # First derive a master key from password using EVP_BytesToKey (OpenSSL compat)
    master_key = _evp_bytes_to_key(password.encode("utf-8"), key_size)
    # Then derive session key with HKDF
    hkdf = HKDF(
        algorithm=hashes.SHA1(),
        length=key_size,
        salt=salt,
        info=b"ss-subkey",
    )
    return hkdf.derive(master_key)


def _evp_bytes_to_key(password: bytes, key_size: int) -> bytes:
    """OpenSSL EVP_BytesToKey with MD5 — Shadowsocks master key derivation."""
    m: list[bytes] = []
    while len(b"".join(m)) < key_size:
        data = password if not m else m[-1] + password
        m.append(hashlib.md5(data, usedforsecurity=False).digest())  # noqa: S324 — protocol spec
    return b"".join(m)[:key_size]


class AEADCipher:
    """Stateful AEAD cipher for Shadowsocks stream encryption/decryption."""

    def __init__(self, cipher_name: str, password: str, salt: bytes | None = None):
        if cipher_name not in CIPHERS:
            raise ValueError(f"Unsupported cipher: {cipher_name}")

        spec = CIPHERS[cipher_name]
        self.key_size = spec["key_size"]

        # Generate or use provided salt
        self.salt = salt or os.urandom(self.key_size)

        # Derive session key
        key = derive_key(password, self.salt, self.key_size)
        self._cipher = spec["cls"](key)

        # Nonce counter (incremented after each encrypt/decrypt)
        self._nonce_counter = 0

    def _next_nonce(self) -> bytes:
        """Generate the next nonce (little-endian counter)."""
        nonce = self._nonce_counter.to_bytes(NONCE_SIZE, "little")
        self._nonce_counter += 1
        return nonce

    def encrypt_chunk(self, plaintext: bytes) -> bytes:
        """Encrypt a single chunk: [encrypted_length][tag][encrypted_payload][tag].

        Returns salt + encrypted data on first call, encrypted data on subsequent calls.
        """
        if len(plaintext) > MAX_PAYLOAD:
            raise ValueError(f"Payload too large: {len(plaintext)} > {MAX_PAYLOAD}")

        # Encrypt length (2 bytes, big-endian)
        length_bytes = struct.pack("!H", len(plaintext))
        encrypted_length = self._cipher.encrypt(self._next_nonce(), length_bytes, None)

        # Encrypt payload
        encrypted_payload = self._cipher.encrypt(self._next_nonce(), plaintext, None)

        return encrypted_length + encrypted_payload

    def decrypt_length(self, data: bytes) -> int:
        """Decrypt the 2-byte length field. Returns payload length."""
        # data should be 2 + TAG_SIZE bytes
        nonce = self._next_nonce()
        length_bytes = self._cipher.decrypt(nonce, data, None)
        return struct.unpack("!H", length_bytes)[0]

    def decrypt_payload(self, data: bytes) -> bytes:
        """Decrypt a payload chunk. data should be payload_len + TAG_SIZE bytes."""
        nonce = self._next_nonce()
        return self._cipher.decrypt(nonce, data, None)


def create_encryptor(cipher_name: str, password: str) -> AEADCipher:
    """Create a new encryptor (generates random salt)."""
    return AEADCipher(cipher_name, password)


def create_decryptor(cipher_name: str, password: str, salt: bytes) -> AEADCipher:
    """Create a decryptor with the given salt from the remote side."""
    return AEADCipher(cipher_name, password, salt=salt)


# =============================================================================
# Address type constants (same as SOCKS5)
# =============================================================================

ATYP_IPV4 = 0x01
ATYP_DOMAIN = 0x03
ATYP_IPV6 = 0x04


# =============================================================================
# Shadowsocks TCP server
# =============================================================================


async def _read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    """Read exactly n bytes, raise on EOF."""
    data = await asyncio.wait_for(reader.readexactly(n), timeout=30)
    return data


async def _decrypt_chunk(reader: asyncio.StreamReader, cipher: AEADCipher) -> bytes:
    """Read and decrypt one AEAD chunk from the stream."""
    # Read encrypted length: 2 bytes + TAG_SIZE
    enc_len = await _read_exact(reader, 2 + TAG_SIZE)
    payload_len = cipher.decrypt_length(enc_len)

    # Read encrypted payload: payload_len + TAG_SIZE
    enc_payload = await _read_exact(reader, payload_len + TAG_SIZE)
    return cipher.decrypt_payload(enc_payload)


def _parse_address(data: bytes) -> tuple[str, int, int]:
    """Parse Shadowsocks target address from decrypted payload.

    Returns (host, port, bytes_consumed).
    """
    atyp = data[0]
    if atyp == ATYP_IPV4:
        host = ".".join(str(b) for b in data[1:5])
        port = struct.unpack("!H", data[5:7])[0]
        return host, port, 7
    elif atyp == ATYP_DOMAIN:
        domain_len = data[1]
        host = data[2:2 + domain_len].decode("utf-8")
        port = struct.unpack("!H", data[2 + domain_len:4 + domain_len])[0]
        return host, port, 4 + domain_len
    elif atyp == ATYP_IPV6:
        parts = []
        for i in range(0, 16, 2):
            parts.append(f"{data[1 + i]:02x}{data[2 + i]:02x}")
        host = ":".join(parts)
        port = struct.unpack("!H", data[17:19])[0]
        return host, port, 19
    else:
        raise ValueError(f"Unsupported address type: {atyp}")


class ShadowsocksService:
    """Shadowsocks AEAD TCP proxy server."""

    def __init__(self, config, state_mgr=None):
        from api.constants import ServiceState
        self.config = config
        self._ServiceState = ServiceState
        if state_mgr is None:
            from api.services.state import StateManager
            state_mgr = StateManager()
        self._state = state_mgr
        self._server: asyncio.Server | None = None
        self._connections = 0

    @property
    def active(self) -> bool:
        return self._server is not None and self._server.is_serving()

    @property
    def connections(self) -> int:
        return self._connections

    def start(self) -> None:
        """Start the Shadowsocks server if enabled and password is set."""
        if not self.config.shadowsocks_enabled:
            return
        if not self.config.shadowsocks_password:
            logger.warning("Shadowsocks enabled but no password set — not starting")
            return
        asyncio.create_task(self._start())

    async def _start(self) -> None:
        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                "0.0.0.0",
                self.config.shadowsocks_port,
            )
            self._state.write("shadowsocks_state", self._ServiceState.RUNNING)
            logger.info(f"Shadowsocks listening on 0.0.0.0:{self.config.shadowsocks_port}")
        except Exception as e:
            logger.error(f"Shadowsocks failed to start: {e}")
            self._state.write("shadowsocks_state", self._ServiceState.ERROR)

    def stop(self) -> None:
        """Stop the Shadowsocks server."""
        if self._server:
            self._server.close()
            self._server = None
        self._state.write("shadowsocks_state", self._ServiceState.DISABLED)
        logger.info("Shadowsocks stopped")

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        """Handle a single Shadowsocks connection."""
        self._connections += 1
        target_writer = None
        try:
            cipher_name = self.config.shadowsocks_cipher
            password = self.config.shadowsocks_password
            key_size = CIPHERS[cipher_name]["key_size"]

            # Step 1: Read client salt
            client_salt = await _read_exact(reader, key_size)
            decryptor = create_decryptor(cipher_name, password, client_salt)

            # Step 2: Decrypt first chunk — contains target address
            first_payload = await _decrypt_chunk(reader, decryptor)
            host, port, consumed = _parse_address(first_payload)
            initial_data = first_payload[consumed:]  # any extra data after address

            # Step 3: Connect to target
            target_reader, target_writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=30,
            )

            # Step 4: Create encryptor for server→client, send salt
            encryptor = create_encryptor(cipher_name, password)
            writer.write(encryptor.salt)
            await writer.drain()

            # Step 5: Send initial data to target (if any came with the address)
            if initial_data:
                target_writer.write(initial_data)
                await target_writer.drain()

            # Step 6: Relay bidirectionally
            await self._relay(reader, writer, target_reader, target_writer,
                              decryptor, encryptor)

        except (asyncio.TimeoutError, asyncio.IncompleteReadError,
                ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            logger.debug(f"Shadowsocks connection error: {e}")
        finally:
            self._connections -= 1
            for w in (writer, target_writer):
                if w is not None:
                    try:
                        w.close()
                    except Exception:
                        pass

    async def _relay(self, client_reader: asyncio.StreamReader,
                     client_writer: asyncio.StreamWriter,
                     target_reader: asyncio.StreamReader,
                     target_writer: asyncio.StreamWriter,
                     decryptor: AEADCipher,
                     encryptor: AEADCipher) -> None:
        """Relay bytes: decrypt client→target, encrypt target→client."""

        async def _client_to_target():
            """Decrypt chunks from client, forward plaintext to target."""
            try:
                while True:
                    plaintext = await _decrypt_chunk(client_reader, decryptor)
                    if not plaintext:
                        break
                    target_writer.write(plaintext)
                    await target_writer.drain()
            except (asyncio.TimeoutError, asyncio.IncompleteReadError,
                    ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                pass
            finally:
                try:
                    target_writer.close()
                except Exception:
                    pass

        async def _target_to_client():
            """Read plaintext from target, encrypt and send to client."""
            try:
                while True:
                    data = await target_reader.read(MAX_PAYLOAD)
                    if not data:
                        break
                    encrypted = encryptor.encrypt_chunk(data)
                    client_writer.write(encrypted)
                    await client_writer.drain()
            except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                pass
            finally:
                try:
                    client_writer.close()
                except Exception:
                    pass

        task1 = asyncio.create_task(_client_to_target())
        task2 = asyncio.create_task(_target_to_client())

        done, pending = await asyncio.wait(
            {task1, task2}, return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()


# Singleton
_service: ShadowsocksService | None = None


def get_shadowsocks_service(config=None, state_mgr=None) -> ShadowsocksService:
    global _service
    if _service is None:
        if config is None:
            from api.config import load_config
            config = load_config()
        _service = ShadowsocksService(config, state_mgr)
    return _service
