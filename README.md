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
| `F` | Edit the selected cell in place (`Enter` saves, `Esc` cancels) |
| `Del` | Clear the selected cell (same as editing it and deleting everything) |
| `/` | Open the command bar (`Enter` runs, `Esc` closes) |
| `Q` | Quit |

The label column (left) is never selectable. Every edit, clear, add, hide, or
mass update is **saved automatically** the moment it happens — there is no
separate "save" step. Changed something by mistake? Run `/undo`.

### Commands (type after `/`)

Pressing `/` opens a command bar with an **autocomplete menu** above it, listing
every command. Keep typing to filter it; `↑`/`↓` move the highlight, `Tab`
completes to the highlighted command, `Enter` runs it, `Esc` closes. You can
also click an entry.

| Command | What it does |
|---------|--------------|
| `/add` | Add a new row or column. Asks for a name, then walks you through each field. |
| `/remove` | Hide a row or column (asks **Yes / No** first). Nothing is deleted — it is only removed from view, so it can come back later via `/undo`. |
| `/mass` | Update many cells of one row or column in order. Type each new value and press `Enter`; an **empty line finishes** and saves. |
| `/undo` | Undo the last change (edit, clear, add, hide, or mass update). Can be repeated to step further back. |
| `/visible` | Reveal all values for **1 minute**, then they re-mask automatically. |
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
