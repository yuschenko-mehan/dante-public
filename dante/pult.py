import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def load_job(path: Path, base: Path) -> dict:
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as e:
        raise ValueError(f"Bad JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("Job must be a JSON object")

    kind = data.get("kind")
    if kind not in ("dante", "cmd"):
        raise ValueError(f"Unknown or missing kind: {kind}")

    # Validate fields per kind
    if kind == "dante":
        if "args" not in data:
            raise ValueError("dante job requires 'args' field")
        args = data["args"]
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ValueError("dante job requires 'args' list of strings")
        command = ""
    else:  # cmd
        command = data.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("cmd job requires non-empty 'command' string")
        args = []

    # cwd handling
    cwd_val = data.get("cwd")
    base_resolved = base.resolve()
    if cwd_val is not None:
        cwd_path = Path(cwd_val)
        if cwd_path.is_absolute():
            resolved_cwd = cwd_path.resolve()
        else:
            resolved_cwd = (base_resolved / cwd_path).resolve()
    else:
        resolved_cwd = (base_resolved / "dante").resolve()

    try:
        resolved_cwd.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"cwd {resolved_cwd} is outside base {base_resolved}")

    # timeout handling
    timeout = data.get("timeout", 900)
    if not isinstance(timeout, int) or not (1 <= timeout <= 7200):
        raise ValueError(f"Invalid timeout: {timeout}")

    return {
        "kind": kind,
        "args": args,
        "command": command,
        "cwd": resolved_cwd,
        "timeout": timeout,
    }


def run_job(job: dict, runner=None) -> tuple[int, str]:
    if runner is None:  # tree-safe timeout / тайм-аут, що вбиває все дерево
        from dante.runner import safe_run as runner
    kind = job["kind"]
    cwd = job["cwd"]
    timeout = job["timeout"]
    args = job["args"]
    command = job["command"]

    # children write UTF-8 (Ukrainian text, ✓/✗ marks) — we read UTF-8
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        if kind == "dante":
            cmd_list = [sys.executable, "-m", "dante", *args]
            res = runner(
                cmd_list,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
        else:
            res = runner(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
        output = (res.stdout or "") + (res.stderr or "")
        return res.returncode, output
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout} s"
    except OSError as e:
        return 127, f"CANNOT START: {e}"


def _settled(path: Path) -> bool:
    """A file whose size does not change for a moment is complete."""
    try:
        a = path.stat().st_size
        time.sleep(0.2)
        return a == path.stat().st_size and a > 0
    except OSError:
        return False


def _run_one(job_path: Path, outbox: Path, done_dir: Path, base: Path, runner=None) -> None:
    """Run one job file: .running marker, result .txt, move the job to done.
    Виконати одне завдання: позначка .running, результат .txt, перенести завдання в done."""
    stem = job_path.stem
    running_path = outbox / f"{stem}.running"
    txt_path = outbox / f"{stem}.txt"
    running_path.write_text("", encoding="utf-8")
    try:
        try:
            job = load_job(job_path, base)
            code, output = run_job(job, runner=runner)
        except ValueError as e:
            code = 2
            output = f"INVALID JOB: {e}"
        except Exception as e:  # never let one job stop the remote / одне завдання не зупиняє пульт
            code = 1
            output = f"PULT ERROR: {type(e).__name__}: {e}"
        txt_path.write_text(f"EXIT {code}\n{output}", encoding="utf-8")
    finally:
        if running_path.exists():
            running_path.unlink()
    dest_job = done_dir / job_path.name
    if dest_job.exists():
        dest_job.unlink()
    shutil.move(str(job_path), str(dest_job))


def job_lane(job_path: Path) -> str:
    """Jobs in the same lane run one after another; different lanes run at the same time.
    lane = "lane" field, else the --project folder, else "main".
    Завдання однієї смуги — по черзі; різних смуг — одночасно."""
    try:
        data = json.loads(job_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "main"
    if isinstance(data, dict):
        if isinstance(data.get("lane"), str) and data["lane"].strip():
            return data["lane"].strip().lower()
        args = data.get("args")
        if isinstance(args, list) and "--project" in args:
            i = args.index("--project")
            if i + 1 < len(args):
                return str(args[i + 1]).strip().lower().rstrip("\\/")
    return "main"


def idle_seconds() -> float:
    """Seconds since the last mouse/keyboard input (Windows); 0 elsewhere.
    Секунд від останнього руху миші/клавіатури (Windows); 0 деінде."""
    if os.name != "nt":
        return 0.0
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return max(0.0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0)


def gpu_temp() -> int | None:
    """GPU temperature in C via nvidia-smi, None if unknown / Температура відеокарти."""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return int(r.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


class Scheduler:
    """Runs jobs of different lanes in parallel, up to max_parallel; pauses new jobs when too hot.
    Виконує завдання різних смуг паралельно (до max_parallel); при перегріві нові не запускає."""

    def __init__(self, inbox: Path, outbox: Path, base: Path, max_parallel: int = 3, max_temp: int = 83,
                 runner=None, temp=gpu_temp, say=print):
        import threading
        self.inbox, self.outbox, self.base = inbox, outbox, base
        self.max_parallel, self.max_temp, self.runner, self.temp, self.say = max_parallel, max_temp, runner, temp, say
        self.running: dict[str, tuple[str, "threading.Thread"]] = {}  # lane -> (job name, thread)
        self._threading = threading
        self._last_temp_check, self._hot = 0.0, False

    def _too_hot(self) -> bool:
        now = time.time()
        if now - self._last_temp_check >= 30:
            self._last_temp_check = now
            t = self.temp()
            hot = t is not None and t >= self.max_temp
            if hot != self._hot:
                self.say(f"GPU {t} C: " + ("pause new jobs / пауза нових завдань" if hot else "ok again / знову гаразд"))
            self._hot = hot
        return self._hot

    def adapt(self) -> None:
        """Idle-time full load (default on) and heartbeat / Повне навантаження в простої (типово ввімкнено) і пульс."""
        from dante import idle_policy as I
        now = time.time()
        try:
            self.outbox.mkdir(parents=True, exist_ok=True)
            (self.outbox / "pult.heartbeat").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
        except OSError:
            pass
        if now - getattr(self, "_last_adapt", 0) < 30:
            return
        self._last_adapt = now
        settings = I.load_settings(self.base / "dante" / "idle.json")
        plan = I.plan_load(idle_seconds(), settings, os.cpu_count() or 4, self.temp())
        if plan["parallel"] != self.max_parallel or plan["reason"] != getattr(self, "_reason", ""):
            self.say(f"load: {plan['reason']} -> parallel {plan['parallel']} / навантаження")
        self.max_parallel, self._reason = plan["parallel"], plan["reason"]
        state = self.base / "dante" / "train.last"
        try:
            last = float(state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            last = None
        if plan["train"] and I.should_train(last, now, settings, len(list(self.inbox.glob("*.json")))):
            job = {"kind": "dante", "lane": "train", "timeout": 7200,
                   "args": ["bench", "--learn", "--models", "gemini,groq,nemotron"]}
            name = time.strftime("zz-train-%Y%m%d-%H%M.json")
            (self.inbox / name).write_text(json.dumps(job), encoding="utf-8")
            os.utime(self.inbox / name, (now - 5, now - 5))
            state.write_text(str(now), encoding="utf-8")
            self.say(f"idle training queued / навчання в простої: {name}")
        self._keep_watchdog(now)

    def _keep_watchdog(self, now: float) -> None:
        """The pult and the watchdog keep each other alive / Пульт і сторож бережуть одне одного."""
        if os.name != "nt" or now - getattr(self, "_last_wd", 0) < 300:
            return
        self._last_wd = now
        from dante import watchdog as WD
        if not WD.pid_alive(WD.read_pid(WD.WD_PID)):
            self.say("watchdog missing -> start / сторожа немає -> запуск")
            WD.start_detached(self.base / "dante" / "watchdog-hidden.cmd")

    def tick(self) -> list[str]:
        """Start what may start now; return names of jobs started.
        Запустити те, що можна зараз; повернути назви запущених."""
        if getattr(self, "auto_adapt", False):
            try:
                self.adapt()
            except Exception as e:  # never stop / ніколи не зупинятися
                self.say(f"adapt error: {type(e).__name__}: {e}")
        for lane, (name, th) in list(self.running.items()):
            if not th.is_alive():
                del self.running[lane]
                self.say(f"done / готово: {name}")
        self.outbox.mkdir(parents=True, exist_ok=True)
        done_dir = self.inbox / "done"
        done_dir.mkdir(parents=True, exist_ok=True)
        busy_names = {n for n, _ in self.running.values()}
        started = []
        now = time.time()
        for job_path in sorted(self.inbox.glob("*.json"), key=lambda p: p.name):
            if len(self.running) >= self.max_parallel or self._too_hot():
                break
            if job_path.name in busy_names:
                continue
            try:
                if now - job_path.stat().st_mtime < 1.0 and not _settled(job_path):
                    continue
            except OSError:
                continue
            lane = job_lane(job_path)
            if lane in self.running:
                continue
            th = self._threading.Thread(target=_run_one, args=(job_path, self.outbox, done_dir, self.base, self.runner),
                                        daemon=True)
            self.running[lane] = (job_path.name, th)
            busy_names.add(job_path.name)
            th.start()
            started.append(job_path.name)
            self.say(f"start [{lane}]: {job_path.name}")
        return started


def process_once(inbox: Path, outbox: Path, base: Path, runner=None) -> list[str]:
    outbox.mkdir(parents=True, exist_ok=True)
    done_dir = inbox / "done"
    done_dir.mkdir(parents=True, exist_ok=True)

    now = time.time()
    # skip a job that is still being written (changed less than a second ago)
    json_files = sorted((p for p in inbox.glob("*.json") if now - p.stat().st_mtime >= 1.0 or _settled(p)),
                        key=lambda p: p.name)
    processed: list[str] = []

    for job_path in json_files:
        _run_one(job_path, outbox, done_dir, base, runner)
        processed.append(job_path.name)

    return processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(Path(__file__).resolve().parents[2]))  # C:\\DANTE
    parser.add_argument("--interval", type=int, default=3)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--parallel", type=int, default=max(2, (os.cpu_count() or 4) // 4),
                        help="jobs of different lanes at the same time / одночасних завдань")
    parser.add_argument("--max-temp", type=int, default=83, help="GPU C that pauses new jobs / пауза при перегріві")
    args = parser.parse_args(argv)

    base = Path(args.base)
    inbox = base / "inbox"
    outbox = base / "outbox"

    if args.once:
        processed = process_once(inbox, outbox, base)
        for p in processed:
            print(p)
        return 0

    log_path = outbox / "pult.log"

    def say(*parts) -> None:
        """Print if there is a window, always append to pult.log / Друк у вікно (якщо є) і завжди в pult.log."""
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in parts)
        if sys.stdout is not None:
            try:
                print(line, flush=True)
            except (OSError, ValueError):
                pass
        try:
            outbox.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    lock = _single_instance(base / "pult.lock")
    if lock is None:
        say("another pult is already running — exiting / інший пульт уже працює — вихід")
        return 0
    try:
        (base / "pult.pid").write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    sched = Scheduler(inbox, outbox, base, max_parallel=max(1, args.parallel), max_temp=args.max_temp, say=say)
    sched.auto_adapt = True  # idle full load + heartbeat + watchdog / простій, пульс, сторож
    say(f"DANTE pult: watching {inbox}, parallel {sched.max_parallel}, max GPU {args.max_temp} C / стежу, паралельно {sched.max_parallel}")
    try:
        while True:
            try:
                sched.tick()
            except OSError as e:  # e.g. a file locked for a moment / файл ненадовго зайнятий
                say("retry:", e)
            except Exception as e:  # never stop the remote / пульт ніколи не зупиняється
                say("ERROR:", type(e).__name__, e)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    return 0


def _single_instance(path: Path):
    """Hold a lock file so only one pult runs; None if another holds it.
    Тримати файл-замок, щоб працював лише один пульт; None, якщо його тримає інший."""
    try:
        f = open(path, "a+")
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        return None


if __name__ == "__main__":
    sys.exit(main())
