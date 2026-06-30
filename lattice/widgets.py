"""Reusable TUI widgets: the editable grid, cells, and the box input.

Terminology note: cells hold opaque values. The first column is the label
column; everything else is a free-form value. Nothing here knows or cares what
those values mean.
"""

from __future__ import annotations

from typing import Callable

import pyperclip
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Input, Static

# Keys that move the cursor, mapped to (row delta, col delta).
_MOVES = {
    "up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1),
    "w": (-1, 0), "s": (1, 0), "a": (0, -1), "d": (0, 1),
}


class BoxInput(Input):
    """An Input that reports submit/cancel through plain callbacks.

    Used both for the in-cell editor and the command bar. Enter submits the
    current text; Escape cancels. Both are handled in ``on_key`` so they never
    reach the parent grid's navigation handler.
    """

    def __init__(
        self,
        value: str,
        on_submit: Callable[[str], None],
        on_cancel: Callable[[], None],
        *,
        placeholder: str = "",
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(value=value, placeholder=placeholder, id=id, classes=classes)
        self._on_submit = on_submit
        self._on_cancel = on_cancel

    def on_key(self, event) -> None:
        if event.key == "enter":
            event.stop()
            self._on_submit(self.value)
        elif event.key == "escape":
            event.stop()
            self._on_cancel()


class CommandInput(Input):
    """The command-bar input. Drives the autocomplete menu above it.

    Up/Down move the menu highlight, Tab completes to it, Enter runs, Escape
    closes. The menu itself is filtered by the app as the value changes.
    """

    def on_key(self, event) -> None:
        app = self.app
        key = event.key
        if key == "enter":
            event.stop()
            app.command_submit()
        elif key == "escape":
            event.stop()
            app.close_command()
        elif key == "down":
            event.stop()
            app.command_move(1)
        elif key == "up":
            event.stop()
            app.command_move(-1)
        elif key == "tab":
            event.stop()
            event.prevent_default()
            app.command_complete()


class Cell(Container):
    """A single grid cell. Shows a value; can flip into an inline editor."""

    MASK = "••••••"

    def __init__(self, value: str, vrow: int, vcol: int, *, is_label: bool) -> None:
        classes = "cell label" if is_label else "cell"
        super().__init__(classes=classes)
        self._value = value
        self._is_label = is_label
        self._revealed = False
        self.vrow = vrow
        self.vcol = vcol

    def compose(self):
        yield Static(self._display(), classes="celltext")

    def _display(self) -> str:
        # Labels are row identifiers, not secret, so they always show. Value
        # cells stay masked until the user reveals them with /visible.
        if not self._value:
            return " "
        if self._is_label or self._revealed:
            return self._value
        return self.MASK

    @property
    def value(self) -> str:
        return self._value

    def show(self, revealed: bool) -> None:
        self._revealed = revealed
        try:
            self.query_one(".celltext", Static).update(self._display())
        except Exception:  # noqa: BLE001 - inner Static not composed yet
            pass

    def set_value(self, value: str) -> None:
        self._value = value
        self.query_one(".celltext", Static).update(self._display())

    def select(self, on: bool) -> None:
        self.set_class(on, "sel")

    def on_click(self) -> None:
        # Clicking a value cell teleports the cursor there. Labels aren't
        # selectable, so clicks on them are ignored.
        if not self._is_label:
            self.app.grid_view.set_cursor(self.vrow, self.vcol)

    def flash(self) -> None:
        """Briefly highlight the cell to confirm a copy."""
        self.add_class("copied")
        self.set_timer(0.45, lambda: self.remove_class("copied"))

    def begin_edit(self, on_submit, on_cancel) -> None:
        self.query_one(".celltext").display = False
        editor = BoxInput(self._value, on_submit, on_cancel, classes="celledit")
        self.mount(editor)
        editor.focus()

    def end_edit(self) -> None:
        for editor in self.query(BoxInput):
            editor.remove()
        self.query_one(".celltext").display = True


class GridView(VerticalScroll):
    """Scrollable, keyboard-driven grid of cells."""

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.vrows: list[int] = []
        self.vcols: list[int] = []
        self.cells: dict[tuple[int, int], Cell] = {}
        self.cursor: tuple[int, int] = (0, 0)
        self.editing = False

    @property
    def grid(self):
        return self.app.grid

    def on_mount(self) -> None:
        self.rebuild()
        self.focus()

    # --- construction --------------------------------------------------
    def _widths(self) -> list[int]:
        widths = []
        for ci in self.vcols:
            longest = len(self.grid.columns[ci].name)
            for ri in self.vrows:
                longest = max(longest, len(self.grid.rows[ri].cells[ci]))
            widths.append(max(12, min(longest + 2, 42)))
        return widths

    def rebuild(self) -> None:
        self.remove_children()
        self.cells.clear()
        self.vrows = self.grid.visible_row_indexes()
        self.vcols = self.grid.visible_col_indexes()
        widths = self._widths()

        rows: list[Horizontal] = []

        header_cells = []
        for w, ci in zip(widths, self.vcols):
            box = Container(
                Static(self.grid.columns[ci].name or " ", classes="celltext"),
                classes="cell hcell",
            )
            box.styles.width = w
            header_cells.append(box)
        rows.append(Horizontal(*header_cells, classes="gridrow header"))

        for vr, ri in enumerate(self.vrows):
            line = []
            for vc, ci in enumerate(self.vcols):
                cell = Cell(
                    self.grid.rows[ri].cells[ci], vr, vc, is_label=(ci == 0)
                )
                cell.styles.width = widths[vc]
                self.cells[(vr, vc)] = cell
                line.append(cell)
            rows.append(Horizontal(*line, classes="gridrow"))

        self.mount(*rows)
        # Cells compose their inner Static on the next refresh; sync reveal
        # state after that so a rebuild while revealed keeps values shown.
        if getattr(self.app, "revealed", False):
            self.call_after_refresh(self.apply_reveal)

        nav = self._nav_cols()
        if self.vrows and nav:
            r = min(self.cursor[0], len(self.vrows) - 1)
            c = min(max(self.cursor[1], nav[0]), nav[-1])
            self.cursor = (r, c)
            self._select(self.cursor, True)

    def apply_reveal(self) -> None:
        """Sync every cell's masked/revealed display with the app state."""
        revealed = getattr(self.app, "revealed", False)
        for cell in self.cells.values():
            cell.show(revealed)

    # --- selection -----------------------------------------------------
    def _nav_cols(self) -> list[int]:
        """Visible column positions the cursor may land on.

        The label column (actual index 0) is a row identifier, like a header,
        so it is never selectable.
        """
        return [vc for vc in range(len(self.vcols)) if self.vcols[vc] != 0]

    def _select(self, coord, on: bool) -> None:
        cell = self.cells.get(coord)
        if cell is not None:
            cell.select(on)
            if on:
                self.call_after_refresh(self.scroll_to_widget, cell)

    def current(self) -> Cell | None:
        return self.cells.get(self.cursor)

    def move(self, dr: int, dc: int) -> None:
        if self.editing or not self.vrows:
            return
        nav = self._nav_cols()
        if not nav:
            return
        r, c = self.cursor
        # Wrap around at every edge.
        nr = (r + dr) % len(self.vrows)
        pos = nav.index(c) if c in nav else 0
        nc = nav[(pos + dc) % len(nav)]
        if (nr, nc) != (r, c):
            self._select((r, c), False)
            self.cursor = (nr, nc)
            self._select((nr, nc), True)

    def set_cursor(self, vr: int, vc: int) -> None:
        """Move the selection to a specific cell (used by mouse clicks)."""
        if self.editing:
            return
        if vc not in self._nav_cols() or not (0 <= vr < len(self.vrows)):
            return
        if (vr, vc) != self.cursor:
            self._select(self.cursor, False)
            self.cursor = (vr, vc)
            self._select((vr, vc), True)
        self.focus()

    # --- actions -------------------------------------------------------
    def copy(self) -> None:
        cell = self.current()
        if cell is None:
            return
        try:
            pyperclip.copy(cell.value)
        except Exception:  # noqa: BLE001 - clipboard backend missing
            self.app.set_status("Clipboard unavailable on this system")
            return
        cell.flash()
        self.app.set_status("Copied to clipboard")

    def edit(self) -> None:
        if self.editing:
            return
        cell = self.current()
        if cell is None:
            return
        self.editing = True
        ri = self.vrows[self.cursor[0]]
        ci = self.vcols[self.cursor[1]]

        def submit(value: str) -> None:
            self.app.push_undo()
            self.grid.set_cell(ri, ci, value)
            self.app.persist()
            self.editing = False
            self.rebuild()
            self.focus()
            self.app.set_status("Saved")

        def cancel() -> None:
            cell.end_edit()
            self.editing = False
            self.focus()
            self.app.set_status("Edit cancelled")

        cell.begin_edit(submit, cancel)

    def clear(self) -> None:
        """Empty the selected cell (like editing it and deleting everything)."""
        if self.editing:
            return
        cell = self.current()
        if cell is None or not cell.value:
            return
        self.app.push_undo()
        ri = self.vrows[self.cursor[0]]
        ci = self.vcols[self.cursor[1]]
        self.grid.set_cell(ri, ci, "")
        self.app.persist()
        self.rebuild()
        self.focus()
        self.app.set_status("Cleared (undo with /undo)")

    # --- keys ----------------------------------------------------------
    def on_key(self, event) -> None:
        if self.editing:
            return
        key = event.key
        if key in _MOVES:
            event.stop()
            self.move(*_MOVES[key])
        elif key in ("enter", "ctrl+c"):
            event.stop()
            self.copy()
        elif key == "f":
            event.stop()
            self.edit()
        elif key in ("delete", "backspace"):
            event.stop()
            self.clear()
        elif key == "slash":
            event.stop()
            self.app.open_command()
