"""S20 (D-082): webhook signing secrets are sealed with AES-256-GCM before the database.

Positive controls: a sealed secret opens with its key, and the stored bytes hide the secret.
Negative controls: a wrong key, a tampered byte, and a key of the wrong length are all refused.
"""

import base64
import importlib
from types import ModuleType

import pytest


def _mod() -> ModuleType:
    return importlib.import_module("transcribe_engine.infrastructure.security.secret_box")


KEY = bytes(range(32))


def test_round_trip_and_no_plaintext_in_the_sealed_bytes() -> None:
    box = _mod()
    secret = b"whsec-plain-value-0123456789"
    sealed = box.seal(KEY, secret)
    assert box.open_sealed(KEY, sealed) == secret
    assert secret not in sealed


def test_wrong_key_is_refused() -> None:
    box = _mod()
    sealed = box.seal(KEY, b"s")
    with pytest.raises(ValueError, match="cannot be opened"):
        box.open_sealed(bytes(32), sealed)


def test_tampered_bytes_are_refused() -> None:
    box = _mod()
    sealed = bytearray(box.seal(KEY, b"s"))
    sealed[-1] ^= 0x01
    with pytest.raises(ValueError, match="cannot be opened"):
        box.open_sealed(KEY, bytes(sealed))


def test_key_must_be_32_bytes_from_base64() -> None:
    box = _mod()
    assert box.parse_key(base64.b64encode(KEY).decode()) == KEY
    with pytest.raises(ValueError, match="32 bytes"):
        box.parse_key("c2hvcnQ=")
