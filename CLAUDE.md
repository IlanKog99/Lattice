# CLAUDE.md — Lattice

Guidance for any AI or human working in this repository.

## What this is

A Textual (Python) terminal app that manages a grid of labelled cells. The grid
is held on disk in an **encoded, non-readable store** (`grid.dat`) and is only
ever decoded into plain text **in memory** at runtime. The on-disk file must
never contain readable content.

This is **security through obscurity**, by deliberate choice — not real
cryptography. The goal is simply that the data file is opaque and not greppable.
Do not add unlock prompts, key derivation, or claims of real security.

## Hard rules — do not break these

1. **No plaintext values anywhere in the repo** except inside the opaque
   `grid.dat`. Real cell values must never appear in source, comments, docs,
   tests, commit messages, or example output. Use obvious dummy placeholders in
   examples.
2. **The store is decoded in memory only.** Never write a readable form of the
   data to disk, not even temporarily. The only on-disk artifact is the encoded
   `grid.dat` (and its `.tmp` during an atomic save).
3. **Auto-save on every change.** Any mutation that touches the store (edit,
   `/add`, `/remove`, `/mass`) must call `app.persist()` immediately. There is
   no manual save.
4. **Nothing is truly deleted.** `/remove` only sets a `hidden` flag on a row or
   column; the data stays in the store. `/remove` asks for Yes/No confirmation
   first. Every mutation calls `app.push_undo()` *before* changing the grid so
   `/undo` can roll it back (in-session only; the undo stack isn't persisted).
5. **`grid.dat` is git-ignored** and must stay that way.
6. **Neutral vocabulary.** Keep the domain language generic (grid, cell, value,
   label, column, row, entry). Avoid framing the contents as credentials in
   code, comments, or docs.

## Architecture

| File | Responsibility |
|------|----------------|
| `Lattice.pyw` | Double-click launcher. Re-spawns into a real terminal because a TUI can't draw under windowless `pythonw`. |
| `lattice/app.py` | `LatticeApp`: top bar, grid, command bar, status line, command dispatch, `persist()`. |
| `lattice/widgets.py` | `GridView` (navigation, copy, in-place edit via `e`, find mode via `f`), `Cell`, `BoxInput`, `CommandInput`, `FindInput`. Find matches the label column and highlights matches with the `match` class (teal), separate from the `sel` cursor (ember). |
| `lattice/screens.py` | `StepModal` base (choice/text steps, key legend, `b`-to-go-back via a history stack) plus `AddScreen`, `RemoveScreen`, `MassScreen`. `ConfirmScreen` is a separate yes/no popup pushed on top for `/remove` (dismisses with `"yes"`/`"no"`/`"back"`/`"cancel"`). |
| `lattice/models.py` | `Grid` / `Column` / `Row` dataclasses, visibility views, and mutations. |
| `lattice/store.py` | `load()` and atomic `save()` through the codec. `DATA_FILE` lives in the project root. |
| `lattice/codec.py` | `pack()` / `unpack()`: utf-8 → zlib → rolling XOR → base85. The reversible mangling. Changing `_MASK` or `_TAG` invalidates existing stores. |
| `lattice/seed.py` | One-shot importer from a pipe-delimited plain-text table. Reads the source at runtime; never embeds it. |

Data model: column 0 is the label column; columns 1+ are value columns. Every
row's `cells` list is kept exactly as wide as `columns` by `Grid.normalise()`.

## Conventions

- Body swaps inside modals are deferred via `call_after_refresh` so the widget
  tree is never rebuilt from inside the event that triggered the step.
- `Screen` already defines `name` and `title`; don't shadow them on modal
  subclasses (use `entry_name`, `title_text`, etc.).
- New slash commands: add an entry to `_COMMANDS` in `app.py` and a
  `StepModal` subclass in `screens.py`. Commands that aren't modals (e.g.
  `/visible`, `/hide`, `/undo`, `/move`) are handled inline in
  `LatticeApp.run_command`.
- Move mode (`/move`) lives in `GridView`: it snapshots the grid on entry,
  reorders live as the user grabs (space) and nudges rows/columns, then either
  keeps the change (pushing the snapshot onto the undo stack) or restores the
  snapshot on cancel. Both exits confirm via `ConfirmScreen`.
- Value cells are **masked by default**. `app.revealed` plus a single timer
  drive a global reveal (`/visible [minutes]`, default 1); `Cell.show()` mirrors
  that state. Labels are never masked. Copy and edit always use the real value,
  so revealing is never required to copy.

## Testing

There are no committed tests (the smoke tests live outside the repo to avoid
embedding data). When testing flows with `App.run_test`, **redirect
`store.DATA_FILE` to a temp copy first** so the real store is never written.

## Run

```powershell
python -m pip install -r requirements.txt
python -m lattice            # or double-click Lattice.pyw
```
