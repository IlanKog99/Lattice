# CLAUDE.md — Lattice

Guidance for any AI or human working in this repository.

## What this is

A Textual (Python) terminal app that manages a grid of labelled cells. The grid
is held on disk in an **encoded, sealed store** (`grid.dat`) and is only ever
decoded into plain text **in memory** at runtime. The on-disk file must never
contain readable content.

`grid.dat` is sealed with **Windows DPAPI** for the current Windows user
(`DP1:` prefix). There is no unlock prompt: Windows opens it for the logged-in
account and nobody else. Older unsealed stores still open and are re-saved
sealed on first load. To move a grid to another PC or user, `/export` writes a
passphrase-protected `LX1:` file (scrypt + AES-GCM) and `/import` reads it. Do
not add prompts to normal use.

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
   label, column, row, entry, seed, code). Never describe the contents as
   anything sensitive in code, comments, docs, or commit messages.

## Architecture

| File | Responsibility |
|------|----------------|
| `Lattice.pyw` | Double-click launcher. Re-spawns into a real terminal because a TUI can't draw under windowless `pythonw`. |
| `lattice/app.py` | `LatticeApp`: top bar, grid, command bar, status line, command dispatch, `persist()`. |
| `lattice/widgets.py` | `GridView` (navigation, copy, in-place edit via `e`, find mode via `f`), `Cell`, `BoxInput`, `CommandInput`, `FindInput`. Find matches the label column and highlights matches with the `match` class (teal), separate from the `sel` cursor (ember). |
| `lattice/screens.py` | `StepModal` base (choice/text steps, key legend, `b`-to-go-back via a history stack) plus `AddScreen`, `RemoveScreen`, `MassScreen`, `FormulaScreen`, `FormulaPromptScreen`. `ConfirmScreen` is a separate yes/no popup pushed on top for `/remove` (dismisses with `"yes"`/`"no"`/`"back"`/`"cancel"`). |
| `lattice/models.py` | `Grid` / `Column` / `Row` dataclasses, visibility views, mutations, and the `is_formula` / `is_code_cell` / `cell_text` helpers for the three cell kinds. |
| `lattice/store.py` | `load()` (upgrades a legacy store to sealed `DP1:`; if that write fails the grid still loads and the upgrade retries next load; raises `ForeignStoreError` for another user's file, `ValueError` for other unreadable data) and verified atomic `save()`. `DATA_FILE` lives in the project root. |
| `lattice/codec.py` | `pack()` / `unpack()`: utf-8 → zlib → rolling XOR → base85 (legacy form, unchanged). `seal()` / `open_blob()` add the DPAPI layer (`DP1:`). Changing `_MASK` or `_TAG` invalidates existing stores. |
| `lattice/dpapi.py` | `protect()` / `unprotect()` via `ctypes` → `crypt32`. CurrentUser scope, fixed app entropy. |
| `lattice/vault_io.py` | `/export` / `/import` file format (`LX1:`): passphrase → scrypt → AES-GCM. `cryptography` is imported lazily, so the app runs without it. `/import` also accepts the old unsealed export format, with no passphrase. |
| `tests/` | stdlib `unittest` suite (`python -m unittest -v`). Dummy data only. |
| `lattice/formula.py` | Safe `+ - * /` / `INPT` evaluator for formula cells, parsed with `ast` (never `eval()`). |
| `lattice/updater.py` | `check_for_update()` (read-only GitHub Releases check against `__version__`) and `apply_update()` (download, overlay, best-effort `pip install`; only ever run by `/update`). See Conventions below. |
| `lattice/code_engine.py` | Time-stepped code generation for code cells (`{"kind": "code", "seed"}`): the cell stores a base32 seed, the 6-digit code is derived from seed + clock on every render and copy and is never stored. `Grid.normalise()` upgrades code cells saved under an older spec by shape, not by name. |
| `lattice/seed.py` | One-shot importer from a pipe-delimited plain-text table. Reads the source at runtime; never embeds it. |

Data model: column 0 is the label column; columns 1+ are value columns. Every
row's `cells` list is kept exactly as wide as `columns` by `Grid.normalise()`.
A cell holds either a plain string, or a **formula spec** — a
`{"prefix", "suffix", "formula"}` dict — distinguished by `models.is_formula()`.

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
- Rename mode (`/rename`) also lives in `GridView`: the cursor is constrained to
  the header cells (top row + label column) and `r` edits the selected header in
  place. Header cells are `Cell` widgets too (`header=True`, never masked);
  `is_label` is kept separate so only column 0 draws the divider border.
- `LatticeApp.persist()` also flashes the top-bar `#saving` indicator (a spinner
  interval plus a lingering hide timer).
- Value cells are **masked by default**. `app.revealed` plus a single timer
  drive a global reveal (`/visible [minutes]`, default 1); `Cell.show()` mirrors
  that state. Labels are never masked. Copy and edit always use the real value,
  so revealing is never required to copy.
- Formula cells: while entering a value in `/add` (or editing an existing
  formula cell with `e`), `Ctrl+F` opens `FormulaScreen` to build a
  `{prefix, suffix, formula}` spec instead of a plain string, either
  step-by-step (prefix/suffix/both/none, then the formula) or in one line via
  `formula.parse_simple("prefix(formula)suffix")` — bracket-depth matched, so
  a formula that itself contains parens still parses correctly. `formula.py`
  parses the formula with `ast` — only `INPT`, integer literals, and
  `+ - * /` are legal, so a user-typed formula can never execute arbitrary
  code. `/` is floor division so results always stay integers. Copying a
  formula cell pushes `FormulaPromptScreen` to ask for `INPT`'s value (with
  live integer validation) and copies `prefix + result + suffix`. `/mass`
  only ever writes plain strings, so mass-updating a formula cell downgrades
  it back to a string.
- Updates are **never installed automatically** (that would let whoever
  controls the release run code unasked). `on_mount` spawns
  `run_worker(self._check_for_update, thread=True)`, which only calls
  `updater.check_for_update()` (read-only: `"available" | "current" |
  "failed"`) plus the local `prune_stale()`. A `REMIND_INTERVAL` (24 h)
  interval re-runs the same check unless the user chose Ignore. A newer
  release pushes `UpdateScreen` (change log, GitHub link built from
  `OWNER`/`REPO`, "run /update"); remote text is rendered with
  `markup=False`. "Remind me later" (default focus) keeps the daily popup
  and sets the top-bar `#update` note; "Ignore"/Esc stops both until the
  next launch. `/update` is the only install path: `_run_update` checks,
  calls `updater.apply_update()` with spinner statuses, and on success
  calls `request_restart()`; on failure it shows "update failed" and does
  not restart. Any callback that touches a widget must go through
  `App.call_from_thread`. Every network, zip, filesystem, and subprocess
  call in `updater.py` catches its own failure and reports `None`/`False`
  rather than raising, and the app workers wrap everything in
  `try/except` — an exception escaping a worker tears the whole app down
  with a traceback, it is not merely logged. The install step
  replaces the `lattice/` package wholesale: it writes every file in the
  release, then deletes any file under `lattice/` the release doesn't ship.
  Nothing outside `lattice/` is ever deleted, which keeps `grid.dat` (root,
  gitignored, never in the release zip) safe. It copies added files before
  overwriting existing ones and prunes only after every copy landed, so a
  copy that dies partway still leaves an importable tree. At startup
  `prune_stale()` also removes modules older releases dropped (matched by
  content hash in `_RETIRED`) and bytecode with no source. `/reload`
  always restarts. Both go through `App.request_restart()` (sets
  `restart_requested`, calls `self.exit()`); `lattice.app.main()` checks
  that flag *after* `App.run()` returns and, if set, replaces the process
  with `os.execv(sys.executable, [sys.executable, "-m", "lattice"])` — same
  window, fresh interpreter, picks up whatever's now on disk.
- Read-only mode: if `store.load()` raises, `LatticeApp.read_only` holds the
  message and `persist()` refuses to write, so a store that couldn't be opened
  is never overwritten. A successful `/import` (`apply_import`) clears it.

## Testing

`python -m unittest -v` from the repo root runs `tests/`. Tests use dummy
placeholder data only and real DPAPI calls (Windows-only suite). Any test that
touches the store patches `store.DATA_FILE` to a temp dir first, and app tests
patch out the update check and What's New popup, so the real store and the
network are never touched. `tests/test_update_flow.py` mocks the check and
the install and asserts launch never downloads or installs.

## Run

```powershell
python -m pip install -r requirements.txt
python -m lattice            # or double-click Lattice.pyw
```

## Git

Every update (commit) must be pushed to `master` right after — no local-only
commits left behind.

## Release

Whenever `lattice/__init__.py`'s `__version__` is bumped and pushed, run
`./release.ps1` (local-only, gitignored, uses the already-signed-in `gh`
CLI) to tag and publish a matching GitHub release. The in-app updater only
ever sees tagged releases — a version bump without one is invisible to
users.

**Every version bump ships release notes.** Write
`release_notes/v<version>.md` (committed) before running `release.ps1`: plain
`* ` bullets, user-facing wording, neutral vocabulary (rule 6), no heading.
`release.ps1` publishes it as the GitHub release body, which is exactly what
`/new` (and the auto What's New popup) displays. `release.ps1` refuses to
release without it.
