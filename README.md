# Lattice

A small, fast terminal app for keeping a grid of labelled cells. The grid lives
on disk in an **encoded, non-readable** store; it is only ever expanded into
plain text inside memory while the app is running. Open the data file in a text
editor and you'll see noise.

This is *obscurity, not security*. There is no master key and no real
encryption — the file is simply mangled so it isn't readable or greppable at a
glance. Don't rely on it to protect anything that truly matters.

```
  Region       Field A        Field B        Field C
  AA (000)     ··········     ··········     ··········
  BB (100)     ··········     ··········     ··········
  ...
```

The left column is the **label** column (a row name, like the headers — it is
never selectable and always shown). Every other column holds a free-form value.
The highlighted cell is the cursor.

The cursor's whole row is given a faint band so you can easily see which row
(and which label) the selected cell belongs to. Whatever value is currently on
your clipboard is also faintly highlighted wherever it appears in the grid.

**Values are masked (`••••••`) by default** and only shown on demand with
`/visible` (see below). Copying still works while masked — you never have to
reveal a value to copy it.

---

## Controls

| Key | Action |
|-----|--------|
| Arrow keys / `W` `A` `S` `D` | Move the cursor (wraps around at the edges) |
| Mouse click | Jump the cursor straight to a value cell |
| `Enter` or `Ctrl+C` | Copy the selected cell to the clipboard |
| `E` | Edit the selected cell in place (`Enter` saves, `Esc` cancels) |
| `F` or `Ctrl+F` | Find: jump to a row by typing part of its label (see below) |
| `V` (hold) | Peek: reveal just the selected cell while held; it re-masks shortly after you let go |
| `Del` | Clear the selected cell (same as editing it and deleting everything) |
| `Ctrl+Z` | Undo the last change (same as `/undo`) |
| `/` | Open the command bar (`Enter` runs, `Esc` closes) |
| `Q` | Quit |

The label column (left) is never selectable. Every edit, clear, add, hide, or
mass update is **saved automatically** the moment it happens — a small spinner
and "saving" flash next to the app name each time — there is no separate "save"
step. Changed something by mistake? Run `/undo`.

Every popup shows its keys along the bottom. On selection screens: arrow keys or
`W`/`S` move, `Enter` selects, `B` goes back a step, `Esc` cancels. On the
confirm popup: arrows or `A`/`D` switch buttons, `Enter` chooses, `B` returns to
the list, `Esc` cancels. (While typing a value, letters go into the field, so
back out of those with `Esc`.)

### Find mode (`F`)

Press `F` and start typing — Lattice matches your text against the **label
column** and highlights every matching row in teal (distinct from the ember
cursor). The cursor jumps to the first match's leftmost cell. `Tab` cycles to
the next match (`Shift+Tab` for the previous). `Enter` keeps the cursor on the
current match; `Esc` cancels and returns it to where you started.

Example: typing `ha` lands you on the `IL-HA` row.

### Move mode (`/move`)

`/move` lets you reorder rows and columns:

1. Move the cursor to the row/column you want and press **Space** to *grab* it.
   The grabbed row and column are tinted.
2. With it grabbed, `↑`/`↓` move that **row** up/down and `←`/`→` move that
   **column** left/right (`W`/`A`/`S`/`D` too). Press **Space** again to drop and
   grab a different one.
3. **Enter** saves (asks to confirm); **Esc** cancels (also asks). Cancelling
   puts everything back the way it was. A saved reorder can be reverted with
   `/undo`.

### Rename mode (`/rename`)

`/rename` moves the cursor onto the **headers** only — the column headers along
the top and the row labels down the left. Use the arrow keys or `W`/`A`/`S`/`D`
to move among them. Press **R** to edit the selected header (type the new text,
`Enter` saves, `Esc` cancels the edit). `Esc` while just navigating leaves
rename mode. No confirmation — renames save immediately (and are undoable).

### Commands (type after `/`)

Pressing `/` opens a command bar with an **autocomplete menu** above it, listing
every command. Keep typing to filter it; `↑`/`↓` move the highlight, `Tab`
completes to the highlighted command, `Enter` runs it, `Esc` closes. You can
also click an entry.

| Command | What it does |
|---------|--------------|
| `/add` | Add a new row or column. Asks for a name, then walks you through each field. |
| `/remove` | Hide a row or column. After you choose, a small **Yes / No** popup opens on top to confirm. Nothing is deleted — it is only removed from view, so it can come back later via `/undo`. |
| `/mass` | Update many cells of one row or column in order. Type each new value and press `Enter`; an **empty line finishes** and saves. |
| `/move` | Reorder rows and columns (see **Move mode** below). |
| `/rename` | Rename a row or column header (see **Rename mode** below). |
| `/undo` | Undo the last change (edit, clear, add, hide, or mass update). Can be repeated to step further back. |
| `/visible` | Reveal **all** values for **1 minute**, then they re-mask automatically. (To peek a single cell instead, hold `V`.) |
| `/visible N` | Reveal for `N` minutes instead (e.g. `/visible 5`). |
| `/hide` | Re-mask values immediately, before the timer runs out. |

---

## Installation

Requires **Python 3.10+** on Windows.

1. Open a terminal in the project folder (`PassesTUI`).
2. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. (First time only) Seed the store from an existing plain-text table:

   ```powershell
   python -m lattice.seed path\to\your_table.txt
   ```

   The plain text is read only at that moment and is never stored in the
   program. Once seeded, you can delete the readable source file — the app
   reads only the encoded `grid.dat` from then on. You can also skip seeding
   entirely and build the grid from scratch with `/add`.

4. Run it:

   ```powershell
   python -m lattice
   ```

   or double-click **`Lattice.pyw`**.

> **Why does double-clicking open a new terminal window?**
> Lattice draws in a terminal. A `.pyw` runs without a console, so the launcher
> opens a fresh terminal window for you and runs there. If you start it from an
> existing terminal, it runs right in place.

---

## Create a Windows Start Menu shortcut

You can launch Lattice from the Start Menu like any installed app.

### The easy way (script)

From a PowerShell prompt in the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\make_shortcut.ps1
```

This creates **`Lattice.lnk`** in your Start Menu
(`%AppData%\Microsoft\Windows\Start Menu\Programs`). Press the Windows key and
type "Lattice" to find it.

### The manual way

1. Press `Win+R`, type `shell:programs`, press Enter. The Start Menu *Programs*
   folder opens.
2. Right-click → **New → Shortcut**.
3. For the location, enter (adjust the path to your machine):

   ```
   "C:\Program Files\PyManager\pythonw.exe" "C:\Users\<you>\Documents\PassesTUI\Lattice.pyw"
   ```

   Use the path to *your* `pythonw.exe` — find it with `(Get-Command pythonw).Source`.
4. Name it **Lattice** and click Finish.
5. (Optional) Right-click the new shortcut → **Properties** → set **Start in**
   to the `PassesTUI` folder.

---

## Project layout

```
PassesTUI/
├─ Lattice.pyw          Double-click launcher (opens a terminal, then runs)
├─ make_shortcut.ps1    Creates the Start Menu shortcut
├─ requirements.txt
├─ grid.dat             The encoded store (created at runtime; git-ignored)
└─ lattice/
   ├─ app.py            App shell: top bar, grid, command bar, status line
   ├─ widgets.py        The editable grid, cells, and box input
   ├─ screens.py        /add, /remove, /mass modal flows
   ├─ models.py         Grid / Column / Row data model
   ├─ store.py          Load & atomic auto-save
   ├─ codec.py          Reversible byte mangling for the store
   └─ seed.py           One-shot importer from a plain-text table
```
