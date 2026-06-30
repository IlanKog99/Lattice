"""Modal flows for the slash commands: add, remove (hide), and mass update.

Each modal is a small step machine. A step swaps the modal body for either a
choice list or a single text prompt. Body swaps are deferred to
``call_after_refresh`` so we never rebuild the tree from inside the very event
(key press / option select) that triggered the step.
"""

from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from .widgets import BoxInput


class StepModal(ModalScreen):
    """Base modal with choice/text step helpers and Escape-to-cancel."""

    title_text = ""

    def compose(self):
        with Vertical(classes="modal"):
            yield Static(self.title_text, classes="modal-title")
            yield Vertical(id="body")

    def on_mount(self) -> None:
        self.start()

    # --- to override ---------------------------------------------------
    def start(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    # --- step rendering ------------------------------------------------
    def _body(self) -> Vertical:
        return self.query_one("#body", Vertical)

    def _swap(self, *widgets, focus=None) -> None:
        body = self._body()
        body.remove_children()
        body.mount(*widgets)
        if focus is not None:
            self.call_after_refresh(focus.focus)

    def ask_choice(self, prompt: str, options: list[tuple[str, object]], on_pick: Callable) -> None:
        self._on_pick = on_pick
        self._choice_values = [value for _, value in options]
        option_list = OptionList(
            *[Option(label, id=str(i)) for i, (label, _) in enumerate(options)]
        )
        self._swap(Static(prompt, classes="prompt"), option_list, focus=option_list)

    def ask_text(self, prompt: str, on_submit: Callable[[str], None], placeholder: str = "") -> None:
        def deferred(value: str) -> None:
            self.call_after_refresh(on_submit, value)

        field = BoxInput("", deferred, self.cancel, placeholder=placeholder, classes="modalinput")
        self._swap(Static(prompt, classes="prompt"), field, focus=field)

    def ask_confirm(self, prompt: str, on_yes: Callable[[], None]) -> None:
        self._on_yes = on_yes
        yes = Button("Yes", id="yes", variant="error")
        no = Button("No", id="no", variant="primary")
        buttons = Horizontal(yes, no, classes="confirm-row")
        # Focus "No" by default so a stray Enter doesn't confirm.
        self._swap(Static(prompt, classes="prompt"), buttons, focus=no)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.call_after_refresh(self._on_yes)
        else:
            self.cancel()

    # --- events --------------------------------------------------------
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        value = self._choice_values[int(event.option.id)]
        self.call_after_refresh(self._on_pick, value)

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop()
            self.cancel()

    # --- exits ---------------------------------------------------------
    def cancel(self) -> None:
        self.dismiss(False)

    def finish(self, changed: bool) -> None:
        if changed:
            self.app.persist()
        self.dismiss(changed)


class AddScreen(StepModal):
    title_text = "/add  —  new row or column"

    def start(self) -> None:
        self.ask_choice("Add a row or a column?", [("Row", "row"), ("Column", "col")], self._kind)

    def _kind(self, kind: str) -> None:
        self.kind = kind
        word = "row" if kind == "row" else "column"
        self.ask_text(f"Name for the new {word}:", self._named, placeholder="name")

    def _named(self, name: str) -> None:
        name = name.strip()
        if not name:
            self.app.set_status("Name cannot be empty")
            self.cancel()
            return
        self.entry_name = name
        grid = self.app.grid
        if self.kind == "row":
            self.targets = [ci for ci in grid.visible_col_indexes() if ci != 0]
            self.labels = [grid.columns[ci].name for ci in self.targets]
        else:
            self.targets = grid.visible_row_indexes()
            self.labels = [grid.rows[ri].cells[0] for ri in self.targets]
        self.values: list[str] = []
        self.idx = 0
        self._collect()

    def _collect(self) -> None:
        if self.idx >= len(self.targets):
            self._commit()
            return
        label = self.labels[self.idx]
        self.ask_text(
            f"Value for “{label}”  ({self.idx + 1}/{len(self.targets)}):",
            self._value,
            placeholder="leave blank for empty",
        )

    def _value(self, value: str) -> None:
        self.values.append(value)
        self.idx += 1
        self._collect()

    def _commit(self) -> None:
        self.app.push_undo()
        grid = self.app.grid
        if self.kind == "row":
            cells = [""] * len(grid.columns)
            cells[0] = self.entry_name
            for ci, value in zip(self.targets, self.values):
                cells[ci] = value
            grid.add_row(cells)
        else:
            full = [""] * len(grid.rows)
            for ri, value in zip(self.targets, self.values):
                full[ri] = value
            grid.add_column(self.entry_name, full)
        self.finish(True)


class RemoveScreen(StepModal):
    title_text = "/remove  —  hide a row or column"

    def start(self) -> None:
        self.ask_choice("Hide a row or a column?", [("Row", "row"), ("Column", "col")], self._kind)

    def _kind(self, kind: str) -> None:
        self.kind = kind
        grid = self.app.grid
        if kind == "row":
            items = [(grid.rows[ri].cells[0] or f"row {ri}", ri) for ri in grid.visible_row_indexes()]
        else:
            items = [(grid.columns[ci].name, ci) for ci in grid.visible_col_indexes() if ci != 0]
        if not items:
            self.app.set_status("Nothing left to hide")
            self.cancel()
            return
        self.ask_choice(f"Which {kind} should be hidden?", items, self._picked)

    def _picked(self, index: int) -> None:
        self._index = index
        grid = self.app.grid
        label = grid.rows[index].cells[0] if self.kind == "row" else grid.columns[index].name
        self.ask_confirm(
            f"Hide {self.kind} “{label}”?\nIt stays in the store and can be brought back with /undo.",
            self._do_hide,
        )

    def _do_hide(self) -> None:
        self.app.push_undo()
        grid = self.app.grid
        if self.kind == "row":
            grid.rows[self._index].hidden = True
        else:
            grid.columns[self._index].hidden = True
        self.finish(True)


class MassScreen(StepModal):
    title_text = "/mass  —  update many cells in order"

    def start(self) -> None:
        self.ask_choice(
            "Mass update a row or a column?", [("Row", "row"), ("Column", "col")], self._kind
        )

    def _kind(self, kind: str) -> None:
        self.kind = kind
        grid = self.app.grid
        if kind == "row":
            items = [(grid.rows[ri].cells[0] or f"row {ri}", ri) for ri in grid.visible_row_indexes()]
        else:
            items = [(grid.columns[ci].name, ci) for ci in grid.visible_col_indexes() if ci != 0]
        if not items:
            self.app.set_status("Nothing to update")
            self.cancel()
            return
        self.ask_choice(f"Which {kind}?", items, self._target)

    def _target(self, index: int) -> None:
        self.target = index
        grid = self.app.grid
        if self.kind == "row":
            self.fields = [ci for ci in grid.visible_col_indexes() if ci != 0]
            self.labels = [grid.columns[ci].name for ci in self.fields]
        else:
            self.fields = grid.visible_row_indexes()
            self.labels = [grid.rows[ri].cells[0] for ri in self.fields]
        self.idx = 0
        self.changed = False
        self._snapped = False
        self._prompt()

    def _current(self, i: int) -> str:
        grid = self.app.grid
        if self.kind == "row":
            return grid.rows[self.target].cells[self.fields[i]]
        return grid.rows[self.fields[i]].cells[self.target]

    def _prompt(self) -> None:
        if self.idx >= len(self.fields):
            self.finish(self.changed)
            return
        label = self.labels[self.idx]
        self.ask_text(
            f"{label}  ({self.idx + 1}/{len(self.fields)})  —  empty line finishes:",
            self._entered,
            placeholder=self._current(self.idx) or "empty",
        )

    def _entered(self, value: str) -> None:
        if value == "":  # empty line acts as EOF
            self.finish(self.changed)
            return
        if not self._snapped:  # snapshot once, before the first change
            self.app.push_undo()
            self._snapped = True
        grid = self.app.grid
        if self.kind == "row":
            grid.rows[self.target].cells[self.fields[self.idx]] = value
        else:
            grid.rows[self.fields[self.idx]].cells[self.target] = value
        self.changed = True
        self.idx += 1
        self._prompt()
