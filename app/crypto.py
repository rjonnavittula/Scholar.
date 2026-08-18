"""At-rest encryption for secrets stored on the Settings row (Canvas token, ICS URL).

Opt-in via HIVE_SECRET_KEY. Unset means encrypt/decrypt are no-ops and values
stay plaintext, exactly as before this module existed — nothing breaks for an
install that doesn't set the key. Ciphertext carries a "fernet:" prefix so a
value written before encryption was enabled (or before this feature existed)
keeps working: decrypt() falls back to returning it unchanged.
"""
from __future__ import annotations

import os

_PREFIX = "fernet:"


def encryption_configured() -> bool:
    return bool(os.getenv("HIVE_SECRET_KEY"))


def _fernet():
    from cryptography.fernet import Fernet

    key = os.getenv("HIVE_SECRET_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        return None


def encrypt_secret(raw: str) -> str:
    if not raw or raw.startswith(_PREFIX):
        return raw
    fernet = _fernet()
    if not fernet:
        return raw
    return _PREFIX + fernet.encrypt(raw.encode()).decode()


def decrypt_secret(value: str) -> str:
    if not value or not value.startswith(_PREFIX):
        return value
    fernet = _fernet()
    if not fernet:
        return value
    try:
        return fernet.decrypt(value[len(_PREFIX):].encode()).decode()
    except Exception:
        return value
