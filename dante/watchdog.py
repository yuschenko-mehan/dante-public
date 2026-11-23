"""DANTE watchdog: a small separate part of DANTE that restarts the pult if it hangs or dies.
Сторож Данте: окрема маленька частина Данте, що перезапускає пульт, якщо той завис або зник.

    pythonw -m dante.watchdog        (the pult also starts it if it is missing / пульт сам запускає його)
Heartbeat: the pult touches C:\\DANTE\\outbox\\pult.heartbeat every round; pid in C:\\DANTE\\pult.pid.
Programs are started through explorer.exe, because Python from the Microsoft Store closes child processes
together with their parent. / Запуск через explorer.exe, бо Python із Microsoft Store закриває дочірні процеси.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from dante import single_instance
from dante import watchdog_logic as W

BASE = Path(__file__).resolve().parents[2]            # C:\DANTE
OUTBOX = BASE / "outbox"
HEARTBEAT = OUTBOX / "pult.heartbeat"
PID_FILE = BASE / "pult.pid"
WD_PID = BASE / "watchdog.pid"
WD_LOCK = BASE / "watchdog.lock"
LOG = OUTBOX / "watchdog.log"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def log(msg: str) -> None:
    try:
        OUTBOX.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def pid_alive(pid: int | None) -> bool:
    """Is a process with this id running? / Чи працює процес із цим номером?"""
    if not pid:
        return False
    if os.name == "nt":
        try:
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                               timeout=20, creationflags=NO_WINDOW)
            return str(pid) in r.stdout
        except (OSError, subprocess.SubprocessError):
            return True  # unknown -> do not restart / невідомо -> не перезапускати
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def start_detached(cmd_file: Path) -> None:
    """Start a .cmd outside our process family / Запустити .cmd поза нашою «родиною» процесів."""
    if os.name == "nt":
        subprocess.run(["explorer.exe", str(cmd_file)], creationflags=NO_WINDOW)
    else:
        subprocess.Popen(["sh", str(cmd_file)], start_new_session=True)


def restart_pult() -> None:
    """Stop every pult and start one new hidden pult / Зупинити всі пульти й запустити один новий."""
    if os.name == "nt":
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*-m dante.pult*' } | "
                        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                       capture_output=True, timeout=60, creationflags=NO_WINDOW)
    time.sleep(2)
    start_detached(BASE / "dante" / "pult-hidden.cmd")


def main() -> int:
    # Only one watchdog: the pult and the boot task may both start one. / Лише один сторож.
    lock = single_instance.acquire(WD_LOCK)
    if lock is None:
        log("another watchdog is already running - exiting / інший сторож уже працює - вихід")
        return 0
    try:
        WD_PID.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    log("watchdog started / сторож запущено")
    history: list[float] = []
    while True:
        time.sleep(60)
        now = time.time()
        verdict = W.check(now, mtime(HEARTBEAT), pid_alive(read_pid(PID_FILE)), limit_s=300)
        if verdict == "restart":
            if W.allow_restart(history, now, max_per_hour=4):
                history.append(now)
                log("pult silent or gone -> restart / пульт мовчить або зник -> перезапуск")
                try:
                    restart_pult()
                except Exception as e:  # keep watching / сторож не зупиняється
                    log(f"restart failed: {type(e).__name__}: {e}")
            else:
                log("too many restarts this hour - waiting / забагато перезапусків - чекаю")


if __name__ == "__main__":
    raise SystemExit(main())
