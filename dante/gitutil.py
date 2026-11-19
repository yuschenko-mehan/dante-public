"""Git helpers: every Architect step becomes one commit, so any step can be undone.

Works only with Git installed. Without Git the Architect still runs, but without undo.
DANTE commits are marked with the prefix "[dante]" — undo never goes past a non-DANTE commit.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

PREFIX = "[dante]"


def available() -> bool:
    return shutil.which("git") is not None


_BUSY = ("index.lock", "permission denied", "unable to create", "unable to write", "resource busy", "being used by another process")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git; retry up to 3 times when a file is briefly locked (antivirus, heavy load on Windows).
    Запустити git; до 3 повторів, якщо файл на мить заблокований (антивірус, велике навантаження у Windows)."""
    for attempt in range(3):
        r = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        busy = any(b in (r.stderr or "").lower() for b in _BUSY)
        if r.returncode == 0 or not busy or attempt == 2:
            return r
        time.sleep(0.5 * (attempt + 1))
    return r


def ensure_repo(root: Path) -> bool:
    """Make `root` a git repository (with a first commit) if it is not one yet."""
    if not available():
        return False
    if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        _git(root, "init")
        _exclude_local(root)
        _git(root, "config", "user.name", "DANTE")
        _git(root, "config", "user.email", "dante@localhost")
        _git(root, "add", "-A")
        _git(root, "commit", "--allow-empty", "-m", f"{PREFIX} start: project state before DANTE")
    elif not _git(root, "config", "user.name").stdout.strip():
        _git(root, "config", "user.name", "DANTE")
        _git(root, "config", "user.email", "dante@localhost")
    _exclude_local(root)
    return True


def _exclude_local(root: Path, patterns: tuple[str, ...] = ("graphify-out/",)) -> None:
    """Keep DANTE's own helper folders out of git without touching the user's .gitignore.
    Не пускати в git службові теки Данте, не чіпаючи .gitignore користувача."""
    try:
        top = _git(root, "rev-parse", "--git-dir").stdout.strip()
        if not top:
            return
        ex = (Path(root) / top / "info" / "exclude") if not Path(top).is_absolute() else Path(top) / "info" / "exclude"
        ex.parent.mkdir(parents=True, exist_ok=True)
        old = ex.read_text(encoding="utf-8") if ex.exists() else ""
        add = [p for p in patterns if p not in old.splitlines()]
        if add:
            ex.write_text(old + ("" if old.endswith("\n") or not old else "\n") + "\n".join(add) + "\n", encoding="utf-8")
    except OSError:
        pass


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
