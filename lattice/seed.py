"""One-shot importer: build the opaque store from a plain-text grid file.

Run once to migrate an existing pipe-delimited table into the encoded store::

    python -m lattice.seed path/to/plain_table.txt

The plain text is read at runtime from the path you pass; it is never baked
into this program. After seeding, the readable source file can be deleted —
the app reads only the encoded store from then on.

Expected layout (columns separated by ``||``, a dashed rule under the header,
an optional ``====`` footer)::

    Col A:        || Col B:   || Col C:   ||
    --------------||----------||----------||
    label one     || value    || value    ||
"""

from __future__ import annotations

import sys
from pathlib import Path

from .models import Column, Grid, Row
from .store import DATA_FILE, save


def _split_row(line: str) -> list[str]:
    # Collapse the fixed-width padding from the source into single spaces.
    parts = [" ".join(p.split()) for p in line.split("||")]
    # A trailing "|| " produces an empty final part; drop it.
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def parse_text(text: str) -> Grid:
    headers: list[str] = []
    rows: list[Row] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if set(line.strip()) <= {"=", " "}:  # footer rule
            continue
        if "||" not in line and set(line.strip()) <= {"-", " "}:
            continue
        fields = _split_row(line)
        # The separator rule is made of dashes once split.
        if all(set(f) <= {"-"} or f == "" for f in fields):
            continue
        if not headers:
            headers = [f.rstrip(":").strip() for f in fields]
            continue
        rows.append(Row(fields))
    grid = Grid([Column(h) for h in headers], rows)
    grid.normalise()
    return grid


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m lattice.seed <plain_table.txt>")
        return 2
    src = Path(argv[0])
    if not src.exists():
        print(f"no such file: {src}")
        return 1
    grid = parse_text(src.read_text(encoding="utf-8"))
    save(grid)
    print(
        f"Imported {len(grid.rows)} rows x {len(grid.columns)} columns "
        f"into {DATA_FILE.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
