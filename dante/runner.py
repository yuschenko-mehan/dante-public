"""Run a build/test command and capture the result.

Stage 1: runs directly on this computer with a timeout.
Stage 3 will add a Docker sandbox without network access.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunResult:
    command: str
    exit_code: int
    output: str
    duration_s: float

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process with all its children (tests often start their own programs).
    Завершити процес разом з усіма дочірніми (тести часто запускають свої програми)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=0x08000000)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def safe_run(args, *, timeout=None, capture_output=False, text=False, encoding=None, errors=None,
             cwd=None, env=None, shell=False, creationflags=0, input=None):
    """Like subprocess.run, but a timeout kills the WHOLE process tree and never hangs on pipes
    that a grandchild still holds (a Windows trap). Raises subprocess.TimeoutExpired.
    Як subprocess.run, але при перевищенні часу вбиває ВСЕ дерево процесів і не зависає на каналах,
    які тримає «онук» (пастка Windows). Кидає subprocess.TimeoutExpired."""
    pipe = subprocess.PIPE if capture_output else None
    kw = dict(cwd=cwd, env=env, shell=shell, stdout=pipe, stderr=pipe,
              stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL)
    if text or encoding:
        kw.update(text=True, encoding=encoding, errors=errors)
    if os.name == "nt":
        kw["creationflags"] = creationflags
    else:
        kw["start_new_session"] = True
    proc = subprocess.Popen(args, **kw)
    try:
        out, err = proc.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:  # pipes still held: stop reading / канали ще зайняті: не читаємо
            for f in (proc.stdout, proc.stderr):
                try:
                    f and f.close()
                except OSError:
                    pass
            out = err = None
        raise subprocess.TimeoutExpired(args, timeout, output=out, stderr=err) from None
    return subprocess.CompletedProcess(args, proc.returncode, out, err)


def run_command(command: str, cwd: Path, timeout_s: int, max_output: int = 8000) -> RunResult:
    # Stop Python from writing .pyc caches: a rewritten file with the same size
    # and timestamp would otherwise be loaded from a stale cache.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    start = time.monotonic()
    try:
        p = safe_run(
            command,
            cwd=cwd,
            env=env,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        out = (p.stdout or "") + (p.stderr or "")
        code = p.returncode
    except subprocess.TimeoutExpired:
        out, code = f"TIMEOUT after {timeout_s}s", 124
    # Keep the end of the output: errors are usually there.
    if len(out) > max_output:
        out = "...[truncated]...\n" + out[-max_output:]
    return RunResult(command, code, out, round(time.monotonic() - start, 3))
