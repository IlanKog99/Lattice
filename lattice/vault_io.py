"""Portable export/import files, for moving a grid between PCs and users.

The on-disk store is sealed to one Windows user, so it can't travel. An
export file is instead sealed with a passphrase the user chooses:

    LX1: + base85(salt[16] + nonce[12] + AES-GCM(scrypt(passphrase), zlib(json)))

Import also accepts the older unsealed store format (no passphrase).
`cryptography` is imported only here, inside the functions, so the rest of
the app runs even if it isn't installed.
"""

from __future__ import annotations

import base64
import json
import os
import zlib
from pathlib import Path

from . import codec, dpapi, store
from .models import Grid

_TAG = "LX1:"
_AAD = b"LX1"
_SALT = 16
_NONCE = 12


class VaultIOError(ValueError):
    """Export/import failed; the message is shown to the user as-is."""


def _crypto():
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as exc:
        raise VaultIOError("Run: python -m pip install -r requirements.txt") from exc
    return AESGCM, Scrypt, InvalidTag


def _key(Scrypt, passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def _read(path) -> str:
    try:
        return Path(path).read_text(encoding="ascii").strip()
    except (OSError, ValueError) as exc:  # UnicodeDecodeError, NUL in path
        raise VaultIOError(f"Can't read {path}") from exc


def needs_passphrase(path) -> bool:
    return _read(path).startswith(_TAG)


def _is_live_grid(path: Path) -> bool:
    try:
        if path.exists() and store.DATA_FILE.exists():
            return os.path.samefile(path, store.DATA_FILE)
        target = path.resolve()
        target = target.with_name(target.name.rstrip(". "))  # Windows drops trailing dots/spaces
        return os.path.normcase(target) == os.path.normcase(store.DATA_FILE.resolve())
    except OSError:
        return True  # unsure: refuse rather than risk the live grid
    except ValueError:  # NUL in path, or a name of only dots/spaces; the write fails later
        return False


def export_grid(grid: Grid, path, passphrase: str) -> None:
    if not passphrase:
        raise VaultIOError("Passphrase cannot be empty")
    AESGCM, Scrypt, _ = _crypto()
    path = Path(path)
    if ":" in path.name:  # NTFS alternate data stream, e.g. grid.dat:x
        raise VaultIOError("Choose a file name to export to")
    if _is_live_grid(path):
        raise VaultIOError("Pick a different file — that is the live grid")
    if not path.name:  # "" or a drive root
        raise VaultIOError("Choose a file name to export to")
    data = zlib.compress(json.dumps(grid.to_dict(), ensure_ascii=False).encode("utf-8"), 9)
    try:
        salt, nonce = os.urandom(_SALT), os.urandom(_NONCE)
        sealed = AESGCM(_key(Scrypt, passphrase, salt)).encrypt(nonce, data, _AAD)
        blob = _TAG + base64.b85encode(salt + nonce + sealed).decode("ascii")
        store.atomic_write(path, blob)
    except (OSError, ValueError) as exc:  # ValueError: NUL in path
        raise VaultIOError(f"Can't write {path}") from exc


def import_grid(path, passphrase: str | None = None) -> Grid:
    blob = _read(path)
    if blob.startswith(_TAG):
        if not passphrase:
            raise VaultIOError("This file needs its passphrase")
        AESGCM, Scrypt, InvalidTag = _crypto()
        try:
            raw = base64.b85decode(blob[len(_TAG):].encode("ascii"))
            salt, nonce, sealed = raw[:_SALT], raw[_SALT:_SALT + _NONCE], raw[_SALT + _NONCE:]
            data = AESGCM(_key(Scrypt, passphrase, salt)).decrypt(nonce, sealed, _AAD)
            text = zlib.decompress(data).decode("utf-8")
        except (InvalidTag, ValueError, zlib.error) as exc:
            raise VaultIOError("Wrong passphrase or damaged file") from exc
    else:
        try:
            text = codec.open_blob(blob)  # legacy export, or a same-user DP1: copy of grid.dat
        except dpapi.DpapiError as exc:  # subclass of ValueError: must come first
            raise VaultIOError("This file belongs to another Windows user or PC — export it there") from exc
        except ValueError as exc:
            raise VaultIOError("Not a Lattice file") from exc
    try:
        return Grid.from_dict(json.loads(text))
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise VaultIOError("Not a Lattice file") from exc
