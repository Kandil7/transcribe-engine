"""Seal webhook signing secrets with AES-256-GCM before they are stored (S20, D-082).

Format: a version byte, a 12-byte random nonce, then the ciphertext with its
16-byte tag. The version byte is authenticated too. The key comes from the environment
(TE_SECRET_KEY, base64 of 32 bytes) and is never stored with the data.
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = ["open_sealed", "parse_key", "seal"]

_VERSION = b"\x01"
_NONCE_BYTES = 12
_TAG_BYTES = 16
_KEY_BYTES = 32


def parse_key(text: str) -> bytes:
    """Decode the base64 key from the environment. Anything else is refused."""
    try:
        raw = base64.b64decode(text, validate=True)
    except ValueError as exc:
        raise ValueError("secret key must be base64") from exc
    if len(raw) != _KEY_BYTES:
        raise ValueError("secret key must decode to 32 bytes")
    return raw


def seal(key: bytes, plaintext: bytes) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    return _VERSION + nonce + AESGCM(key).encrypt(nonce, plaintext, _VERSION)


def open_sealed(key: bytes, sealed: bytes) -> bytes:
    if len(sealed) < 1 + _NONCE_BYTES + _TAG_BYTES or sealed[:1] != _VERSION:
        raise ValueError("cannot be opened: unknown format")
    nonce = sealed[1 : 1 + _NONCE_BYTES]
    try:
        return AESGCM(key).decrypt(nonce, sealed[1 + _NONCE_BYTES :], _VERSION)
    except InvalidTag as exc:
        raise ValueError("cannot be opened with this key") from exc
