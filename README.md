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

A cell can also be a **formula** instead of a plain value — flagged with a
small `ƒ` marker and a teal rule. Copying one asks for a whole number and
copies the computed result instead of a fixed string (see below).

Lattice checks for updates in the background on launch — it never blocks
what you're doing. If a newer version is out, a small indicator next to the
app name walks through **checking for update** → **downloading update** →
**installing update** → **relaunch to update**. That last one sticks around:
close and reopen Lattice whenever you're ready, and the new version loads.
Your grid is never touched by an update.

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

### Commands (type after `/`)

Pressing `/` opens a command bar with an **autocomplete menu** above it, listing
every command. Keep typing to filter it; `↑`/`↓` move the highlight, `Tab`
completes to the highlighted command, `Enter` runs it, `Esc` closes. You can
also click an entry.

| Command | What it does |
|---------|--------------|
| `/add` | Add a new row or column. Asks for a name, then walks you through each field. Press **Ctrl+F** on a value step to make that field a formula instead (see below). |
| `/remove` | Hide a row or column. After you choose, a small **Yes / No** popup opens on top to confirm. Nothing is deleted — it is only removed from view, so it can come back later via `/undo`. |
| `/mass` | Update many cells of one row or column in order. Type each new value and press `Enter`; an **empty line finishes** and saves. |
| `/move` | Reorder rows and columns (see **Move mode** below). |
| `/rename` | Rename a row or column header (see **Rename mode** below). |
| `/undo` | Undo the last change (edit, clear, add, hide, or mass update). Can be repeated to step further back. |
| `/visible` | Reveal **all** values for **1 minute**, then they re-mask automatically. (To peek a single cell instead, hold `V`.) |
| `/visible N` | Reveal for `N` minutes instead (e.g. `/visible 5`). |
| `/hide` | Re-mask values immediately, before the timer runs out. |
| `/update` | Check for an update right now (same check that runs at launch). If one's already downloaded and waiting, this restarts Lattice instead to pick it up. |
| `/reload` | Restart Lattice in place — same window, fresh process. |

### Formula cells

While entering a value in `/add` (or editing an existing formula cell with
`E`), press **Ctrl+F** to make that field a formula instead of a fixed value.
Two ways to build it:

- **Step-by-step:** choose whether it has a **prefix**, a **suffix**,
  **both**, or **none** — static text glued to the start and/or end of the
  result — then type the **formula** using `INPT` for the number you'll
  supply later, and the four basic operators `+ - * /` (integers only; `/`
  rounds down).
- **Simple (one line):** pick "Simple: prefix(formula)suffix" and type it
  all at once, e.g. `asd(INPT * 2 * 3)zxc` — everything inside the
  parentheses is the formula, everything outside is prefix/suffix.

Example: prefix `asd`, suffix `zxc`, formula `INPT * 2 * 10`. Copying that
cell (`Enter` / `Ctrl+C`) asks for `INPT`'s value — enter `5` and `asd100zxc`
lands on your clipboard. The formula and its static parts stay masked like
any other value until revealed with `/visible`.

---

## Installation

Requires **Python 3.10+** on Windows.

1. Open a terminal in the project folder (`Lattice`).
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

---

## Project layout

```
Lattice/
├─ Lattice.pyw          Double-click launcher (opens a terminal, then runs)
├─ make_shortcut.ps1    Creates the Start Menu shortcut
├─ requirements.txt
├─ grid.dat             The encoded store (created at runtime; git-ignored)
└─ lattice/
   ├─ app.py            App shell: top bar, grid, command bar, status line
   ├─ widgets.py        The editable grid, cells, and box input
   ├─ screens.py        /add, /remove, /mass, formula modal flows
   ├─ models.py         Grid / Column / Row data model
   ├─ store.py          Load & atomic auto-save
   ├─ codec.py          Reversible byte mangling for the store
   ├─ formula.py        Safe INPT / + - * / evaluator for formula cells
   ├─ updater.py        Background self-update from GitHub releases
   └─ seed.py           One-shot importer from a plain-text table
```
