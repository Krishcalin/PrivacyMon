"""Credential vault (AES-256-GCM envelope encryption)."""
from __future__ import annotations

import pytest

from platform_db import crypto

KEY = crypto.new_master_key()  # a valid base64 32-byte key


def test_round_trip():
    ref = crypto.encrypt_secret("s3cr3t-readonly", key=KEY)
    assert ref.startswith("enc:v1:")
    assert crypto.resolve_secret(ref, key=KEY) == "s3cr3t-readonly"


def test_ciphertext_is_not_the_plaintext_and_varies():
    a = crypto.encrypt_secret("hunter2", key=KEY)
    b = crypto.encrypt_secret("hunter2", key=KEY)
    assert "hunter2" not in a and a != b  # random nonce -> different ciphertext


def test_wrong_key_fails_to_decrypt():
    ref = crypto.encrypt_secret("pw", key=KEY)
    with pytest.raises(Exception):
        crypto.resolve_secret(ref, key=crypto.new_master_key())


def test_is_encrypted():
    assert crypto.is_encrypted(crypto.encrypt_secret("x", key=KEY))
    assert not crypto.is_encrypted("secretsmanager://a/b")
    assert not crypto.is_encrypted(None)


def test_external_refs_and_garbage_are_rejected():
    with pytest.raises(NotImplementedError):
        crypto.resolve_secret("secretsmanager://a/b", key=KEY)
    with pytest.raises(ValueError):
        crypto.resolve_secret("", key=KEY)


def test_key_must_be_32_bytes():
    import base64
    with pytest.raises(ValueError):
        crypto.encrypt_secret("x", key=base64.b64encode(b"tooshort").decode())
