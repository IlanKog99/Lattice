"""Load and persist the grid to the opaque on-disk store.

The store file lives next to the project (one directory above this package)
and is written through :mod:`lattice.codec`, so it never contains readable
text. Saves are atomic (write temp, then replace) so a crash mid-write can't
corrupt the existing file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import codec
from .models import Grid

# The store sits beside the launcher, in the project root.
DATA_FILE = Path(__file__).resolve().parent.parent / "grid.dat"


def load() -> Grid:
    """Return the stored grid, or an empty grid if there is nothing yet."""
    if not DATA_FILE.exists():
        return Grid()
    text = codec.unpack(DATA_FILE.read_text(encoding="ascii"))
    return Grid.from_dict(json.loads(text))


def save(grid: Grid) -> None:
    """Persist the grid atomically through the codec."""
    grid.normalise()
    blob = codec.pack(json.dumps(grid.to_dict(), ensure_ascii=False))
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(blob, encoding="ascii")
    os.replace(tmp, DATA_FILE)
