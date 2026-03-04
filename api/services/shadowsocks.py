"""Shadowsocks AEAD encryption — wraps SOCKS5 TCP streams.

Supports:
- aes-256-gcm (default)
- chacha20-ietf-poly1305

Uses the standard Shadowsocks key derivation (HKDF-SHA1) and AEAD
framing: [encrypted_length][length_tag][encrypted_payload][payload_tag].
"""

import hashlib
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

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
    m = []
    while len(b"".join(m)) < key_size:
        data = password if not m else m[-1] + password
        m.append(hashlib.md5(data).digest())
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
