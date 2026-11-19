"""The "GitHub" window: connect once through the browser, then publish with one button (or automatically).
Вікно «GitHub»: один раз підключитися через браузер, далі викладати однією кнопкою (або автоматично).

DANTE never sees the GitHub password: the official GitHub CLI shows an 8-character code,
the author types it on github.com and presses Authorize.
Данте ніколи не бачить пароля GitHub: офіційна програма GitHub CLI показує код із 8 символів,
автор вводить його на github.com і натискає Authorize.
"""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import webbrowser
from pathlib import Path

from dante import github_ops as O
from dante import github_pub as G
from dante import gui_logic as L

NEW_CONSOLE = 0x00000010  # CREATE_NEW_CONSOLE: a visible black window / видиме чорне вікно

TX = {
    "uk": {
        "title": "GitHub — підключення та викладання", "head": "GitHub",
        "git": "git (зберігає версії)", "gh": "GitHub CLI (офіційна програма GitHub)", "acc": "Акаунт GitHub",
        "yes": "✓ є", "no": "✗ немає", "not_conn": "✗ не підключено", "checking": "перевіряю…",
        "install": "Встановити", "login": "Увійти через браузер", "signup": "Створити акаунт",
        "how": ("Як підключити (один раз):\n"
                "1. Якщо немає git або GitHub CLI — «Встановити» (безкоштовно; Windows може спитати дозвіл).\n"
                "2. «Увійти через браузер»: у чорному вікні натисніть Enter — з'явиться код із 8 символів\n"
                "    і відкриється github.com. Введіть код і натисніть Authorize. Пароль Данте не бачить.\n"
                "3. «Оновити стан» — має з'явитися ваш логін."),
        "vis": "Новий репозиторій:", "private": "приватний (бачите лише ви)", "public": "публічний (бачать усі)",
        "auto": "Автоматично викладати після кожної успішної задачі (лише у вже створений репозиторій)",
        "refresh": "Оновити стан", "publish": "Викласти зараз", "close": "Закрити",
        "need_project": "Спершу оберіть папку проєкту в головному вікні.",
        "confirm_t": "Новий репозиторій",
        "confirm": ("Створити {vis} репозиторій «{repo}» на акаунті {user}\nі викласти {n} файлів?\n\n"
                    "Перед викладанням Данте перевірить, чи немає в коді ключів.\n"
                    "README та опис будуть українською й англійською."),
        "vis_private": "ПРИВАТНИЙ", "vis_public": "ПУБЛІЧНИЙ",
        "only_windows": "Вхід і встановлення з цього вікна працюють у Windows.",
        "started": "Відкрито окреме вікно. Коли закінчите — «Оновити стан».",
    },
    "en": {
        "title": "GitHub — connect and publish", "head": "GitHub",
        "git": "git (keeps versions)", "gh": "GitHub CLI (official GitHub program)", "acc": "GitHub account",
        "yes": "✓ yes", "no": "✗ missing", "not_conn": "✗ not connected", "checking": "checking…",
        "install": "Install", "login": "Sign in with browser", "signup": "Create account",
        "how": ("How to connect (once):\n"
                "1. If git or GitHub CLI is missing — “Install” (free; Windows may ask for permission).\n"
                "2. “Sign in with browser”: press Enter in the black window — an 8-character code appears\n"
                "    and github.com opens. Type the code and press Authorize. DANTE never sees the password.\n"
                "3. “Refresh” — your login should appear."),
        "vis": "New repository:", "private": "private (only you see it)", "public": "public (everyone sees it)",
        "auto": "Publish automatically after every successful task (only to an existing repository)",
        "refresh": "Refresh", "publish": "Publish now", "close": "Close",
        "need_project": "First choose the project folder in the main window.",
        "confirm_t": "New repository",
        "confirm": ("Create a {vis} repository “{repo}” on account {user}\nand publish {n} files?\n\n"
                    "Before publishing DANTE checks the code for keys.\nREADME and description will be in Ukrainian and English."),
        "vis_private": "PRIVATE", "vis_public": "PUBLIC",
        "only_windows": "Sign-in and install from this window work on Windows.",
        "started": "A separate window opened. When done — “Refresh”.",
    },
}

WINGET_IDS = {"git": "Git.Git", "gh": "GitHub.cli"}


def open_console(cmd: list[str]) -> bool:
    """Start a command in its own visible window (Windows) / Запустити команду в окремому видимому вікні."""
    if os.name != "nt":
        return False
    subprocess.Popen(cmd, creationflags=NEW_CONSOLE)
    return True


def confirm_new_repo(app, lang: str) -> bool:
    """Ask before creating a new repository; True = go / Спитати перед створенням нового репозиторію."""
    from tkinter import messagebox
    T = TX.get(lang, TX["uk"])
    root = Path(app.state.project)
    vis = T["vis_public"] if app.state.github_public else T["vis_private"]
    user = O.github_user() or "?"
    text = T["confirm"].format(vis=vis, repo=G.repo_name(root.name), user=user, n=len(G.files_to_publish(root)))
    return messagebox.askyesno(T["confirm_t"], text, parent=app.root)


class GithubWindow:
    def __init__(self, app) -> None:
        self.app, tk, ttk = app, app.tk, app.ttk
        self.T = T = TX.get(app.lang, TX["uk"])
        P = app.P
        self.q: queue.Queue = queue.Queue()
        w = self.win = tk.Toplevel(app.root)
        w.title(f"DANTE — {T['title']}")
        w.configure(bg=P["BG"])
        w.transient(app.root)
        try:
            from dante.gui import _dark_title_bar
            _dark_title_bar(w)
        except Exception:
            pass
        f = ttk.Frame(w, padding=16)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        tk.Label(f, text=T["head"], bg=P["BG"], fg=P["ACCENT"], font=app.F(18, bold=True)).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.marks = {}
        for r, key in enumerate(("git", "gh", "acc"), start=1):
            ttk.Label(f, text=T[key]).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 12))
            self.marks[key] = tk.Label(f, text=T["checking"], bg=P["BG"], fg=P["FG"], font=app.F(11, bold=True))
            self.marks[key].grid(row=r, column=1, sticky="w")
            if key == "acc":
                bf = ttk.Frame(f)
                bf.grid(row=r, column=2, sticky="e")
                ttk.Button(bf, text=T["login"], command=self.login).pack(side="left")
                ttk.Button(bf, text=T["signup"], command=lambda: webbrowser.open("https://github.com/signup")).pack(
                    side="left", padx=(6, 0))
            else:
                ttk.Button(f, text=T["install"], command=lambda k=key: self.install(k)).grid(row=r, column=2, sticky="e")
        tk.Label(f, text=T["how"], bg=P["BG"], fg=P["FG2"], font=app.F(10), justify="left").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(10, 10))
        vf = ttk.Frame(f)
        vf.grid(row=5, column=0, columnspan=3, sticky="w")
        ttk.Label(vf, text=T["vis"]).pack(side="left")
        self.public = tk.IntVar(value=1 if app.state.github_public else 0)
        for val, key in ((0, "private"), (1, "public")):
            ttk.Radiobutton(vf, text=T[key], variable=self.public, value=val, command=self.save_opts).pack(
                side="left", padx=(10, 0))
        self.auto = tk.IntVar(value=1 if app.state.github_auto else 0)
        ttk.Checkbutton(f, text=T["auto"], variable=self.auto, command=self.save_opts).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(8, 4))
        bb = ttk.Frame(f)
        bb.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for i in range(3):
            bb.columnconfigure(i, weight=1, uniform="g")
        ttk.Button(bb, text=T["refresh"], style="Big.TButton", command=self.refresh).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(bb, text=T["publish"], style="Accent.TButton", command=self.publish).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(bb, text=T["close"], style="Big.TButton", command=w.destroy).grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self.note = tk.Label(f, text="", bg=P["BG"], fg=P["WARN"], font=app.F(10), justify="left")
        self.note.grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
        w.bind("<Escape>", lambda e: w.destroy())
        self.refresh()
        w.after(150, self.poll)

    def save_opts(self) -> None:
        self.app.state.github_public = bool(self.public.get())
        self.app.state.github_auto = bool(self.auto.get())
        L.save_state(self.app.state)

    def refresh(self) -> None:
        for m in self.marks.values():
            m.configure(text=self.T["checking"], fg=self.app.P["FG"])

        def work():
            st = O.status()
            if st["gh"] and st["user"]:
                O.run(["gh", "auth", "setup-git"], timeout=60)  # git uses the GitHub sign-in / git бере вхід GitHub
            self.q.put(st)
        threading.Thread(target=work, daemon=True).start()

    def poll(self) -> None:
        try:
            st = self.q.get_nowait()
            P, T = self.app.P, self.T
            for key in ("git", "gh"):
                self.marks[key].configure(text=T["yes"] if st[key] else T["no"], fg=P["OK"] if st[key] else P["ERR"])
            self.marks["acc"].configure(text=f"✓ {st['user']}" if st["user"] else T["not_conn"],
                                        fg=P["OK"] if st["user"] else P["ERR"])
            self.status = st
        except queue.Empty:
            pass
        try:
            self.win.after(200, self.poll)
        except Exception:  # window closed / вікно закрито
            pass

    def install(self, key: str) -> None:
        ok = open_console(["winget", "install", "--id", WINGET_IDS[key], "-e", "--source", "winget",
                           "--accept-package-agreements", "--accept-source-agreements"])
        self.note.configure(text=self.T["started"] if ok else self.T["only_windows"])

    def login(self) -> None:
        gh = O.find_tool("gh")
        if not gh:
            self.install("gh")
            return
        ok = open_console([gh, "auth", "login", "--web", "--git-protocol", "https", "--hostname", "github.com"])
        self.note.configure(text=self.T["started"] if ok else self.T["only_windows"])

    def publish(self) -> None:
        self.app.publish(ask=True)
        self.win.lift()
