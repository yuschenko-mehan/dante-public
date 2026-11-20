"""Window logic without tkinter (so it can be tested anywhere).

What each button runs, the hotkey table, remembered settings and wallet totals.
Логіка вікна без tkinter (щоб можна було тестувати будь-де).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

DANTE_ROOT = Path(__file__).resolve().parents[1]  # folder with keys.txt, dante.toml, audit

from dante.i18n import LANGS, t

AGENT_IDS = ["", "gemini", "codex"]  # value of --agent ("" = DANTE's own free models)
TEMPLATE_IDS = ["fix", "add", "tests", "refactor"]


def agent_labels(lang: str) -> list[str]:
    return [t(lang, "agent_" + a) for a in AGENT_IDS]


def agent_id(lang: str, label: str) -> str:
    for lg in (lang, *LANGS):
        for a in AGENT_IDS:
            if t(lg, "agent_" + a) == label:
                return a
    return label if label in AGENT_IDS else ""


def template_labels(lang: str) -> list[str]:
    return [t(lang, "tpl_" + k) for k in TEMPLATE_IDS]


def template_text(lang: str, label: str) -> str:
    for k in TEMPLATE_IDS:
        if t(lang, "tpl_" + k) == label:
            return t(lang, f"tpl_{k}_text")
    return ""


# Edit keys mapping / Мапа клавіш редагування
EDIT_KEYS = {67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>", 65: "<<SelectAll>>"}   # C V X A

# Window keys mapping by virtual key code / Мапа клавіш вікна за кодом віртуальної клавіші
WINDOW_KEYS_BY_CODE = {80: "plan", 84: "tests", 77: "models", 71: "github"}          # P T M G


def edit_event(keycode: int, keysym: str) -> str | None:
    """Return virtual event for edit key or None if handled by Latin layout.
    Повернути віртуальну подію для клавіші редагування або None, якщо оброблено латинською розкладкою."""
    if keysym.lower() in ("c", "v", "x", "a"):
        return None
    return EDIT_KEYS.get(keycode)


def window_action(keycode: int, keysym: str) -> str | None:
    """Return window action for hotkey or None if handled by Latin layout.
    Повернути дію вікна для гарячої клавіші або None, якщо оброблено латинською розкладкою."""
    if keysym.lower() in ("p", "t", "m", "g"):
        return None
    return WINDOW_KEYS_BY_CODE.get(keycode)


def context_menu(lang: str) -> list[tuple[str, str]]:
    """Return context menu items [(label, virtual event)] for the given language.
    Повернути пункти контекстного меню [(мітка, віртуальна подія)] для заданої мови."""
    if lang == "uk":
        return [
            ("Вирізати", "<<Cut>>"),
            ("Копіювати", "<<Copy>>"),
            ("Вставити", "<<Paste>>"),
            ("Виділити все", "<<SelectAll>>"),
        ]
    else:
        return [
            ("Cut", "<<Cut>>"),
            ("Copy", "<<Copy>>"),
            ("Paste", "<<Paste>>"),
            ("Select all", "<<SelectAll>>"),
        ]


# Global hotkeys (work from any program on Windows). id: (modifiers, virtual key, action, keys)
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
HOTKEYS = {
    1: (MOD_CONTROL | MOD_ALT, ord("D"), "toggle", "Ctrl+Alt+D"),
    2: (MOD_CONTROL | MOD_ALT, ord("Q"), "stop", "Ctrl+Alt+Q"),
    3: (MOD_CONTROL | MOD_ALT, 0x0D, "approve", "Ctrl+Alt+Enter"),
    4: (MOD_CONTROL | MOD_ALT, ord("Z"), "undo", "Ctrl+Alt+Z"),
    5: (MOD_CONTROL | MOD_ALT, ord("R"), "reader", "Ctrl+Alt+R"),
}
WINDOW_KEYS = [("Ctrl+Enter", "wk_run"), ("Ctrl+P", "wk_plan"), ("Ctrl+T", "wk_test"),
               ("Ctrl+M", "wk_models"), ("Ctrl+G", "wk_github"), ("Esc", "wk_stop"), ("F1", "wk_help")]


def help_text(lang: str = "uk") -> str:
    lines = [t(lang, "keys_global")] + [f"  {h[3]} — {t(lang, 'hk_' + h[2])}" for h in HOTKEYS.values()]
    lines += ["", t(lang, "keys_window")] + [f"  {k} — {t(lang, key)}" for k, key in WINDOW_KEYS]
    lines += ["", t(lang, "help_money"), t(lang, "help_stop")]
    return "\n".join(lines)


@dataclass
class State:
    project: str = ""
    task: str = ""
    test: str = "python -m unittest discover -s tests"
    agent: str = ""            # "", "gemini" or "codex"
    protect_tests: bool = True
    lang: str = "uk"
    contrast: int = 85         # 0..100, the knob in the window
    draft_font: bool = True    # drafting font (ISOCPEUR / GOST / OpenGost) for the whole window
    recent: list[str] = field(default_factory=list)
    shortcut_done: bool = False
    github_auto: bool = False    # publish after every successful task / викладати після кожної успішної задачі
    github_public: bool = False  # new repositories are public / нові репозиторії публічні


def state_file() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "DANTE" / "window.json"


def load_state(path: Path | None = None) -> State:
    path = path or state_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in State.__dataclass_fields__}
        st = State(**known)
        st.agent = agent_id(st.lang, st.agent)  # older files kept the shown name
        if st.lang not in LANGS:
            st.lang = "uk"
        return st
    except (OSError, ValueError, TypeError):
        return State()


def save_state(st: State, path: Path | None = None) -> None:
    path = path or state_file()
    if st.project and st.project not in st.recent:
        st.recent = ([st.project] + st.recent)[:10]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(st), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


class InputError(ValueError):
    """Something the author must fill in first (shown as a friendly message).
    Те, що автор має спочатку заповнити (показується як дружнє повідомлення)."""


def _need_project(st: State) -> str:
    if not st.project or not Path(st.project).is_dir():
        raise InputError(t(st.lang, "need_project"))
    return st.project


def dante_args(action: str, st: State) -> list[str]:
    """Arguments for `python -m dante ...` for a button. / Аргументи для `python -m dante ...` для кнопки."""
    if action == "run":
        project = _need_project(st)
        if not st.task.strip():
            raise InputError(t(st.lang, "need_task"))
        if not st.test.strip():
            raise InputError(t(st.lang, "need_test"))
        args = ["run", "--project", project, "--task", st.task.strip(), "--test", st.test.strip()]
        if st.protect_tests:
            args += ["--protect", "tests"]
        if st.agent in AGENT_IDS[1:]:
            args += ["--agent", st.agent]
        return args
    if action == "plan":
        project = _need_project(st)
        if not st.task.strip():
            raise InputError(t(st.lang, "need_goal"))
        args = ["plan", "--project", project, "--goal", st.task.strip()]
        if st.test.strip():
            args += ["--check", st.test.strip()]
        return args
    if action == "approve":
        return ["approve", "--project", _need_project(st)]
    if action == "do":
        args = ["do", "--project", _need_project(st)]
        if st.protect_tests:
            args += ["--protect", "tests"]
        if st.agent in AGENT_IDS[1:]:
            args += ["--agent", st.agent]
        return args
    if action in ("undo", "history"):
        return [action, "--project", _need_project(st)]
    if action in ("check", "ping"):
        return [action]
    raise ValueError(f"unknown action {action}")


def python_command(args: list[str]) -> list[str]:
    return [sys.executable, "-m", "dante", *args]


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["DANTE_NO_PROMPT"] = "1"  # no console questions; paid models therefore stay off
    return env


def latest_audit(audit_dir: Path | None = None) -> Path | None:
    d = audit_dir or (DANTE_ROOT / "audit")
    files = sorted(d.glob("*.jsonl")) if d.is_dir() else []
    return files[-1] if files else None


def wallet_summary(lang: str = "uk") -> str:
    from dante.config import KEYS_FILE, load_settings
    from dante.wallet import Wallet

    s = load_settings(DANTE_ROOT / "dante.toml")
    w = Wallet(s, KEYS_FILE.parent / "wallet.jsonl")
    paid_on = t(lang, "paid_yes") if s.allow_paid else t(lang, "paid_no")
    return (f"{t(lang, 'wallet_today')}: {w.fmt(w.spent_today())}\n"
            f"{t(lang, 'wallet_month')}: {w.fmt(w.spent_month())}\n"
            f"{t(lang, 'wallet_paid')}: {paid_on}")


def make_desktop_shortcut(target: Path | None = None, lang: str = "uk") -> str:
    """Windows: put a «DANTE» shortcut on the desktop that opens the window. Returns a message.
    Windows: покласти ярлик «DANTE» на робочий стіл, який відкриває вікно. Повертає повідомлення."""
    import subprocess
    target = target or (DANTE_ROOT / "Dante.bat")
    ps = ("$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell)"
          ".CreateShortcut((Join-Path $d 'DANTE.lnk')); "
          f"$s.TargetPath='{target}'; $s.WorkingDirectory='{target.parent}'; $s.WindowStyle=7; "
          "$s.Description='Arkhitektor Dante'; $s.Save(); Write-Output (Join-Path $d 'DANTE.lnk')")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                           timeout=30, creationflags=0x08000000)
    except (OSError, subprocess.TimeoutExpired) as e:
        return t(lang, "shortcut_fail", e=e)
    return (t(lang, "shortcut_ok") if r.returncode == 0
            else t(lang, "shortcut_fail", e=(r.stderr or "").strip()[:200]))


CONTEST_FILE = Path(__file__).resolve().parents[1] / "contest.json"


def contest_enabled(path: Path | None = None) -> bool:
    """Contest of models: OFF by default, switched on by the author when speed matters.
    Конкурс моделей: типово ВИМКНЕНО, вмикає автор, коли потрібна швидкість."""
    import json
    try:
        return bool(json.loads((path or CONTEST_FILE).read_text(encoding="utf-8")).get("enabled", False))
    except (OSError, ValueError, AttributeError):
        return False


def set_contest(on: bool, path: Path | None = None) -> None:
    import json
    target = path or CONTEST_FILE
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data["enabled"] = bool(on)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


CRITIC_FILE = Path(__file__).resolve().parents[1] / "critic.json"


def critic_enabled(path: Path | None = None) -> bool:
    """Critic: ON by default / Критик: типово УВІМКНЕНИЙ."""
    import json
    try:
        return bool(json.loads((path or CRITIC_FILE).read_text(encoding="utf-8")).get("enabled", True))
    except (OSError, ValueError, AttributeError):
        return True


def set_critic(on: bool, path: Path | None = None) -> None:
    """Switch the critic / Перемкнути критика."""
    import json
    target = path or CRITIC_FILE
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data["enabled"] = bool(on)
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
