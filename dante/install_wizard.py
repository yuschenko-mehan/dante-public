"""Installation wizard: language, DANTE role, shortcut, autostart, keys from a flash drive.
Майстер встановлення: мова, роль Данте, ярлик, автозапуск, ключі з флешки.
Runs after install_dante.ps1 has made sure Python is present. / Запускається після install_dante.ps1."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dante import roles as R

ROOT = Path(__file__).resolve().parents[1]
WINGET = {"gh": "GitHub.cli", "node": "OpenJS.NodeJS.LTS", "obsidian": "Obsidian.Obsidian"}
MSG = {
    "uk": {"yes": ("т", "так", "y", "yes"), "ask": " (т/н): ", "done": "Готово.", "shortcut": "Ярлик «DANTE» на робочому столі",
           "autostart": "Пульт Данте запускатиметься разом з Windows", "flash": "Відновити ключі з флешки зараз?",
           "role_saved": "Роль збережено", "install": "Встановити", "later": "встановлюється окремо (див. docs/INSTALL.uk.md)",
           "graphify": "Встановити Graphify (карта коду, Данте працює точніше)?", "selftest": "Запустити самоперевірку?",
           "bad": "Не зрозумів, ще раз.", "end": "Встановлення завершено. Відкрийте Данте ярликом «DANTE»."},
    "en": {"yes": ("y", "yes"), "ask": " (y/n): ", "done": "Done.", "shortcut": "Desktop shortcut \"DANTE\"",
           "autostart": "DANTE pult will start with Windows", "flash": "Restore keys from a flash drive now?",
           "role_saved": "Role saved", "install": "Install", "later": "is installed separately (see docs/INSTALL.md)",
           "graphify": "Install Graphify (code map, DANTE works more precisely)?", "selftest": "Run the self-test?",
           "bad": "Not understood, again.", "end": "Installation finished. Open DANTE with the \"DANTE\" shortcut."},
}


def ask(m, q):
    return input(q + m["ask"]).strip().lower() in m["yes"]


def make_shortcut():
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\\DANTE.lnk');"
          f"$s.TargetPath='{ROOT}\\Dante.bat';$s.WorkingDirectory='{ROOT}';$s.IconLocation='{ROOT}\\assets\\dante.ico';"
          f"$s.WindowStyle=7;$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


def enable_autostart():
    startup = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
    startup.mkdir(parents=True, exist_ok=True)
    (startup / "DANTE-pult.cmd").write_text(
        f'@echo off\r\ncd /d "{ROOT}"\r\nstart "" pythonw -m dante.pult\r\n', encoding="ascii", errors="ignore")


def main() -> int:
    lang = None
    while lang is None:
        lang = R.parse_language(input("Мова / Language: 1 — українська, 2 — English: "))
    m = MSG[lang]
    rid = None
    while rid is None:
        print(R.menu_text(lang))
        rid = R.parse_choice(input("> "))
        if rid is None:
            print(m["bad"])
    R.save_role(ROOT / "role.json", rid, lang)
    print(f"{m['role_saved']}: {R.name(rid, lang)}")
    comps = R.components(rid)
    for c in comps:
        if c in WINGET and ask(m, f"{m['install']} {c}?"):
            subprocess.run(["winget", "install", "-e", "--id", WINGET[c], "--accept-package-agreements",
                            "--accept-source-agreements"], check=False)
        elif c in ("chatbox", "freellmapi", "claude_code", "murakha", "ollama", "knyaz_service", "ant_autostart"):
            print(f"- {c} {m['later']}")
    if "graphify" in comps and ask(m, m["graphify"]):
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "graphifyy"], check=False)
    if "shortcuts" in comps or "dante" in comps:
        make_shortcut()
        print("+", m["shortcut"])
    if "pult_autostart" in comps:
        enable_autostart()
        print("+", m["autostart"])
    if "dante" in comps and ask(m, m["flash"]):
        from dante import flash_keys
        flash_keys.from_flash()
    if ask(m, m["selftest"]):
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=str(ROOT), check=False)
    print(m["end"])
    return 0


if __name__ == "__main__":
    rc = main()
    input("\nEnter…")
    sys.exit(rc)
