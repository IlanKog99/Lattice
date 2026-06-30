"""Reversible byte mangling for the on-disk store.

This is deliberately *not* cryptography. The goal is only that the data file
is opaque to a casual human who opens it in a text editor: it should not look
like anything meaningful and the contents should never be greppable. The
transform is fully reversible and happens entirely in memory on load.

Pipeline:  text -> utf-8 -> zlib deflate -> rolling XOR -> base85 -> ascii
"""

from __future__ import annotations

import base64
import zlib

# Rolling mask. Changing this invalidates existing data files.
_MASK = bytes(
    (0x5B, 0xA7, 0x3C, 0xE1, 0x09, 0xF4, 0x82, 0x6D,
     0x1A, 0xCB, 0x70, 0x9E, 0x3F, 0xD2, 0x64, 0xB8)
)
_TAG = b"LZ1"  # format marker so we can detect/upgrade later


def _roll(raw: bytes) -> bytes:
    m, n = _MASK, len(_MASK)
    return bytes(b ^ m[i % n] for i, b in enumerate(raw))


def pack(text: str) -> str:
    """Turn plain text into an opaque ascii blob."""
    blob = zlib.compress(text.encode("utf-8"), 9)
    blob = _roll(_TAG + blob)
    return base64.b85encode(blob).decode("ascii")


def unpack(blob: str) -> str:
    """Reverse :func:`pack`. Raises ValueError if the blob is unusable."""
    try:
        raw = _roll(base64.b85decode(blob.strip().encode("ascii")))
        if not raw.startswith(_TAG):
            raise ValueError("bad marker")
        return zlib.decompress(raw[len(_TAG):]).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - normalise to one error type
        raise ValueError("unreadable data file") from exc
