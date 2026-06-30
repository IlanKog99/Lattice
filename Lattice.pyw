"""Double-click launcher for Lattice.

A ``.pyw`` runs under ``pythonw`` with no console attached, but Lattice is a
terminal app and needs somewhere to draw. So: if we already have a real
terminal, run in place; otherwise open a fresh console window (Windows
Terminal when available, a classic console otherwise) and run there.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _has_terminal() -> bool:
    try:
        return bool(sys.stdout) and sys.stdout.isatty()
    except Exception:
        return False


def _console_python() -> str:
    """The console interpreter that matches the current (windowless) one."""
    here = Path(sys.executable)
    candidate = here.with_name("python.exe")
    return str(candidate if candidate.exists() else here)


def _launch_in_console() -> None:
    python = _console_python()
    terminal = shutil.which("wt.exe")
    if terminal:  # Windows Terminal: nicer colours and unicode
        subprocess.Popen(
            [terminal, "-d", str(ROOT), python, "-m", "lattice"],
            cwd=str(ROOT),
        )
    else:  # classic console window
        CREATE_NEW_CONSOLE = 0x00000010
        subprocess.Popen(
            [python, "-m", "lattice"],
            cwd=str(ROOT),
            creationflags=CREATE_NEW_CONSOLE,
        )


def main() -> None:
    sys.path.insert(0, str(ROOT))
    if _has_terminal():
        from lattice.app import main as run
        run()
    else:
        _launch_in_console()


if __name__ == "__main__":
    main()
