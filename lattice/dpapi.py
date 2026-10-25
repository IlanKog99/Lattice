"""Windows DPAPI: encrypt bytes for the current Windows user.

The key never leaves Windows: a blob made here opens only for the same
Windows account (on the same PC, or wherever that profile roams). No prompt,
no password — Windows unlocks it from the logged-in session.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

ENTROPY = b"lattice-grid-v1"  # app-specific; blobs from other apps won't open
_UI_FORBIDDEN = 0x1


class DpapiError(ValueError):
    """DPAPI refused: wrong user/PC, wrong entropy, or not a DPAPI blob."""


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_args = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
_crypt32.CryptProtectData.argtypes = _args
_crypt32.CryptProtectData.restype = wintypes.BOOL
_crypt32.CryptUnprotectData.argtypes = _args
_crypt32.CryptUnprotectData.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _call(fn, data: bytes, entropy: bytes) -> bytes:
    src_buf = ctypes.create_string_buffer(data, max(len(data), 1))
    ent_buf = ctypes.create_string_buffer(entropy, max(len(entropy), 1))
    src = _Blob(len(data), ctypes.cast(src_buf, ctypes.POINTER(ctypes.c_char)))
    ent = _Blob(len(entropy), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None,
              _UI_FORBIDDEN, ctypes.byref(out)):
        raise DpapiError(f"DPAPI call failed (Windows error {ctypes.get_last_error()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect(data: bytes, entropy: bytes = ENTROPY) -> bytes:
    return _call(_crypt32.CryptProtectData, data, entropy)


def unprotect(blob: bytes, entropy: bytes = ENTROPY) -> bytes:
    return _call(_crypt32.CryptUnprotectData, blob, entropy)
