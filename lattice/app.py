"""The Lattice application: top bar, grid, command bar, and status line."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from . import APP_NAME, __version__, store
from .screens import AddScreen, MassScreen, RemoveScreen
from .widgets import BoxInput, GridView

HINTS = (
    "↑↓←→ / wasd  move   ·   enter  copy   ·   f  edit   ·   "
    "/visible  reveal   ·   /  command   ·   q  quit"
)

DEFAULT_REVEAL_MINUTES = 1
MAX_REVEAL_MINUTES = 600

_COMMANDS = {
    "add": AddScreen,
    "remove": RemoveScreen,
    "mass": MassScreen,
}


class LatticeApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = APP_NAME

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.grid = store.load()
        self.revealed = False
        self._reveal_timer = None

    # --- layout --------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(
            f"[b]{APP_NAME}[/b]  [dim]v{__version__}[/dim]\n"
            "[dim]a quiet little grid keeper[/dim]",
            id="topbar",
        )
        yield GridView(id="grid")
        yield Static(HINTS, id="status")
        with Horizontal(id="cmdbar"):
            yield Static("›", id="cmdprompt")
            yield BoxInput("", self.run_command, self.close_command, id="cmdinput")

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

    def refresh_grid(self, _result=None) -> None:
        self.grid_view.rebuild()
        self.grid_view.focus()

    def set_status(self, message: str | None = None) -> None:
        bar = self.query_one("#status", Static)
        bar.update(message or HINTS)
        if message:
            self.set_timer(2.6, lambda: bar.update(HINTS))

    # --- command bar ---------------------------------------------------
    def open_command(self) -> None:
        self.query_one("#cmdbar").display = True
        field = self.query_one("#cmdinput", BoxInput)
        field.value = "/"
        field.cursor_position = len(field.value)
        field.focus()

    def close_command(self) -> None:
        self.query_one("#cmdbar").display = False
        self.query_one("#cmdinput", BoxInput).value = ""
        self.grid_view.focus()

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
