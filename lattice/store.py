"""Load and persist the grid to the opaque on-disk store.

The store file lives next to the project (one directory above this package)
and is written through :mod:`lattice.codec`, sealed with Windows DPAPI for the
current user. An older unsealed store is re-saved sealed the first time it is
loaded. Saves are verified and atomic (write temp, then replace) so a crash
mid-write can't corrupt the existing file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import codec, dpapi
from .models import Grid

# The store sits beside the launcher, in the project root.
DATA_FILE = Path(__file__).resolve().parent.parent / "grid.dat"


class ForeignStoreError(ValueError):
    """The store is sealed for another Windows user or PC."""


def load() -> Grid:
    """Return the stored grid, or an empty grid if there is nothing yet."""
    if not DATA_FILE.exists():
        return Grid()
    blob = DATA_FILE.read_text(encoding="ascii")
    try:
        text = codec.open_blob(blob)
    except dpapi.DpapiError as exc:
        raise ForeignStoreError(
            "This grid belongs to another Windows user or PC — "
            "/export it there, then /import it here"
        ) from exc
    try:
        grid = Grid.from_dict(json.loads(text))
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError("unreadable data file") from exc
    if codec.is_legacy(blob):
        try:
            save(grid)  # one-time silent upgrade to the sealed form
        except (OSError, ValueError):
            pass  # locked file or seal/verify failure: still usable, upgrade retried next load
    return grid


def save(grid: Grid) -> None:
    """Persist the grid sealed, verified, and atomically."""
    grid.normalise()
    text = json.dumps(grid.to_dict(), ensure_ascii=False)
    blob = codec.seal(text)
    if codec.open_blob(blob) != text:
        raise ValueError("sealed store failed verification")
    atomic_write(DATA_FILE, blob)


def atomic_write(path: Path, text: str) -> None:
    """Write ascii text to a temp file beside path, then swap it in."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="ascii")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
