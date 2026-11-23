"""One running copy of a program, guarded by an OS file lock (freed by the OS even after a crash or power loss).
Лише одна запущена копія програми: замок файлу ОС (ОС знімає його навіть після збою чи зникнення світла)."""
from __future__ import annotations

import os
from pathlib import Path


def acquire(path):
    """Lock `path`; return a handle, or None if another copy holds it.
    Замкнути `path`; повернути дескриптор або None, якщо його тримає інша копія."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    f = open(p, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    try:
        f.seek(0)
        f.truncate()
        f.write(str(os.getpid()).encode("ascii"))
        f.flush()
    except OSError:
        pass
    return f


def release(handle) -> None:
    """Free the lock; safe for None and for a second call.
    Зняти замок; безпечно для None і для повторного виклику."""
    if handle is None or handle.closed:
        return
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    handle.close()
