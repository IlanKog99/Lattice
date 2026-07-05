"""In-memory data model for the grid.

A grid is a list of columns and a list of rows. The first column is the
"label" column (the left-hand identifier); every other column holds free-form
cell values. Rows and columns are never deleted by the UI — they are only
flagged hidden, so nothing is ever truly lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Column:
    name: str
    hidden: bool = False


@dataclass
class Row:
    cells: list[Any] = field(default_factory=list)
    hidden: bool = False


def is_formula(value: Any) -> bool:
    """True if `value` is a formula spec ({prefix, suffix, formula}) rather than a plain string."""
    return isinstance(value, dict)


def formula_preview(spec: dict) -> str:
    return f"{spec.get('prefix', '')}INPT{spec.get('suffix', '')}"


def cell_text(value: Any) -> str:
    """Render any cell value (plain string or formula spec) as displayable text."""
    return formula_preview(value) if is_formula(value) else value


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
