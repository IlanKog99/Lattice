"""Background self-updater: pulls the latest GitHub release and overlays it.

Every network/filesystem/subprocess call here is best-effort — this is a
background nicety, not a critical path, so failures are swallowed and simply
leave the app as it was (never crash, never block the running session).

Because the running process already has its modules loaded in memory,
overwriting the .py files on disk doesn't affect the current session at all.
The new code only takes effect the next time Lattice is launched, so there is
no in-process restart to orchestrate.

grid.dat is gitignored and therefore never present in the release zip, so an
additive overlay (write/overwrite, never delete-then-extract) protects it
without needing an explicit exclusion list.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from . import __version__

OWNER = "IlanKog99"
REPO = "Lattice"
API_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUEST_TIMEOUT = 10
STAGE_DELAY = 1.2  # keep each status visible long enough to actually read


def _report(on_status: Callable[[str | None], None], status: str | None) -> None:
    on_status(status)
    if status is not None:
        time.sleep(STAGE_DELAY)


def parse_version(tag: str) -> tuple[int, ...]:
    """"v1.2.3" -> (1, 2, 3). Raises ValueError if it doesn't look like a version."""
    text = tag.strip().lstrip("vV")
    parts = text.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a version tag: {tag!r}")
    return tuple(int(p) for p in parts)


def is_newer(remote_tag: str, local_version: str) -> bool:
    """True if `remote_tag` is a newer version than `local_version`.

    Never raises — an unparseable remote tag is treated as "not newer" so a
    malformed release can't break the update check.
    """
    try:
        return parse_version(remote_tag) > parse_version(local_version)
    except ValueError:
        return False


def fetch_latest_release() -> dict | None:
    """{"tag_name": ..., "zipball_url": ...} for the latest release, or None."""
    try:
        req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {"tag_name": data["tag_name"], "zipball_url": data["zipball_url"]}
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        return None


def download_zip(url: str, dest_dir: Path) -> Path | None:
    """Download `url` into `dest_dir`, return the file path, or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            blob = resp.read()
        path = dest_dir / "update.zip"
        path.write_bytes(blob)
        return path
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def extract_and_strip(zip_path: Path, dest_dir: Path) -> Path | None:
    """Extract `zip_path` into `dest_dir` and return the single top-level
    folder GitHub's zipball wraps everything in (or None on a bad archive)."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest_dir)
    except (zipfile.BadZipFile, OSError):
        return None
    children = [p for p in dest_dir.iterdir() if p.is_dir()]
    return children[0] if len(children) == 1 else dest_dir


def overlay(src_dir: Path, dest_dir: Path) -> None:
    """Copy every file from `src_dir` onto `dest_dir`, creating folders as
    needed. Never deletes anything — files absent from `src_dir` (like
    grid.dat, which is gitignored and so never appears here) are left alone.

    ponytail: overlay-only, so a file removed upstream lingers locally
    forever. Fine for now; revisit with a manifest-based prune if it bites.
    """
    for src_path in src_dir.rglob("*"):
        if src_path.is_dir():
            continue
        rel = src_path.relative_to(src_dir)
        dest_path = dest_dir / rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)


def pip_install() -> bool:
    """Best-effort `pip install -r requirements.txt`. True on success."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            timeout=120,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def run_update_check(
    on_status: Callable[[str | None], None], *, announce_current: bool = False
) -> None:
    """Check for and apply an update, reporting progress through `on_status`.

    Statuses: "checking for update", "downloading update", "installing
    update", "relaunch to update". If nothing changed (already current, or a
    step failed), calls `on_status(None)` — silent, for the automatic
    startup check — unless `announce_current` is set, in which case it
    reports "up to date" instead (used by the manual /update command, which
    should always give feedback).
    """
    _report(on_status, "checking for update")
    release = fetch_latest_release()
    if release is None or not is_newer(release["tag_name"], __version__):
        on_status("up to date" if announce_current else None)
        return

    _report(on_status, "downloading update")
    with tempfile.TemporaryDirectory(prefix="lattice_update_") as tmp:
        tmp_path = Path(tmp)
        zip_path = download_zip(release["zipball_url"], tmp_path)
        if zip_path is None:
            on_status(None)
            return

        _report(on_status, "installing update")
        extracted = extract_and_strip(zip_path, tmp_path / "extracted")
        if extracted is None:
            on_status(None)
            return

        overlay(extracted, PROJECT_ROOT)
        pip_install()

    _report(on_status, "relaunch to update")
