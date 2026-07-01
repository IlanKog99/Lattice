"""Modal flows for the slash commands: add, remove (hide), and mass update.

Each command is a small step machine (`StepModal`) that swaps its body between
a choice list and a text prompt. A short key legend is shown at the bottom of
every popup. Choice steps support `b` to go back a step; `/remove` raises a
separate `ConfirmScreen` popup on top for the final yes/no.

Body swaps are deferred to ``call_after_refresh`` so we never rebuild the tree
from inside the event (key press / option select) that triggered the step.
"""

from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from .widgets import BoxInput


def _legend(pairs: list[tuple[str, str]]) -> str:
    """Build a coloured key legend (bright keys, dim labels)."""
    return "     ".join(f"[#ff9d5c b]{k}[/] [#7d8b95]{d}[/]" for k, d in pairs)


CHOICE_KEYS = _legend([("↑↓ / w s", "move"), ("enter", "select"), ("b", "back"), ("esc", "cancel")])
TEXT_KEYS = _legend([("enter", "save"), ("esc", "cancel")])
CONFIRM_KEYS = _legend([("←→ / a d", "switch"), ("enter", "select"), ("b", "back"), ("esc", "cancel")])


class ConfirmScreen(ModalScreen):
    """A small yes/no popup shown on top of another modal.

    Dismisses with one of: ``"yes"``, ``"no"``, ``"back"``, ``"cancel"``.
    """

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question

    def compose(self):
        with Vertical(classes="confirm-modal"):
            yield Static(self._question, classes="prompt")
            with Horizontal(classes="confirm-row"):
                yield Button("Yes", id="yes", variant="error")
                yield Button("No", id="no", variant="primary")
            yield Static(CONFIRM_KEYS, classes="modal-keys")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()  # safe default

    def _toggle(self) -> None:
        no = self.query_one("#no", Button)
        yes = self.query_one("#yes", Button)
        (yes if no.has_focus else no).focus()

    def on_key(self, event) -> None:
        key = event.key
        if key in ("left", "right", "a", "d"):
            event.stop()
            self._toggle()
        elif key == "enter":
            event.stop()
            focused = self.focused
            self.dismiss("yes" if (focused is not None and focused.id == "yes") else "no")
        elif key == "b":
            event.stop()
            self.dismiss("back")
        elif key == "escape":
            event.stop()
            self.dismiss("cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss("yes" if event.button.id == "yes" else "no")


class StepModal(ModalScreen):
    """Base modal: choice/text steps, a key legend, and `b`-to-go-back."""

    title_text = ""

    def compose(self):
        with Vertical(classes="modal"):
            yield Static(self.title_text, classes="modal-title")
            yield Vertical(id="body")
            yield Static("", classes="modal-keys", id="keys")

    def on_mount(self) -> None:
        self._history: list[Callable[[], None]] = []
        self.start()

    # --- to override ---------------------------------------------------
    def start(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    # --- step rendering ------------------------------------------------
    def _body(self) -> Vertical:
        return self.query_one("#body", Vertical)

    def set_keys(self, markup: str) -> None:
        self.query_one("#keys", Static).update(markup)

    def _swap(self, *widgets, focus=None) -> None:
        body = self._body()
        body.remove_children()
        body.mount(*widgets)
        if focus is not None:
            self.call_after_refresh(focus.focus)

    def step(self, render: Callable[[], None]) -> None:
        """Advance to a new step, remembering it for `b` (back)."""
        self._history.append(render)
        render()

    def back(self) -> None:
        if len(self._history) > 1:
            self._history.pop()
            self._history[-1]()
        else:
            self.cancel()

    def ask_choice(self, prompt: str, options: list[tuple[str, object]], on_pick: Callable) -> None:
        self._on_pick = on_pick
        self._choice_values = [value for _, value in options]
        option_list = OptionList(
            *[Option(label, id=str(i)) for i, (label, _) in enumerate(options)]
        )
        self._swap(Static(prompt, classes="prompt"), option_list, focus=option_list)
        self.set_keys(CHOICE_KEYS)

    def ask_text(self, prompt: str, on_submit: Callable[[str], None], placeholder: str = "") -> None:
        def deferred(value: str) -> None:
            self.call_after_refresh(on_submit, value)

        field = BoxInput("", deferred, self.cancel, placeholder=placeholder, classes="modalinput")
        self._swap(Static(prompt, classes="prompt"), field, focus=field)
        self.set_keys(TEXT_KEYS)

    # --- events --------------------------------------------------------
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        value = self._choice_values[int(event.option.id)]
        self.call_after_refresh(self._on_pick, value)

    def on_key(self, event) -> None:
        key = event.key
        if key == "escape":
            event.stop()
            self.cancel()
        elif key == "b":
            # Reaches here only on choice steps; a focused text input swallows
            # its own keystrokes, so typing "b" in a value never backs out.
            event.stop()
            self.back()
        elif key in ("w", "s"):
            lists = self.query(OptionList)
            if lists:
                event.stop()
                option_list = lists.first()
                if key == "w":
                    option_list.action_cursor_up()
                else:
                    option_list.action_cursor_down()

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
        self.step(self._pick_kind)

    def _pick_kind(self) -> None:
        self.ask_choice("Add a row or a column?", [("Row", "row"), ("Column", "col")], self._kind_chosen)

    def _kind_chosen(self, kind: str) -> None:
        self.kind = kind
        self.step(self._enter_name)

    def _enter_name(self) -> None:
        word = "row" if self.kind == "row" else "column"
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
        self.step(self._collect)

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
        self._collect()  # next field; no history push (text steps)

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
        self.step(self._pick_kind)

    def _pick_kind(self) -> None:
        self.ask_choice("Hide a row or a column?", [("Row", "row"), ("Column", "col")], self._kind_chosen)

    def _kind_chosen(self, kind: str) -> None:
        self.kind = kind
        self.step(self._pick_target)

    def _pick_target(self) -> None:
        grid = self.app.grid
        if self.kind == "row":
            items = [(grid.rows[ri].cells[0] or f"row {ri}", ri) for ri in grid.visible_row_indexes()]
        else:
            items = [(grid.columns[ci].name, ci) for ci in grid.visible_col_indexes() if ci != 0]
        if not items:
            self.app.set_status("Nothing left to hide")
            self.cancel()
            return
        self.ask_choice(f"Which {self.kind} should be hidden?", items, self._target_chosen)

    def _target_chosen(self, index: int) -> None:
        self._index = index
        grid = self.app.grid
        label = grid.rows[index].cells[0] if self.kind == "row" else grid.columns[index].name
        question = (
            f"Hide {self.kind} “{label}”?\n"
            "It stays in the store and can return with /undo."
        )
        self.app.push_screen(ConfirmScreen(question), self._confirmed)

    def _confirmed(self, result) -> None:
        if result == "yes":
            self._do_hide()
        elif result == "back":
            self._pick_target()  # re-show the list (already in history)
        else:  # "no" or "cancel"
            self.cancel()

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
        self.step(self._pick_kind)

    def _pick_kind(self) -> None:
        self.ask_choice("Mass update a row or a column?", [("Row", "row"), ("Column", "col")], self._kind_chosen)

    def _kind_chosen(self, kind: str) -> None:
        self.kind = kind
        self.step(self._pick_target)

    def _pick_target(self) -> None:
        grid = self.app.grid
        if self.kind == "row":
            items = [(grid.rows[ri].cells[0] or f"row {ri}", ri) for ri in grid.visible_row_indexes()]
        else:
            items = [(grid.columns[ci].name, ci) for ci in grid.visible_col_indexes() if ci != 0]
        if not items:
            self.app.set_status("Nothing to update")
            self.cancel()
            return
        self.ask_choice(f"Which {self.kind}?", items, self._target_chosen)

    def _target_chosen(self, index: int) -> None:
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
        self.step(self._prompt)

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
        self._prompt()  # next field; no history push (text steps)
