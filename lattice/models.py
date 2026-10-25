"""In-memory data model for the grid.

A grid is a list of columns and a list of rows. The first column is the
"label" column (the left-hand identifier); every other column holds free-form
cell values. Rows and columns are never deleted by the UI — they are only
flagged hidden, so nothing is ever truly lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import code_engine, formula


@dataclass
class Column:
    name: str
    hidden: bool = False


@dataclass
class Row:
    cells: list[Any] = field(default_factory=list)
    hidden: bool = False


def is_code_cell(value: Any) -> bool:
    """True if `value` is a code-cell spec ({kind: "code", seed})."""
    return isinstance(value, dict) and value.get("kind") == "code"


def is_formula(value: Any) -> bool:
    """True if `value` is a formula spec — any dict that isn't a code-cell spec.

    Existing formula specs have no "kind" key (they predate code cells), so
    this stays the fallback rather than requiring a "kind": "formula" tag.
    """
    return isinstance(value, dict) and not is_code_cell(value)


def _upgrade_cell(value: Any) -> Any:
    """Older stores tagged code cells with a different `kind` and seed key.
    Identified by shape (a `kind` plus exactly one other key) rather than by
    the old names, so those names never need to appear in source."""
    if isinstance(value, dict) and "kind" in value and not is_code_cell(value) and len(value) == 2:
        seed = next(v for k, v in value.items() if k != "kind")
        return {"kind": "code", "seed": seed}
    return value


def formula_preview(spec: dict) -> str:
    return f"{spec.get('prefix', '')}INPT{spec.get('suffix', '')}"


def cell_text(value: Any) -> str:
    """Render any cell value (string, formula spec, or code-cell spec) as text.

    A code cell's raw seed is never rendered anywhere, even revealed --
    only the current rotating code, same as what copying it produces.
    """
    if is_code_cell(value):
        try:
            return code_engine.generate(value.get("seed", ""))
        except Exception:  # noqa: BLE001 - corrupt/invalid stored seed
            return "?" * code_engine.DIGITS
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
        if not isinstance(data, dict):
            raise ValueError("Not a Lattice file")
        cols = [Column(c["name"], c.get("hidden", False)) for c in data.get("columns", [])]
        rows = [Row(r["cells"], r.get("hidden", False)) for r in data.get("rows", [])]
        # Wrong JSON types would load fine and crash rendering later.
        if not (
            all(isinstance(c.name, str) and isinstance(c.hidden, bool) for c in cols)
            and all(
                isinstance(r.cells, list) and isinstance(r.hidden, bool)
                and all(isinstance(v, (str, dict)) for v in r.cells)
                for r in rows
            )
        ):
            raise ValueError("Not a Lattice file")
        grid = cls(cols, rows)
        grid.normalise()
        # After normalise so legacy code cells are already upgraded. A formula
        # spec needs a valid str formula (and str prefix/suffix), a code cell a
        # str seed, or copying crashes.
        if not all(
            isinstance(v.get("seed", ""), str) if is_code_cell(v) else (
                isinstance(v.get("formula"), str) and formula.validate(v["formula"])
                and all(isinstance(v.get(k, ""), str) for k in ("prefix", "suffix"))
            )
            for r in grid.rows for v in r.cells if isinstance(v, dict)
        ):
            raise ValueError("Not a Lattice file")
        return grid

    # --- integrity -----------------------------------------------------
    def normalise(self) -> None:
        """Make every row exactly as wide as the column list, and upgrade
        code cells saved under the older two-key spec to the current tags."""
        width = len(self.columns)
        for r in self.rows:
            r.cells = [_upgrade_cell(c) for c in r.cells]
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
