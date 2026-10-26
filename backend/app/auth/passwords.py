"""Password hashing (Phase 1a): scrypt from the standard library, salted, constant-time compared.

Stored as `scrypt$n$r$p$salt_hex$hash_hex`, so the cost can be raised later without losing hashes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1
MIN_LENGTH = 12


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(hash_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


def weak_reason(password: str) -> str:
    """Why a new password is refused, or "" when it is acceptable."""
    if len(password) < MIN_LENGTH:
        return f"at least {MIN_LENGTH} characters"
    if (
        password.lower() == password
        or password.upper() == password
        or not any(c.isdigit() for c in password)
    ):
        return "upper- and lower-case letters and a digit"
    return ""
