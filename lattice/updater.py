"""Update check and on-demand install from GitHub releases.

Nothing here runs code from the network on its own. At launch (and once a
day while the app is open) Lattice only *checks* whether a newer release
exists — `check_for_update()` reads release metadata and writes nothing to
disk. Downloading and installing happens solely when the user runs
`/update`, via `apply_update()`, after which the app relaunches itself.

Every network/filesystem/subprocess call here is best-effort: failures are
caught and reported as None/False rather than raised, so the caller (a
worker thread) never crashes the app.

The install replaces the `lattice/` package wholesale: every file the
release ships is written, and any file under `lattice/` the release doesn't
ship is deleted. Nothing outside `lattice/` is ever deleted, so grid.dat
(gitignored, never in the release zip, and living in the project root) is
always safe.
"""

from __future__ import annotations

import hashlib
import json
import re
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
    """{"tag_name", "zipball_url", "body"} for the latest release, or None."""
    try:
        req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "tag_name": data["tag_name"],
            "zipball_url": data["zipball_url"],
            "body": data.get("body") or "",
        }
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        return None


def release_page(version: str) -> str:
    """The GitHub page for `version`, built locally rather than taken from
    the API response."""
    return f"https://github.com/{OWNER}/{REPO}/releases/tag/v{version}"


def check_for_update() -> tuple[str, dict | None]:
    """Is a newer release out? Returns (state, update).

    state is "available" (update is {"version", "notes", "url",
    "zipball_url"}), "current", or "failed" (couldn't reach GitHub).
    Read-only: talks to the GitHub API and writes nothing to disk.
    """
    release = fetch_latest_release()
    if release is None:
        return "failed", None
    if not is_newer(release["tag_name"], __version__):
        return "current", None
    version = release["tag_name"].strip().lstrip("vV")
    return "available", {
        "version": version,
        "notes": format_release_notes(release["body"]),
        "url": release_page(version),
        "zipball_url": release["zipball_url"],
    }


def fetch_release_notes(version: str) -> str | None:
    """The release-notes body for the tag matching `version`, or None."""
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/v{version}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("body")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def format_release_notes(raw: str | None) -> str:
    """Light cleanup of GitHub's auto-generated release notes for display."""
    text = raw or ""
    text = re.sub(r"^#+\s*What's Changed\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*Full Changelog\*\*.*$", "", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r"\s+in https://\S+/pull/\d+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+by @\S+\b", "", text)
    text = re.sub(r"^\*\s+", "• ", text, flags=re.MULTILINE)
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines) if lines else "No notable changes."


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
    needed, then delete any file under `dest_dir/lattice` that the release
    doesn't ship (old modules, stale bytecode). Nothing outside `lattice/` is
    deleted, so grid.dat and other local files in the root are left alone.
    """
    files = [p for p in src_dir.rglob("*") if p.is_file()]
    # Added files first, overwrites second. If the copy dies partway (a locked
    # file, a full disk), what's left on disk still imports: a half-overlay
    # that only added a module nothing references yet is harmless, while one
    # that overwrote an import of a module not written yet is fatal.
    files.sort(key=lambda p: (dest_dir / p.relative_to(src_dir)).exists())
    for src_path in files:
        dest_path = dest_dir / src_path.relative_to(src_dir)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)

    # Prune only after every copy landed, and only against a release that
    # really contains the package -- a malformed zip must never empty it.
    src_pkg, dest_pkg = src_dir / "lattice", dest_dir / "lattice"
    if not (src_pkg / "__init__.py").is_file():
        return
    for dest_path in [p for p in dest_pkg.rglob("*") if p.is_file()]:
        if not (src_pkg / dest_path.relative_to(dest_pkg)).is_file():
            try:
                dest_path.unlink()
            except OSError:
                pass  # a leftover file is harmless; the new code is already in


# Content hashes (LF and CRLF) of modules earlier releases shipped and later
# ones dropped. Installs upgraded by the older, never-deleting overlay still
# carry them, and the overlay above only runs on the *next* update, so they're
# matched by content and removed at startup.
_RETIRED = {
    "9714f32b5e59635b74103f8a5e80b5876eec070879ce7296b163c7133f9602b9",
    "36e579544ca3689bdaba5346164658d17e8131c9a24d68200b6e6e5eb28b7c80",
}


def prune_stale(root: Path = PROJECT_ROOT) -> None:
    """Best-effort: delete retired modules and any bytecode whose source
    module no longer exists."""
    pkg = root / "lattice"
    try:
        stale = [p for p in pkg.glob("*.py") if hashlib.sha256(p.read_bytes()).hexdigest() in _RETIRED]
    except OSError:
        return
    stale += [
        p for p in pkg.glob("__pycache__/*.pyc")
        if not (pkg / f"{p.name.split('.')[0]}.py").is_file()
        or (pkg / f"{p.name.split('.')[0]}.py") in stale
    ]
    for path in stale:
        try:
            path.unlink()
        except OSError:
            pass


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


def apply_update(update: dict, on_status: Callable[[str | None], None]) -> bool:
    """Download and install `update` (from check_for_update). True on success.

    Only ever called from /update. Reports "downloading update" and
    "installing update" through `on_status`. The new code takes effect once
    the app relaunches.
    """
    _report(on_status, "downloading update")
    with tempfile.TemporaryDirectory(prefix="lattice_update_") as tmp:
        tmp_path = Path(tmp)
        zip_path = download_zip(update["zipball_url"], tmp_path)
        if zip_path is None:
            return False

        _report(on_status, "installing update")
        extracted = extract_and_strip(zip_path, tmp_path / "extracted")
        if extracted is None:
            return False

        try:
            overlay(extracted, PROJECT_ROOT)
        except OSError:
            return False
    pip_install()
    return True
