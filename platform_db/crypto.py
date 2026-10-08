"""Credential vault — AES-256-GCM envelope encryption for data-source secrets.

The SRS v1 default (section 7.1 / 14): a read-only target password is never stored in
clear. The API encrypts it with a 256-bit master key and stores only the ciphertext as
the data source's ``credential_ref``; the worker decrypts it transiently at scan time
to open the read-only connection. The master key comes from ``PRIVACYMON_MASTER_KEY``
(base64, 32 bytes) and never touches the database. HashiCorp Vault / CyberArk refs
(``secretsmanager://`` / ``ssm://``) are a Hardening item and raise here for now.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIX = "enc:v1:"
_NONCE_BYTES = 12
_KEY_BYTES = 32


def new_master_key() -> str:
    """Generate a fresh base64 master key (for operators / `.env`)."""
    return base64.b64encode(os.urandom(_KEY_BYTES)).decode("ascii")


def _coerce_key(raw: str | bytes) -> bytes:
    if isinstance(raw, bytes):
        key = raw
    else:
        try:
            key = base64.b64decode(raw, validate=True)
        except Exception as e:  # noqa: BLE001
            raise ValueError("PRIVACYMON_MASTER_KEY must be base64") from e
    if len(key) != _KEY_BYTES:
        raise ValueError("master key must decode to 32 bytes (AES-256)")
    return key


def _env_key() -> bytes:
    raw = os.environ.get("PRIVACYMON_MASTER_KEY")
    if not raw:
        raise RuntimeError(
            "PRIVACYMON_MASTER_KEY is not set; cannot encrypt or resolve credentials")
    return _coerce_key(raw)


def is_encrypted(ref: str | None) -> bool:
    return bool(ref) and ref.startswith(_PREFIX)


def encrypt_secret(plaintext: str, *, key: str | bytes | None = None) -> str:
    """Return ``enc:v1:<base64(nonce||ciphertext)>`` for ``plaintext``."""
    k = _coerce_key(key) if key is not None else _env_key()
    nonce = os.urandom(_NONCE_BYTES)
    ct = AESGCM(k).encrypt(nonce, plaintext.encode("utf-8"), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def resolve_secret(ref: str, *, key: str | bytes | None = None) -> str:
    """Decrypt a credential reference back to the plaintext secret."""
    if is_encrypted(ref):
        k = _coerce_key(key) if key is not None else _env_key()
        blob = base64.b64decode(ref[len(_PREFIX):])
        return AESGCM(k).decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], None).decode("utf-8")
    if ref and ref.startswith(("secretsmanager://", "ssm://")):
        raise NotImplementedError("external vault references are a Hardening item")
    raise ValueError("unrecognised or empty credential reference")
