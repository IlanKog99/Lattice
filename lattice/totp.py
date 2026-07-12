"""TOTP (RFC 6238) code generation for totp-type cells.

Stdlib only. A totp cell stores a base32 secret; the 6-digit code is
computed fresh from that secret and the current time whenever it's
copied -- the code itself is never stored, only the secret.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time

DIGITS = 6
PERIOD = 30  # seconds
_ALGO = hashlib.sha1


def normalize_secret(secret: str) -> str:
    """Upper-case, strip whitespace/hyphens, and pad a pasted base32 secret."""
    text = "".join(secret.split()).replace("-", "").upper()
    padding = (-len(text)) % 8
    return text + "=" * padding


def validate_secret(secret: str) -> bool:
    """True if `secret` decodes as base32 once normalised."""
    normalized = normalize_secret(secret)
    if not normalized:
        return False
    try:
        base64.b32decode(normalized)
        return True
    except (ValueError, TypeError):
        return False


def generate(secret: str, *, when: float | None = None) -> str:
    """The current (or `when`'s) DIGITS-digit TOTP code for `secret`."""
    key = base64.b32decode(normalize_secret(secret))
    counter = int((when if when is not None else time.time()) // PERIOD)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, _ALGO).digest()
    offset = digest[-1] & 0x0F
    chunk = digest[offset:offset + 4]
    code = (struct.unpack(">I", chunk)[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(code).zfill(DIGITS)


def demo() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert generate(secret, when=59) == "287082"
    assert validate_secret("JBSWY3DPEHPK3PXP")
    assert not validate_secret("not base32!!!")
    print("totp: ok")


if __name__ == "__main__":
    demo()
