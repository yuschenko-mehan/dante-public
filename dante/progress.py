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
