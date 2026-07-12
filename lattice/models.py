"""In-memory data model for the grid.

A grid is a list of columns and a list of rows. The first column is the
"label" column (the left-hand identifier); every other column holds free-form
cell values. Rows and columns are never deleted by the UI — they are only
flagged hidden, so nothing is ever truly lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import totp


@dataclass
class Column:
    name: str
    hidden: bool = False


@dataclass
class Row:
    cells: list[Any] = field(default_factory=list)
    hidden: bool = False


def is_totp(value: Any) -> bool:
    """True if `value` is a TOTP secret spec ({kind: "totp", secret})."""
    return isinstance(value, dict) and value.get("kind") == "totp"


def is_formula(value: Any) -> bool:
    """True if `value` is a formula spec — any dict that isn't a TOTP spec.

    Existing formula specs have no "kind" key (they predate TOTP cells), so
    this stays the fallback rather than requiring a "kind": "formula" tag.
    """
    return isinstance(value, dict) and not is_totp(value)


def formula_preview(spec: dict) -> str:
    return f"{spec.get('prefix', '')}INPT{spec.get('suffix', '')}"


def cell_text(value: Any) -> str:
    """Render any cell value (string, formula spec, or TOTP spec) as text.

    A TOTP cell's raw secret is never rendered anywhere, even revealed --
    only the current rotating code, same as what copying it produces.
    """
    if is_totp(value):
        try:
            return totp.generate(value.get("secret", ""))
        except Exception:  # noqa: BLE001 - corrupt/invalid stored secret
            return "?" * totp.DIGITS
    if is_formula(value):
        return formula_preview(value)
    return value


@dataclass
class Grid:
    columns: list[Column] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)

    # --- serialisation -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": [{"name": c.name, "hidden": c.hidden} for c in self.columns],
            "rows": [{"cells": list(r.cells), "hidden": r.hidden} for r in self.rows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Grid":
        cols = [Column(c["name"], c.get("hidden", False)) for c in data.get("columns", [])]
        rows = [Row(list(r["cells"]), r.get("hidden", False)) for r in data.get("rows", [])]
        grid = cls(cols, rows)
        grid.normalise()
        return grid

    # --- integrity -----------------------------------------------------
    def normalise(self) -> None:
        """Make every row exactly as wide as the column list."""
        width = len(self.columns)
        for r in self.rows:
            if len(r.cells) < width:
                r.cells.extend([""] * (width - len(r.cells)))
            elif len(r.cells) > width:
                del r.cells[width:]

    # --- views (visible only) -----------------------------------------
    def visible_col_indexes(self) -> list[int]:
        return [i for i, c in enumerate(self.columns) if not c.hidden]

    def visible_row_indexes(self) -> list[int]:
        return [i for i, r in enumerate(self.rows) if not r.hidden]

    # --- mutations -----------------------------------------------------
    def set_cell(self, row_idx: int, col_idx: int, value: Any) -> None:
        self.rows[row_idx].cells[col_idx] = value

    def add_row(self, cells: list[Any]) -> None:
        row = Row(list(cells))
        self.rows.append(row)
        self.normalise()

    def add_column(self, name: str, values: list[Any]) -> None:
        self.columns.append(Column(name))
        for r, v in zip(self.rows, values):
            r.cells.append(v)
        self.normalise()
