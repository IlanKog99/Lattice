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


class FindInput(Input):
    """The find-bar input. Typing filters the label column; Tab cycles matches.

    Enter accepts (keeps the cursor on the current match), Escape cancels (puts
    it back). Typing is handled by the app via Input.Changed.
    """

    def on_key(self, event) -> None:
        app = self.app
        key = event.key
        if key == "enter":
            event.stop()
            app.find_accept()
        elif key == "escape":
            event.stop()
            app.find_cancel()
        elif key == "tab":
            event.stop()
            event.prevent_default()
            app.find_next(1)
        elif key == "shift+tab":
            event.stop()
            event.prevent_default()
            app.find_next(-1)


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

    def __init__(
        self, value: str, vrow: int, vcol: int, *, is_label: bool = False, header: bool = False
    ) -> None:
        classes = "cell"
        if is_label:
            classes += " label"   # row-header column: colour + a divider border
        if header:
            classes += " hcell"   # top header row
        super().__init__(classes=classes)
        self._value = value
        self._is_label = is_label
        self._header = header
        self._revealed = False
        self.vrow = vrow
        self.vcol = vcol

    def compose(self):
        yield Static(self._display(), classes="celltext")

    def _display(self) -> str:
        # Labels and headers are identifiers, not secret, so they always show.
        # Value cells stay masked until revealed with /visible.
        if not self._value:
            return " "
        if self._is_label or self._header or self._revealed:
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
        self.find_mode = False
        self.matches: list[int] = []
        self.match_pos = 0
        self._find_origin = (0, 0)
        self._peek_cell: "Cell | None" = None
        self._peek_timer = None
        self.move_mode = False
        self.grabbed = False
        self.grab_ri = 0
        self.grab_ci = 0
        self._move_original = None
        self.header_cells: dict[int, Cell] = {}
        self.rename_mode = False
        self.rename_cur = ("h", 0)
        self._clip = ""

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
            width = max(12, min(longest + 2, 42))
            if ci == 0:
                width += 1  # room for the row-header separator border
            widths.append(width)
        return widths

    def rebuild(self) -> None:
        self.remove_children()
        self.cells.clear()
        self.vrows = self.grid.visible_row_indexes()
        self.vcols = self.grid.visible_col_indexes()
        widths = self._widths()

        rows: list[Horizontal] = []

        self.header_cells: dict[int, Cell] = {}
        header_cells = []
        for vc, (w, ci) in enumerate(zip(widths, self.vcols)):
            cell = Cell(self.grid.columns[ci].name, -1, vc, is_label=(ci == 0), header=True)
            cell.styles.width = w
            self.header_cells[vc] = cell
            header_cells.append(cell)
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
        if self._clip:
            self.mark_clipboard(self._clip)

        nav = self._nav_cols()
        if self.rename_mode:
            self._rename_select(self.rename_cur, True)
        elif self.vrows and nav:
            r = min(self.cursor[0], len(self.vrows) - 1)
            c = min(max(self.cursor[1], nav[0]), nav[-1])
            self.cursor = (r, c)
            self._select(self.cursor, True)

    def apply_reveal(self) -> None:
        """Sync every cell's masked/revealed display with the app state."""
        revealed = getattr(self.app, "revealed", False)
        for cell in self.cells.values():
            cell.show(revealed)

    def mark_clipboard(self, text: str) -> None:
        """Faintly flag cells whose value equals the current clipboard text."""
        self._clip = text
        match = (text or "")
        for cell in self.cells.values():
            cell.set_class(bool(match) and cell.value == match, "clipmatch")

    # --- selection -----------------------------------------------------
    def _nav_cols(self) -> list[int]:
        """Visible column positions the cursor may land on.

        The label column (actual index 0) is a row identifier, like a header,
        so it is never selectable.
        """
        return [vc for vc in range(len(self.vcols)) if self.vcols[vc] != 0]

    def _select(self, coord, on: bool) -> None:
        cell = self.cells.get(coord)
        if cell is None:
            return
        cell.select(on)
        # Faintly band the whole row so it's clear which row the cursor is on.
        vr = coord[0]
        for (r, _c), other in self.cells.items():
            if r == vr:
                other.set_class(on, "rowsel")
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

    # --- move mode (reorder rows/columns) ------------------------------
    def enter_move(self) -> None:
        from .models import Grid

        self.move_mode = True
        self.grabbed = False
        self._move_original = Grid.from_dict(self.grid.to_dict())
        self.add_class("movemode")
        self.focus()
        self.app.set_status("Move: navigate, then space to grab a row + column")

    def _grab(self) -> None:
        self.grabbed = True
        self.grab_ri = self.vrows[self.cursor[0]]
        self.grab_ci = self.vcols[self.cursor[1]]
        self._apply_grab()
        self.app.set_status("Grabbed — arrows move the row (↑↓) and column (←→); space to drop")

    def _drop(self) -> None:
        self.grabbed = False
        for cell in self.cells.values():
            cell.remove_class("grabrow")
            cell.remove_class("grabcol")
        self.app.set_status("Dropped — navigate and grab another, or enter to save")

    def _apply_grab(self) -> None:
        gvr = self.vrows.index(self.grab_ri)
        gvc = self.vcols.index(self.grab_ci)
        for (r, c), cell in self.cells.items():
            cell.set_class(r == gvr, "grabrow")
            cell.set_class(c == gvc, "grabcol")

    def _move_row(self, direction: int) -> None:
        vis = self.grid.visible_row_indexes()
        pos = vis.index(self.grab_ri)
        npos = pos + direction
        if not (0 <= npos < len(vis)):
            return
        i, j = vis[pos], vis[npos]
        self.grid.rows[i], self.grid.rows[j] = self.grid.rows[j], self.grid.rows[i]
        self.grab_ri = j

    def _move_col(self, direction: int) -> None:
        vis = [ci for ci in self.grid.visible_col_indexes() if ci != 0]
        if self.grab_ci not in vis:
            return
        pos = vis.index(self.grab_ci)
        npos = pos + direction
        if not (0 <= npos < len(vis)):
            return
        i, j = vis[pos], vis[npos]
        self.grid.columns[i], self.grid.columns[j] = self.grid.columns[j], self.grid.columns[i]
        for row in self.grid.rows:
            row.cells[i], row.cells[j] = row.cells[j], row.cells[i]
        self.grab_ci = j

    def _reorder(self, row: int = 0, col: int = 0) -> None:
        if row:
            self._move_row(row)
        if col:
            self._move_col(col)
        self.rebuild()
        self._select(self.cursor, False)
        self.cursor = (self.vrows.index(self.grab_ri), self.vcols.index(self.grab_ci))
        self._select(self.cursor, True)
        self._apply_grab()

    def finish_move(self, apply: bool) -> None:
        if apply:
            self.app.push_undo_state(self._move_original)
            self.app.persist()
        else:
            self.app.grid = self._move_original
        self.move_mode = False
        self.grabbed = False
        self._move_original = None
        self.remove_class("movemode")
        self.rebuild()
        self.focus()
        self.app.set_status("New order saved" if apply else "Move cancelled")

    # --- rename mode (edit row/column headers) -------------------------
    def enter_rename(self) -> None:
        self.rename_mode = True
        self.add_class("renamemode")
        self._select(self.cursor, False)  # drop the normal cursor band
        self.rename_cur = ("h", 0)
        self._rename_select(self.rename_cur, True)
        self.focus()
        self.app.set_status("Rename: navigate headers · r edit · enter save · esc exit")

    def _rename_cell(self, target) -> "Cell | None":
        kind, idx = target
        if kind == "h":
            return self.header_cells.get(idx)
        return self.cells.get((idx, 0))

    def _rename_select(self, target, on: bool) -> None:
        cell = self._rename_cell(target)
        if cell is not None:
            cell.select(on)
            if on:
                self.call_after_refresh(self.scroll_to_widget, cell)

    def _rename_move(self, dr: int, dc: int) -> None:
        kind, idx = self.rename_cur
        new = None
        if kind == "h":
            if dc < 0 and idx > 0:
                new = ("h", idx - 1)
            elif dc > 0 and idx < len(self.vcols) - 1:
                new = ("h", idx + 1)
            elif dr > 0 and idx == 0 and self.vrows:
                new = ("r", 0)
        else:  # "r" — a row label in the left column
            if dr < 0:
                new = ("h", 0) if idx == 0 else ("r", idx - 1)
            elif dr > 0 and idx < len(self.vrows) - 1:
                new = ("r", idx + 1)
        if new is not None and new != self.rename_cur:
            self._rename_select(self.rename_cur, False)
            self.rename_cur = new
            self._rename_select(new, True)

    def rename_edit(self) -> None:
        if self.editing:
            return
        cell = self._rename_cell(self.rename_cur)
        if cell is None:
            return
        self.editing = True
        kind, idx = self.rename_cur

        def submit(value: str) -> None:
            self.app.push_undo()
            if kind == "h":
                self.grid.columns[self.vcols[idx]].name = value
            else:
                self.grid.rows[self.vrows[idx]].cells[0] = value
            self.app.persist()
            self.editing = False
            self.rebuild()
            self.focus()
            self.app.set_status("Renamed")

        def cancel() -> None:
            cell.end_edit()
            self.editing = False
            self.focus()
            self.app.set_status("Rename cancelled")

        cell.begin_edit(submit, cancel)

    def exit_rename(self) -> None:
        self._rename_select(self.rename_cur, False)
        self.rename_mode = False
        self.remove_class("renamemode")
        self.rebuild()
        self.focus()
        self.app.set_status(None)

    # --- peek (hold v to reveal the current cell) ----------------------
    PEEK_HOLD = 0.7  # re-mask this long after the last v (i.e. after release)

    def peek(self) -> None:
        cell = self.current()
        if cell is None:
            return
        # Holding v repeats the key; if the cursor changed, restore the old one.
        if self._peek_cell is not None and self._peek_cell is not cell:
            self._peek_cell.show(getattr(self.app, "revealed", False))
        cell.show(True)
        self._peek_cell = cell
        if self._peek_timer is not None:
            self._peek_timer.stop()
        self._peek_timer = self.set_timer(self.PEEK_HOLD, self._end_peek)

    def _end_peek(self) -> None:
        if self._peek_cell is not None:
            self._peek_cell.show(getattr(self.app, "revealed", False))
            self._peek_cell = None
        self._peek_timer = None

    # --- find ----------------------------------------------------------
    def start_find(self) -> None:
        self.find_mode = True
        self._find_origin = self.cursor
        self.matches = []
        self.match_pos = 0

    def update_find(self, query: str) -> None:
        for cell in self.cells.values():
            cell.remove_class("match")
        q = query.strip().lower()
        self.matches = []
        if q:
            for vr, ri in enumerate(self.vrows):
                if q in self.grid.rows[ri].cells[0].lower():
                    self.matches.append(vr)
        for vr in self.matches:
            label = self.cells.get((vr, 0))
            if label is not None:
                label.add_class("match")
        if self.matches:
            self.match_pos = 0
            self._goto_match()

    def _goto_match(self) -> None:
        nav = self._nav_cols()
        if not nav or not self.matches:
            return
        vr = self.matches[self.match_pos]
        self._select(self.cursor, False)
        self.cursor = (vr, nav[0])
        self._select(self.cursor, True)

    def find_next(self, delta: int) -> None:
        if not self.matches:
            return
        self.match_pos = (self.match_pos + delta) % len(self.matches)
        self._goto_match()

    def clear_find(self, restore: bool) -> None:
        for cell in self.cells.values():
            cell.remove_class("match")
        self.find_mode = False
        if restore and 0 <= self._find_origin[0] < len(self.vrows):
            self._select(self.cursor, False)
            self.cursor = self._find_origin
            self._select(self.cursor, True)
        self.matches = []
        self.match_pos = 0

    # --- keys ----------------------------------------------------------
    def _on_move_key(self, event) -> None:
        key = event.key
        if not self.grabbed:
            if key in _MOVES:
                event.stop()
                self.move(*_MOVES[key])
            elif key == "space":
                event.stop()
                self._grab()
            elif key == "enter":
                event.stop()
                self.app.move_request_apply()
            elif key == "escape":
                event.stop()
                self.app.move_request_cancel()
            return
        # grabbed: arrows/wasd reorder instead of moving the cursor
        if key in ("up", "w"):
            event.stop()
            self._reorder(row=-1)
        elif key in ("down", "s"):
            event.stop()
            self._reorder(row=1)
        elif key in ("left", "a"):
            event.stop()
            self._reorder(col=-1)
        elif key in ("right", "d"):
            event.stop()
            self._reorder(col=1)
        elif key == "space":
            event.stop()
            self._drop()
        elif key == "enter":
            event.stop()
            self.app.move_request_apply()
        elif key == "escape":
            event.stop()
            self.app.move_request_cancel()

    def _on_rename_key(self, event) -> None:
        key = event.key
        if key in _MOVES:
            event.stop()
            self._rename_move(*_MOVES[key])
        elif key in ("r", "enter"):
            event.stop()
            self.rename_edit()
        elif key == "escape":
            event.stop()
            self.exit_rename()

    def on_key(self, event) -> None:
        if self.editing:
            return
        if self.rename_mode:
            self._on_rename_key(event)
            return
        if self.move_mode:
            self._on_move_key(event)
            return
        key = event.key
        if key in _MOVES:
            event.stop()
            self.move(*_MOVES[key])
        elif key in ("enter", "ctrl+c"):
            event.stop()
            self.copy()
        elif key == "e":
            event.stop()
            self.edit()
        elif key in ("f", "ctrl+f"):
            event.stop()
            self.app.open_find()
        elif key == "v":
            event.stop()
            self.peek()
        elif key == "ctrl+z":
            event.stop()
            self.app.undo()
        elif key in ("delete", "backspace"):
            event.stop()
            self.clear()
        elif key == "slash":
            event.stop()
            self.app.open_command()
