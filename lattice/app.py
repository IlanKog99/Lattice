"""The Lattice application: top bar, grid, command bar, and status line."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from . import APP_NAME, __version__, store
from .screens import AddScreen, MassScreen, RemoveScreen
from .widgets import CommandInput, GridView

def _k(key: str, label: str) -> str:
    return f"[#ff6a3d b]{key}[/] [#aeb8c4]{label}[/]"


HINTS = "   ".join(
    [
        _k("↑↓←→/wasd", "move"),
        _k("enter/ctrl+c", "copy"),
        _k("f", "edit"),
        _k("del", "clear"),
        _k("/", "commands"),
        _k("q", "quit"),
    ]
)

DEFAULT_REVEAL_MINUTES = 1
MAX_REVEAL_MINUTES = 600
UNDO_DEPTH = 100

_COMMANDS = {
    "add": AddScreen,
    "remove": RemoveScreen,
    "mass": MassScreen,
}

# Everything the autocomplete menu can offer: (name, description).
COMMAND_INFO = [
    ("add", "Add a row or column"),
    ("remove", "Hide a row or column"),
    ("mass", "Update many cells in order"),
    ("undo", "Undo the last change"),
    ("visible", "Reveal values (e.g. /visible 5)"),
    ("hide", "Mask values now"),
    ("quit", "Exit Lattice"),
]
_KNOWN = {name for name, _ in COMMAND_INFO} | {"exit", "q"}


class LatticeApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = APP_NAME

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.grid = store.load()
        self.revealed = False
        self._reveal_timer = None
        self._undo: list = []

    # --- layout --------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(
            f"[b]{APP_NAME}[/b]  [dim]v{__version__}[/dim]\n"
            "[dim]a quiet little grid keeper[/dim]",
            id="topbar",
        )
        yield GridView(id="grid")
        yield Static(HINTS, id="status")
        with Vertical(id="cmdbar"):
            yield OptionList(id="cmdmenu")
            with Horizontal(id="cmdrow"):
                yield Static("›", id="cmdprompt")
                # select_on_focus=False so the leading "/" isn't highlighted
                # and overwritten by the first keystroke.
                yield CommandInput(id="cmdinput", select_on_focus=False)

    def on_mount(self) -> None:
        if not self.grid.columns:
            self.set_status("Empty store — use /add to begin, or seed from a file")

    # --- grid helpers --------------------------------------------------
    @property
    def grid_view(self) -> GridView:
        return self.query_one(GridView)

    def persist(self) -> None:
        """Auto-save: called after every change that touches the store."""
        store.save(self.grid)

    # --- undo ----------------------------------------------------------
    def push_undo(self) -> None:
        """Snapshot the grid *before* a change, so /undo can roll it back."""
        from .models import Grid

        self._undo.append(Grid.from_dict(self.grid.to_dict()))
        if len(self._undo) > UNDO_DEPTH:
            self._undo.pop(0)

    def undo(self) -> None:
        if not self._undo:
            self.set_status("Nothing to undo")
            return
        self.grid = self._undo.pop()
        self.persist()
        self.refresh_grid()
        self.set_status("Undid last change")

    def refresh_grid(self, _result=None) -> None:
        self.grid_view.rebuild()
        self.grid_view.focus()

    def set_status(self, message: str | None = None) -> None:
        bar = self.query_one("#status", Static)
        bar.update(message or HINTS)
        if message:
            self.set_timer(2.6, lambda: bar.update(HINTS))

    # --- command bar + autocomplete menu -------------------------------
    def open_command(self) -> None:
        self.query_one("#cmdbar").display = True
        field = self.query_one("#cmdinput", CommandInput)
        field.value = "/"
        field.cursor_position = 1
        self._filter_menu("/")
        field.focus()

    def close_command(self) -> None:
        self.query_one("#cmdbar").display = False
        self.query_one("#cmdinput", CommandInput).value = ""
        self.grid_view.focus()

    def _menu(self) -> OptionList:
        return self.query_one("#cmdmenu", OptionList)

    def _filter_menu(self, value: str) -> None:
        tokens = value.lstrip("/").split()
        prefix = tokens[0].lower() if tokens else ""
        menu = self._menu()
        menu.clear_options()
        matches = [(n, d) for n, d in COMMAND_INFO if n.startswith(prefix)]
        for name, desc in matches:
            menu.add_option(
                Option(Text.from_markup(f"[b]/{name}[/b]  [dim]{desc}[/dim]"), id=name)
            )
        menu.display = bool(matches)
        if matches:
            menu.highlighted = 0

    def _highlighted_command(self) -> str | None:
        menu = self._menu()
        if not menu.option_count or menu.highlighted is None:
            return None
        return menu.get_option_at_index(menu.highlighted).id

    def command_move(self, delta: int) -> None:
        menu = self._menu()
        if not menu.option_count:
            return
        if delta > 0:
            menu.action_cursor_down()
        else:
            menu.action_cursor_up()

    def command_complete(self) -> None:
        name = self._highlighted_command()
        if not name:
            return
        field = self.query_one("#cmdinput", CommandInput)
        field.value = f"/{name} "
        field.cursor_position = len(field.value)
        self._filter_menu(field.value)

    def command_submit(self) -> None:
        value = self.query_one("#cmdinput", CommandInput).value
        tokens = value.lstrip("/").split()
        typed = tokens[0].lower() if tokens else ""
        if typed in _KNOWN:
            self.run_command(value)
        else:
            name = self._highlighted_command()
            self.run_command(f"/{name}" if name else value)

    def on_input_changed(self, event) -> None:
        if event.input.id == "cmdinput":
            self._filter_menu(event.value)

    def on_option_list_option_selected(self, event) -> None:
        # A click on a menu entry runs that command.
        if event.option_list.id == "cmdmenu":
            self.run_command(f"/{event.option.id}")

    def run_command(self, raw: str) -> None:
        self.close_command()
        parts = raw.strip().lstrip("/").split()
        if not parts:
            return
        name, args = parts[0].lower(), parts[1:]
        if name in ("q", "quit", "exit"):
            self.exit()
            return
        if name == "visible":
            self._cmd_visible(args)
            return
        if name == "hide":
            self.hide_values()
            return
        if name == "undo":
            self.undo()
            return
        screen = _COMMANDS.get(name)
        if screen is None:
            self.set_status(f"Unknown command: /{name}")
            return
        self.push_screen(screen(), self.refresh_grid)

    # --- value visibility ----------------------------------------------
    def _cmd_visible(self, args: list[str]) -> None:
        minutes: float = DEFAULT_REVEAL_MINUTES
        if args:
            try:
                minutes = float(args[0])
            except ValueError:
                self.set_status("Usage: /visible [minutes]")
                return
            if minutes <= 0 or minutes > MAX_REVEAL_MINUTES:
                self.set_status(f"Minutes must be between 0 and {MAX_REVEAL_MINUTES}")
                return
        self.reveal_for(minutes)

    def reveal_for(self, minutes: float) -> None:
        self.revealed = True
        self.grid_view.apply_reveal()
        if self._reveal_timer is not None:
            self._reveal_timer.stop()
        self._reveal_timer = self.set_timer(minutes * 60, self.hide_values)
        shown = f"{minutes:g}"
        self.set_status(f"Values visible for {shown} min — /hide to mask now")

    def hide_values(self) -> None:
        self.revealed = False
        if self._reveal_timer is not None:
            self._reveal_timer.stop()
            self._reveal_timer = None
        self.grid_view.apply_reveal()
        self.set_status("Values hidden")


def main() -> None:
    LatticeApp().run()


if __name__ == "__main__":
    main()


# Make the stylesheet path absolute regardless of working directory.
LatticeApp.CSS_PATH = str(Path(__file__).resolve().parent / "styles.tcss")
