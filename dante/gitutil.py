"""Git helpers: every Architect step becomes one commit, so any step can be undone.

Works only with Git installed. Without Git the Architect still runs, but without undo.
DANTE commits are marked with the prefix "[dante]" — undo never goes past a non-DANTE commit.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PREFIX = "[dante]"


def available() -> bool:
    return shutil.which("git") is not None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def ensure_repo(root: Path) -> bool:
    """Make `root` a git repository (with a first commit) if it is not one yet."""
    if not available():
        return False
    if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        _git(root, "init")
        _git(root, "config", "user.name", "DANTE")
        _git(root, "config", "user.email", "dante@localhost")
        _git(root, "add", "-A")
        _git(root, "commit", "--allow-empty", "-m", f"{PREFIX} start: project state before DANTE")
    elif not _git(root, "config", "user.name").stdout.strip():
        _git(root, "config", "user.name", "DANTE")
        _git(root, "config", "user.email", "dante@localhost")
    return True


def commit(root: Path, message: str) -> str | None:
    """Commit everything; returns the short commit id, or None if nothing changed / no git."""
    if not available():
        return None
    _git(root, "add", "-A")
    r = _git(root, "commit", "-m", f"{PREFIX} {message}")
    if r.returncode != 0:
        return None
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def last_message(root: Path) -> str:
    return _git(root, "log", "-1", "--pretty=%s").stdout.strip()


def undo_last(root: Path) -> str:
    """Undo the last DANTE step (only if the last commit is DANTE's and is not the start commit)."""
    if not available():
        return "Git is not installed: undo is not possible."
    msg = last_message(root)
    if not msg.startswith(PREFIX) or msg.startswith(f"{PREFIX} start:"):
        return "Nothing to undo: the last change was not a DANTE step."
    r = _git(root, "reset", "--hard", "HEAD~1")
    if r.returncode != 0:
        return "Undo failed: " + r.stderr.strip()[:300]
    return f"Undone: {msg[len(PREFIX):].strip()}"


def history(root: Path, n: int = 20) -> list[str]:
    out = _git(root, "log", f"-{n}", "--pretty=%h %ad %s", "--date=format:%Y-%m-%d %H:%M").stdout
    return [line for line in out.splitlines() if PREFIX in line]
