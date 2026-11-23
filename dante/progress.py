import re
from dataclasses import dataclass, field
from datetime import datetime

_T = "%Y-%m-%d %H:%M:%S"
_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (.*)$")


@dataclass
class Job:
    name: str
    lane: str = ""
    seconds: int = 0
    ok: bool | None = None


@dataclass
class Status:
    alive: bool
    running: list = field(default_factory=list)
    recent: list = field(default_factory=list)


def _ts(s):
    try:
        return datetime.strptime(s, _T)
    except ValueError:
        return None


def status_from_log(lines, now, read_result=None):
    run, done = {}, []
    alive = False
    for ln in lines:
        m = _LINE.match(ln.strip())
        if not m:
            continue
        t, rest = _ts(m.group(1)), m.group(2)
        alive = True
        if rest.startswith("DANTE pult: watching"):
            run.clear()
        elif rest.startswith("start ["):
            lane, name = re.match(r"start \[(.*?)\]: (.*?)(?:\.json)?$", rest).groups()
            run[name] = (lane, t)
        elif rest.startswith("done"):
            name = rest.split(":", 1)[1].strip().removesuffix(".json")
            run.pop(name, None)
            done.append(name)
    n = _ts(now)
    running = [Job(k, lane, int((n - t).total_seconds()) if n and t else 0) for k, (lane, t) in run.items()]
    recent = []
    for name in reversed(done[-5:]):
        ok = None
        if read_result:
            try:
                ok = read_result(name).startswith("EXIT 0")
            except Exception:
                ok = None
        recent.append(Job(name, ok=ok))
    return Status(alive, running, recent)


def human_time(sec, lang="uk"):
    uk = lang == "uk"
    if sec < 60:
        return f"{sec} {'с' if uk else 's'}"
    h, m = divmod(sec // 60, 60)
    if h:
        return f"{h} {'год' if uk else 'h'} {m} {'хв' if uk else 'min'}"
    return f"{m} {'хв' if uk else 'min'}"


def bar_text(s, lang="uk"):
    uk = lang == "uk"
    if not s.alive:
        return "○ Данте не запущений" if uk else "○ DANTE is not running"
    if not s.running:
        return "● Данте чекає завдань" if uk else "● DANTE is waiting for jobs"
    j = s.running[0]
    return (f"● Данте працює · завдань: {len(s.running)} · {j.name} {human_time(j.seconds, lang)}" if uk
            else f"● DANTE working · jobs: {len(s.running)} · {j.name} {human_time(j.seconds, lang)}")


def detail_lines(s, lang="uk"):
    out = [f"▶ {j.name} [{j.lane}] — {human_time(j.seconds, lang)}" for j in s.running]
    out += [f"{'✗' if j.ok is False else '✓'} {j.name}" for j in s.recent]
    return out


def pult_text(heartbeat, now, lang="uk"):
    """Separate pult indicator from its heartbeat file. / Окремий індикатор пульта за файлом пульсу."""
    uk = lang == "uk"
    h, n = _ts((heartbeat or "").strip()), _ts(now)
    if not h or not n:
        return "Пульт: ○ не запущений" if uk else "Pult: ○ not running"
    age = int((n - h).total_seconds())
    if age <= 60:
        return f"Пульт: ● працює (пульс {age} с тому)" if uk else f"Pult: ● running (pulse {age} s ago)"
    return f"Пульт: ○ мовчить {human_time(age, lang)}" if uk else f"Pult: ○ silent for {human_time(age, lang)}"


def live_lines(events, lang="uk"):
    """What DANTE is doing inside the current job, from its audit log. / Що Данте робить усередині завдання."""
    uk = lang == "uk"
    out, task, plan, step, model, attempt, files, test, done, lesson = [], None, None, None, None, None, None, None, False, False
    for e in events:
        ev = e.get("event")
        if ev == "task_start" and task is None:
            task = str(e.get("task", ""))[:80]
        elif ev == "mission_plan":
            plan = len(e.get("steps") or [])
        elif ev == "mission_step":
            step = (e.get("step"), e.get("total"))
        elif ev == "academy_lesson":
            lesson = True
        elif ev == "llm_response":
            attempt, model = e.get("attempt"), e.get("model")
        elif ev == "files_written":
            files = e.get("files") or []
        elif ev == "test_run":
            test = (e.get("exit_code"), str(e.get("output_tail", "")).strip().splitlines()[-1:] or [""])
        elif ev == "task_success":
            done = True
    if task is None and not events:
        return out
    out.append(("Завдання: " if uk else "Task: ") + (task or ""))
    if plan:
        s = f" · крок {step[0]} з {step[1]}" if (step and uk) else (f" · step {step[0]} of {step[1]}" if step else "")
        out.append((f"План: {plan} кроків" if uk else f"Plan: {plan} steps") + s)
    if lesson:
        out.append("Урок Академії: є" if uk else "Academy lesson: yes")
    if attempt:
        out.append((f"Спроба {attempt} · {model}" if uk else f"Attempt {attempt} · {model}"))
    if files:
        out.append(("Файли: " if uk else "Files: ") + ", ".join(files[:6]))
    if test:
        if test[0] == 0:
            out.append("Тести: ✓ пройшли" if uk else "Tests: ✓ passed")
        else:
            out.append((f"Тести: ✗ не пройшли ({test[1][0][:60]})" if uk else f"Tests: ✗ failed ({test[1][0][:60]})"))
    if done:
        out.append("Готово ✓" if uk else "Done ✓")
    return out
