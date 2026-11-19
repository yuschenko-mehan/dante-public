"""Graphify project map access.
Доступ до карти проєкту Graphify.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

GRAPHIFY = [sys.executable, "-m", "graphify"]  # works even when Scripts/ is not on PATH (Store Python) / працює навіть коли Scripts/ немає в PATH


def available() -> bool:
    """Return True if graphify is installed.
    Повернути True, якщо graphify встановлено."""
    return importlib.util.find_spec("graphify") is not None


def refresh(root: Path, run=subprocess.run, timeout: int = 120) -> bool:
    """Update Graphify graph for root.
    Оновити граф Graphify для кореня."""
    try:
        res = run(
            GRAPHIFY + ["update", "."],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return res.returncode == 0 and (root / "graphify-out" / "graph.json").exists()
    except Exception:
        return False


def context(
    root: Path,
    query: str,
    budget_tokens: int = 1500,
    run=subprocess.run,
    timeout: int = 120,
) -> str:
    """Get project map context using Graphify query.
    Отримати контекст карти проєкту за допомогою запиту Graphify."""
    if not refresh(root, run=run, timeout=timeout):
        return ""
    try:
        res = run(
            GRAPHIFY + ["query", query, "--budget", str(budget_tokens)],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return ""
        text = "PROJECT MAP (Graphify: functions, files, line numbers, calls):\n" + res.stdout.strip()
        max_chars = budget_tokens * 4
        return text[:max_chars]
    except Exception:
        return ""

