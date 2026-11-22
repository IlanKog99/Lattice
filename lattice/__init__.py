"""Lattice — a terminal grid manager.

A small TUI for keeping a grid of labelled cells. The on-disk store is
encoded and sealed to the current Windows user (DPAPI) and is only ever
expanded into plain text inside memory while the app is running.
"""

__version__ = "1.6.0"
APP_NAME = "Lattice"
