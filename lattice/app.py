"""The Lattice application: top bar, grid, command bar, and status line."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pyperclip
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from . import APP_NAME, store, updater
from .screens import AddScreen, ConfirmScreen, MassScreen, RemoveScreen
from .widgets import CommandInput, FindInput, GridView

def _k(key: str, label: str) -> str:
    return f"[#ff6a3d b]{key}[/] [#aeb8c4]{label}[/]"


HINTS = "   ".join(
    [
        _k("↑↓←→/wasd", "move"),
        _k("enter/ctrl+c", "copy"),
        _k("e", "edit"),
        _k("f", "find"),
        _k("v", "peek"),
        _k("del", "clear"),
        _k("ctrl+z", "undo"),
        _k("/", "commands"),
        _k("q", "quit"),
    ]
)

MOVE_HINTS = "   ".join(
    [
        "[#ff6a3d b]MOVE MODE[/]",
        _k("wasd/arrows", "cursor"),
        _k("space", "grab/drop"),
        _k("arrows", "reorder"),
        _k("enter", "save"),
        _k("esc", "cancel"),
    ]
)

RENAME_HINTS = "   ".join(
    [
        "[#ff6a3d b]RENAME MODE[/]",
        _k("wasd/arrows", "headers"),
        _k("r", "edit"),
        _k("enter", "save"),
        _k("esc", "exit"),
    ]
)

DEFAULT_REVEAL_MINUTES = 1
MAX_REVEAL_MINUTES = 600
UNDO_DEPTH = 100

# cli-spinners "dots2" and "bouncingBall" frame sets (80ms/frame in the
# original spec) — saving uses dots2, the background updater uses the ball.
DOTS_FRAMES = "⣾⣽⣻⢿⡿⣟⣯⣷"
BALL_FRAMES = (
    "( ●    )", "(  ●   )", "(   ●  )", "(    ● )", "(     ●)",
    "(    ● )", "(   ●  )", "(  ●   )", "( ●    )", "(●     )",
)
SPINNER_INTERVAL = 0.08

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
    ("move", "Reorder rows and columns"),
    ("rename", "Rename a row or column header"),
    ("undo", "Undo the last change"),
    ("visible", "Reveal values (e.g. /visible 5)"),
    ("hide", "Mask values now"),
    ("update", "Check for an update now"),
    ("reload", "Restart Lattice"),
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
        self._save_frame = 0
        self._save_anim = None
        self._save_hide = None
        self._update_frame = 0
        self._update_anim = None
        self._update_text = ""
        self._update_ready = False
        self.restart_requested = False

    # --- layout --------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static(
                f"[b]{APP_NAME}[/b]\n[dim]a quiet little grid keeper[/dim]",
                id="appname",
            )
            yield Static("", id="saving")
            yield Static("", id="update")
        yield GridView(id="grid")
        yield Static(HINTS, id="status")
        with Vertical(id="findbar"):
            yield Static(
                "[#7d8b95]type to match labels[/]   ·   "
                "[#56c5d6 b]Tab[/] [#7d8b95]next[/]   ·   "
                "[#56c5d6 b]Shift+Tab[/] [#7d8b95]prev[/]   ·   "
                "[#56c5d6 b]Enter[/] [#7d8b95]keep[/]   ·   "
                "[#56c5d6 b]Esc[/] [#7d8b95]cancel[/]",
                id="findhint",
            )
            with Horizontal(id="findrow"):
                yield Static("find ›", id="findprompt")
                yield FindInput(id="findinput")
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
        self.set_interval(1.0, self._poll_clipboard)
        self.run_worker(self._check_for_update, thread=True)

    # --- background self-update -----------------------------------------
    def _check_for_update(self) -> None:
        updater.run_update_check(self._set_update_status)

    def _check_for_update_manual(self) -> None:
        updater.run_update_check(self._set_update_status, announce_current=True)

    def cmd_update(self) -> None:
        """/update — manual check; restarts instead if one's already staged."""
        if self._update_ready:
            self.request_restart()
            return
        self.run_worker(self._check_for_update_manual, thread=True)

    def request_restart(self) -> None:
        """/reload, and /update once an update is staged: relaunch in place."""
        self.restart_requested = True
        self.exit()

    def _set_update_status(self, status: str | None) -> None:
        self.call_from_thread(self._show_update_status, status)

    def _show_update_status(self, status: str | None) -> None:
        indicator = self.query_one("#update", Static)
        if status is None:
            indicator.display = False
            if self._update_anim is not None:
                self._update_anim.stop()
                self._update_anim = None
            return
        indicator.display = True
        if status in ("relaunch to update", "up to date"):
            if self._update_anim is not None:
                self._update_anim.stop()
                self._update_anim = None
            self._update_ready = status == "relaunch to update"
            indicator.update(f"[#2a7d8c]✓[/] [#6b7787]{status}[/]")
            if status == "up to date":
                self.set_timer(2.0, lambda: setattr(indicator, "display", False))
            return
        self._update_text = status
        if self._update_anim is None:
            self._update_anim = self.set_interval(SPINNER_INTERVAL, self._update_spin)
        self._update_spin()

    def _update_spin(self) -> None:
        frame = BALL_FRAMES[self._update_frame % len(BALL_FRAMES)]
        self._update_frame += 1
        try:
            self.query_one("#update", Static).update(f"[#2a7d8c]{frame}[/] [#6b7787]{self._update_text}[/]")
        except Exception:  # noqa: BLE001 - widget gone during shutdown
            pass

    # --- clipboard match -----------------------------------------------
    def _poll_clipboard(self) -> None:
        try:
            text = pyperclip.paste()
            gv = self.grid_view
        except Exception:  # noqa: BLE001 - no clipboard backend, or shutting down
            return
        if text != gv._clip:
            gv.mark_clipboard(text)

    # --- grid helpers --------------------------------------------------
    @property
    def grid_view(self) -> GridView:
        return self.query_one(GridView)

    def persist(self) -> None:
        """Auto-save: called after every change that touches the store."""
        store.save(self.grid)
        self._show_saving()

    # --- auto-save indicator -------------------------------------------
    def _show_saving(self) -> None:
        indicator = self.query_one("#saving", Static)
        indicator.display = True
        if self._save_anim is None:
            self._save_anim = self.set_interval(SPINNER_INTERVAL, self._spin)
        self._spin()
        if self._save_hide is not None:
            self._save_hide.stop()
        # linger a beat after the last save so the user notices it
        self._save_hide = self.set_timer(1.0, self._hide_saving)

    def _spin(self) -> None:
        frame = DOTS_FRAMES[self._save_frame % len(DOTS_FRAMES)]
        self._save_frame += 1
        try:
            self.query_one("#saving", Static).update(f"[#3fb950]{frame}[/] [#6b7787]saving[/]")
        except Exception:  # noqa: BLE001 - widget gone during shutdown
            pass

    def _hide_saving(self) -> None:
        try:
            self.query_one("#saving", Static).display = False
        except Exception:  # noqa: BLE001
            pass
        if self._save_anim is not None:
            self._save_anim.stop()
            self._save_anim = None
        self._save_hide = None

    # --- undo ----------------------------------------------------------
    def push_undo(self) -> None:
        """Snapshot the grid *before* a change, so /undo can roll it back."""
        from .models import Grid

        self.push_undo_state(Grid.from_dict(self.grid.to_dict()))

    def push_undo_state(self, grid) -> None:
        self._undo.append(grid)
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

    # --- move mode -----------------------------------------------------
    def enter_move(self) -> None:
        gv = self.grid_view
        if not gv.vrows or not gv.vcols:
            self.set_status("Nothing to move")
            return
        gv.enter_move()

    def enter_rename(self) -> None:
        gv = self.grid_view
        if not gv.vcols:
            self.set_status("Nothing to rename")
            return
        gv.enter_rename()

    def move_request_apply(self) -> None:
        self.push_screen(
            ConfirmScreen("Save the new order?"),
            lambda r: self.grid_view.finish_move(True) if r == "yes" else None,
        )

    def move_request_cancel(self) -> None:
        self.push_screen(
            ConfirmScreen("Discard changes and leave move mode?"),
            lambda r: self.grid_view.finish_move(False) if r == "yes" else None,
        )

    def refresh_grid(self, _result=None) -> None:
        self.grid_view.rebuild()
        self.grid_view.focus()

    def _base_hints(self) -> str:
        gv = self.grid_view
        if gv.move_mode:
            return MOVE_HINTS
        if gv.rename_mode:
            return RENAME_HINTS
        return HINTS

    def set_status(self, message: str | None = None) -> None:
        bar = self.query_one("#status", Static)
        base = self._base_hints()
        bar.update(message or base)
        if message:
            self.set_timer(2.6, lambda: bar.update(self._base_hints()))

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
        elif event.input.id == "findinput":
            self.grid_view.update_find(event.value)

    # --- find ----------------------------------------------------------
    def open_find(self) -> None:
        self.query_one("#findbar").display = True
        field = self.query_one("#findinput", FindInput)
        field.value = ""
        self.grid_view.start_find()
        field.focus()

    def _close_find(self, restore: bool) -> None:
        self.query_one("#findbar").display = False
        self.query_one("#findinput", FindInput).value = ""
        self.grid_view.clear_find(restore)
        self.grid_view.focus()

    def find_accept(self) -> None:
        self._close_find(restore=False)

    def find_cancel(self) -> None:
        self._close_find(restore=True)

    def find_next(self, delta: int) -> None:
        self.grid_view.find_next(delta)

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
        if name == "move":
            self.enter_move()
            return
        if name == "rename":
            self.enter_rename()
            return
        if name == "update":
            self.cmd_update()
            return
        if name == "reload":
            self.request_restart()
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
    app = LatticeApp()
    app.run()
    if app.restart_requested:
        # Textual has already restored the terminal by the time run()
        # returns, so it's safe to replace this process image in place --
        # same window, fresh code, no new console to manage.
        os.execv(sys.executable, [sys.executable, "-m", "lattice"])


if __name__ == "__main__":
    main()


# Make the stylesheet path absolute regardless of working directory.
LatticeApp.CSS_PATH = str(Path(__file__).resolve().parent / "styles.tcss")
