"""The Lattice application: top bar, grid, command bar, and status line."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from . import APP_NAME, __version__, store
from .screens import AddScreen, MassScreen, RemoveScreen
from .widgets import BoxInput, GridView

HINTS = "↑↓←→ / wasd  move   ·   enter  copy   ·   f  edit   ·   /  command   ·   q  quit"

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
        name = raw.strip().lstrip("/").strip().lower()
        if not name:
            return
        if name in ("q", "quit", "exit"):
            self.exit()
            return
        screen = _COMMANDS.get(name)
        if screen is None:
            self.set_status(f"Unknown command: /{name}")
            return
        self.push_screen(screen(), self.refresh_grid)


def main() -> None:
    LatticeApp().run()


if __name__ == "__main__":
    main()


# Make the stylesheet path absolute regardless of working directory.
LatticeApp.CSS_PATH = str(Path(__file__).resolve().parent / "styles.tcss")
