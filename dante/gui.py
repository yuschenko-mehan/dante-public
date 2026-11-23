"""DANTE window: Windows 11 dark style, Ukrainian / English, big buttons, STOP, global hotkeys.

Start: python -m dante gui   (or the DANTE shortcut / Dante.bat)
Every button runs `python -m dante ...` as a separate process, so STOP can always end it.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from dante import FULL_NAME, NAME, __build__, __version__
from dante import gui_logic as L
from dante.i18n import LANGS, t

# Windows PowerShell style; text/background contrast follows the «Contrast» slider (0 = darkest .. 100)
from dante.theme import CAMPBELL, palette, palette_for, step as _step, value_from_x, x_from_value  # noqa: E402
from dante import ui_theme  # noqa: E402
UI_JSON = Path(__file__).resolve().parents[1] / "ui.json"

ACCENT, ACCENT_HOVER, ACCENT_FG = CAMPBELL["cyan"], "#8ae6e6", "#000000"
DANGER, DANGER_HOVER = "#c50f1f", "#a30d1a"
PS_YELLOW = "#f9f1a5"
DEFAULT_CONTRAST = 60  # classic PowerShell: white-grey text on dark blue


STATUS = {"ready": "#454545", "working": "#0f7b0f", "waiting": "#9d5d00", "done": "#0f7b0f",
          "failed": "#c42b1c", "stopped": "#c42b1c", "you": "#9d5d00"}


class GlobalHotkeys(threading.Thread):
    """Windows RegisterHotKey in its own thread; actions go to the `out` queue. Does nothing elsewhere."""

    def __init__(self, out: queue.Queue):
        super().__init__(daemon=True)
        self.out = out
        self.thread_id = None

    def run(self) -> None:
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self.thread_id = kernel32.GetCurrentThreadId()
        failed = [keys for hid, (mods, vk, _a, keys) in L.HOTKEYS.items()
                  if not user32.RegisterHotKey(None, hid, mods | L.MOD_NOREPEAT, vk)]
        if failed:
            self.out.put(("busy_keys", ", ".join(failed)))
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                hk = L.HOTKEYS.get(msg.wParam)
                if hk:
                    self.out.put(("hotkey", hk[2]))
        for hid in L.HOTKEYS:
            user32.UnregisterHotKey(None, hid)

    def stop(self) -> None:
        if os.name == "nt" and self.thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)  # WM_QUIT


class Slider:
    """Wide contrast slider (PowerShell-like): click or drag anywhere on it, mouse wheel = 1 step
    (Shift + wheel = 10), arrow keys = 1, PageUp/PageDown = 10, Home = 0 (darkest), End = 100,
    double click = default. `on_change(value)` is called live while dragging."""

    def __init__(self, parent, value: int, on_change, P: dict, width: int = 240, height: int = 30,
                 default: int = DEFAULT_CONTRAST):
        import tkinter as tk
        self.c = tk.Canvas(parent, width=width, height=height, bg=P["BG"], highlightthickness=1,
                           highlightbackground=P["BORDER"], highlightcolor=ACCENT, cursor="hand2", takefocus=1)
        self.w, self.h, self.default, self.on_change = width, height, default, on_change
        self.value = int(max(0, min(100, value)))
        self.label = None
        self.P = P
        self._pending = None
        self.c.bind("<ButtonPress-1>", self._mouse)
        self.c.bind("<B1-Motion>", self._mouse)
        self.c.bind("<Double-Button-1>", lambda e: self.set(self.default, now=True))
        self.c.bind("<MouseWheel>", lambda e: self.set(_step(self.value, (10 if e.state & 1 else 1) * (1 if e.delta > 0 else -1))))
        self.c.bind("<Button-4>", lambda e: self.set(_step(self.value, 1)))
        self.c.bind("<Button-5>", lambda e: self.set(_step(self.value, -1)))
        for key, d in (("<Left>", -1), ("<Down>", -1), ("<Right>", 1), ("<Up>", 1), ("<Prior>", 10), ("<Next>", -10)):
            self.c.bind(key, lambda e, d=d: self.set(_step(self.value, d)))
        self.c.bind("<Home>", lambda e: self.set(0))
        self.c.bind("<End>", lambda e: self.set(100))
        self.draw()

    def _mouse(self, e) -> None:
        self.c.focus_set()
        self.set(value_from_x(e.x, self.w))

    def set(self, v: int, now: bool = False) -> None:
        v = int(max(0, min(100, v)))
        if v == self.value and not now:
            return
        self.value = v
        self.draw()
        if self._pending:
            self.c.after_cancel(self._pending)
        self._pending = self.c.after(1 if now else 25, self._fire)  # live, but not more often than needed

    def _fire(self) -> None:
        self._pending = None
        self.on_change(self.value)

    def draw(self) -> None:
        c, w, h, P = self.c, self.w, self.h, self.P
        c.configure(bg=P["BG"], highlightbackground=P["BORDER"])
        c.delete("all")
        x0, x1, mid = x_from_value(0, w), x_from_value(100, w), h // 2
        steps = 50  # the track shows the range: from black to the brightest text
        for i in range(steps):
            g = int(30 + 225 * i / (steps - 1))
            xa = x0 + (x1 - x0) * i / steps
            xb = x0 + (x1 - x0) * (i + 1) / steps
            c.create_rectangle(xa, mid - 3, xb + 1, mid + 3, fill=f"#{g:02x}{g:02x}{g:02x}", outline="")
        for v in range(0, 101, 10):  # ticks every 10 %
            x = x_from_value(v, w)
            c.create_line(x, mid + 6, x, mid + (11 if v % 50 == 0 else 8), fill=P["FG2"])
        x = x_from_value(self.value, w)
        c.create_rectangle(x - 5, 3, x + 5, h - 3, fill=PS_YELLOW, outline=P["BG"])  # block «cursor» like PowerShell
        if self.label is not None:
            self.label.configure(text=f"{self.value}%")


_MUTEX = None


def another_window_open() -> bool:
    """Windows: True if another DANTE window already runs (then it keeps the global keys)."""
    global _MUTEX
    if os.name != "nt":
        return False
    import ctypes
    k = ctypes.windll.kernel32
    if _MUTEX is None:
        _MUTEX = k.CreateMutexW(None, False, "Local\\DANTE_window")
        return k.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    return False


def _dark_title_bar(root) -> None:
    """Windows 10 (20H1+) / 11: dark window frame. Ignored elsewhere."""
    if os.name != "nt":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old number)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except Exception:
        pass


def _ui_font(root) -> str:
    from tkinter import font
    fams = set(font.families(root))
    for f in ("Segoe UI Variable Text", "Segoe UI", "Noto Sans", "DejaVu Sans"):
        if f in fams:
            return f
    return "TkDefaultFont"


def _dpi_aware() -> None:
    """Without this Windows stretches the window as a picture on 125-150 % screens, and letters blur.
    Без цього Windows розтягує вікно як картинку на екранах 125-150 %, і літери розпливаються."""
    if os.name != "nt":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor / для кожного монітора
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _mono_font(root) -> str:
    from tkinter import font
    fams = set(font.families(root))
    for f in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono"):
        if f in fams:
            return f
    return "TkFixedFont"


class DanteWindow:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.state = L.load_state()
        self.proc: subprocess.Popen | None = None
        self.events: queue.Queue = queue.Queue()
        self.stopped = False
        self.status_key = "ready"

        _dpi_aware()  # sharp text: tell Windows we draw at the real screen scale / чіткий текст
        root = self.root = tk.Tk()
        try:  # Tk points follow the real DPI / розміри шрифтів за справжньою щільністю екрана
            root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
        except Exception:
            pass
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(sw - 40, max(1180, int(sw * 0.66))), int(sh * 0.86)  # always fits the screen
        root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+10")
        root.minsize(min(820, sw - 20), min(520, sh - 60))
        self.theme_mode = ui_theme.load_mode(UI_JSON)
        self.P = palette_for(self.theme_mode, self.state.contrast)
        root.configure(bg=self.P["BG"])
        self.setup_fonts()
        self._style()
        _dark_title_bar(root)

        self.build()
        self.say(t(self.lang, "welcome"))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.hotkeys = GlobalHotkeys(self.events)
        self.another = another_window_open()
        if self.another:
            self.say(t(self.lang, "second_window"))
        else:
            self.hotkeys.start()
        if os.name == "nt" and not self.state.shortcut_done:
            self.say(L.make_desktop_shortcut(lang=self.lang))
            self.state.shortcut_done = True
            L.save_state(self.state)
        root.after(100, self.poll)

    @property
    def lang(self) -> str:
        return self.state.lang

    def setup_fonts(self) -> None:
        from tkinter import font
        from dante import fonts
        self.ui_font = _ui_font(self.root)
        self.mono = _mono_font(self.root)
        self.font, self.slant = self.ui_font, False
        if self.state.draft_font:
            loaded = fonts.load_private_fonts()
            self.font, self.slant = fonts.choose(set(font.families(self.root)), loaded)

    def F(self, size: int, bold: bool = False, mono: bool = False) -> tuple:
        """Font tuple for every text in the window (drafting font, slanted when it is upright by itself)."""
        if mono:  # code and the log always in a crisp monospace font / код і журнал — завжди чіткий моноширинний
            return (self.mono, size)
        draft = self.state.draft_font
        # drafting fonts have thin strokes: in that mode all text is bold and a bit larger (better contrast).
        # A drawn (synthetic) slant makes small letters jump, so it is used only for big headings.
        # Штучний нахил робить дрібні літери «стрибучими», тому він лише для великих заголовків.
        styles = (("bold",) if bold or draft else ()) + (("italic",) if self.slant and size >= 16 else ())
        return (self.font, size + (2 if draft else 0), *styles)

    # ---------- look
    def _style(self) -> None:
        ttk, root, P = self.ttk, self.root, self.P
        BG, SURFACE, SURFACE2, HOVER, BORDER, FG, FG2, LOG_BG = (
            P[k] for k in ("BG", "SURFACE", "SURFACE2", "HOVER", "BORDER", "FG", "FG2", "LOG_BG"))
        st = ttk.Style(root)
        st.theme_use("clam")
        base = self.F(11)
        root.option_add("*Font", base)
        root.option_add("*TCombobox*Listbox.background", SURFACE)
        root.option_add("*TCombobox*Listbox.foreground", FG)
        root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_FG)
        root.option_add("*TCombobox*Listbox.font", base)
        st.configure(".", background=BG, foreground=FG, fieldbackground=SURFACE, bordercolor=BORDER,
                     lightcolor=BORDER, darkcolor=BORDER, troughcolor=BG, focuscolor=ACCENT,
                     selectbackground=ACCENT, selectforeground=ACCENT_FG, insertcolor=FG, font=base)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG2, font=base)
        st.configure("TButton", background=SURFACE2, foreground=FG, borderwidth=1, relief="flat", font=base,
                     padding=(6, 7), bordercolor=BORDER, lightcolor=SURFACE2, darkcolor=SURFACE2)
        st.map("TButton", background=[("pressed", SURFACE), ("active", HOVER)],
               lightcolor=[("active", HOVER)], darkcolor=[("active", HOVER)])
        big = self.F(12, bold=True)
        st.configure("Big.TButton", font=big, padding=(8, 10))
        st.configure("Small.TButton", font=self.F(10), padding=(4, 6))
        st.configure("Accent.TButton", font=big, padding=(8, 10), background=ACCENT,
                     foreground=ACCENT_FG, bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
        st.map("Accent.TButton", background=[("pressed", "#3aa0d6"), ("active", ACCENT_HOVER)],
               lightcolor=[("active", ACCENT_HOVER)], darkcolor=[("active", ACCENT_HOVER)])
        st.configure("Danger.TButton", font=big, padding=(8, 10), background=DANGER,
                     foreground="#ffffff", bordercolor=DANGER, lightcolor=DANGER, darkcolor=DANGER)
        st.map("Danger.TButton", background=[("pressed", "#8a1f15"), ("active", DANGER_HOVER)],
               lightcolor=[("active", DANGER_HOVER)], darkcolor=[("active", DANGER_HOVER)])
        st.configure("TEntry", fieldbackground=SURFACE, foreground=FG, padding=6, insertcolor=FG)
        st.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])
        st.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE2, foreground=FG,
                     arrowcolor=FG2, padding=5)
        st.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("readonly", FG)],
               bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
               selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", FG)])
        st.configure("TCheckbutton", background=BG, foreground=FG2, indicatorbackground=SURFACE,
                     indicatorforeground=ACCENT_FG, font=base)
        st.map("TCheckbutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT)])
        st.configure("TRadiobutton", background=BG, foreground=FG2, indicatorbackground=SURFACE,
                     indicatorforeground=ACCENT_FG, font=base)
        st.map("TRadiobutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT)])
        st.configure("Vertical.TScrollbar", background=SURFACE2, troughcolor=LOG_BG, bordercolor=LOG_BG,
                     arrowcolor=FG2, lightcolor=SURFACE2, darkcolor=SURFACE2)
        st.map("Vertical.TScrollbar", background=[("active", HOVER)])

    # ---------- layout (rebuilt when the language changes)
    def build(self) -> None:
        tk, ttk, lg = self.tk, self.ttk, self.lang
        root = self.root
        root.title(f"{t(lg, 'title')} — {NAME} ({FULL_NAME}) · v{__version__}, {t(lg, 'build')} {__build__}")

        P = self.P
        root.configure(bg=P["BG"])
        head = ttk.Frame(root, padding=(14, 8, 14, 0))
        head.pack(fill="x")
        self._paint = []  # tk widgets recoloured live when the contrast slider moves
        self._reg(tk.Label(head, text=NAME, fg=ACCENT, font=self.F(22, bold=True)), bg="BG").pack(side="left")
        names = self._reg(tk.Frame(head), bg="BG")
        names.pack(side="left", padx=(12, 0))
        self._reg(tk.Label(names, text=FULL_NAME, font=self.F(12)), bg="BG", fg="FG").pack(anchor="w")
        self._reg(tk.Label(names, text=f"{t(lg, 'version')} {__version__} · {t(lg, 'build')} {__build__}",
                           font=self.F(10)), bg="BG", fg="FG2").pack(anchor="w")
        # contrast slider (0 = darkest) + drafting font switch
        pct = self._reg(tk.Label(head, font=self.F(11, bold=True), width=5), bg="BG", fg="FG")
        pct.pack(side="right")
        self.slider = Slider(head, self.state.contrast, self.change_contrast, P)
        self.slider.label = pct
        self.slider.draw()
        self.slider.c.pack(side="right", padx=(6, 2))
        ttk.Label(head, text=t(lg, "contrast")).pack(side="right")
        # Day / Night / As in Windows / День / Ніч / Як у Windows
        ttk.Button(head, text=ui_theme.mode_label(self.theme_mode, lg), command=self.cycle_theme).pack(side="right", padx=(0, 12))

        top = ttk.Frame(root, padding=(14, 8, 14, 6))
        top.pack(fill="x")
        ttk.Label(top, text=t(lg, "project")).pack(side="left")
        self.project = tk.StringVar(value=self.state.project)
        self.project_box = ttk.Combobox(top, textvariable=self.project, values=self.state.recent)
        self.project_box.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(top, text=t(lg, "folder_btn"), command=self.pick_folder).pack(side="left")
        ttk.Button(top, text=t(lg, "open_folder"), command=self.open_folder).pack(side="left", padx=6)
        self.lang_box = ttk.Combobox(top, values=list(LANGS.values()), state="readonly", width=11)
        self.lang_box.set(LANGS[lg])
        self.lang_box.bind("<<ComboboxSelected>>", self.change_language)
        self.lang_box.pack(side="right")
        ttk.Label(top, text="🌐").pack(side="right", padx=(10, 4))
        self.status = tk.Label(top, bg=STATUS["ready"], fg="#ffffff", font=self.F(11, bold=True),
                               padx=12, pady=4)
        self.status.pack(side="right", padx=(10, 0))
        self.set_status(self.status_key)

        mid = ttk.Frame(root, padding=(14, 0))
        mid.pack(fill="x")
        row = ttk.Frame(mid)
        row.pack(fill="x")
        ttk.Label(row, text=t(lg, "task_label")).pack(side="left")
        self.protect = tk.BooleanVar(value=self.state.protect_tests)
        self.template = ttk.Combobox(row, values=L.template_labels(lg), state="readonly", width=24)
        self.template.pack(side="right")
        self.template.bind("<<ComboboxSelected>>", self.use_template)
        ttk.Label(row, text=t(lg, "template")).pack(side="right", padx=6)
        border = self._reg(tk.Frame(mid, padx=1, pady=1), bg="BORDER")
        border.pack(fill="x", pady=6)
        self.task = self._reg(tk.Text(border, height=3, wrap="word", font=self.F(12), relief="flat", padx=8, pady=6,
                                      selectbackground=ACCENT, selectforeground=ACCENT_FG, highlightthickness=0),
                              bg="SURFACE", fg="FG", insertbackground="FG")
        self.task.pack(fill="x")
        self.task.insert("1.0", self.state.task)
        self.task.bind("<FocusIn>", lambda e: border.configure(bg=ACCENT))
        self.task.bind("<FocusOut>", lambda e: border.configure(bg=self.P["BORDER"]))
        opts = ttk.Frame(mid)  # switches / перемикачі
        opts.pack(fill="x", pady=(0, 4))
        ttk.Checkbutton(opts, text=t(lg, "protect"), variable=self.protect).pack(side="left", padx=(0, 16))
        # switches: drafting font, contest of models (off by default) / перемикачі: шрифт, конкурс (типово вимкн.)
        self.draft = tk.BooleanVar(value=self.state.draft_font)
        ttk.Checkbutton(opts, text=t(lg, "draft_font"), variable=self.draft,
                        command=self.change_font).pack(side="left", padx=(0, 16))
        self.contest = tk.BooleanVar(value=L.contest_enabled())
        ttk.Checkbutton(opts, text=t(lg, "contest"), variable=self.contest,
                        command=lambda: (L.set_contest(bool(self.contest.get())),
                                         self.say(t(self.lang, "contest_on" if self.contest.get() else "contest_off"))
                                         )).pack(side="left")

        opts = ttk.Frame(mid)
        opts.pack(fill="x")
        opts.columnconfigure(1, weight=1)
        ttk.Label(opts, text=t(lg, "check")).grid(row=0, column=0, sticky="w")
        self.test = tk.StringVar(value=self.state.test)
        ttk.Entry(opts, textvariable=self.test).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(opts, text=t(lg, "who")).grid(row=0, column=2, sticky="w", padx=(12, 0))
        labels = L.agent_labels(lg)
        self.agent = tk.StringVar(value=labels[L.AGENT_IDS.index(self.state.agent)]
                                  if self.state.agent in L.AGENT_IDS else labels[0])
        ttk.Combobox(opts, textvariable=self.agent, values=labels, state="readonly",
                     width=30).grid(row=0, column=3, sticky="e", padx=(6, 0))

        # buttons share the width equally, so nothing is cut off in any language
        b1 = ttk.Frame(root, padding=(14, 12, 14, 4))
        b1.pack(fill="x")
        row1 = [("run", "Accent.TButton", lambda: self.start("run")),
                ("plan", "Big.TButton", lambda: self.start("plan")),
                ("approve", "Big.TButton", lambda: self.start("approve")),
                ("do", "Big.TButton", lambda: self.start("do")),
                ("stop", "Danger.TButton", self.stop)]
        for i, (key, style, cmd) in enumerate(row1):
            b1.columnconfigure(i, weight=1, uniform="b1")
            ttk.Button(b1, text=t(lg, key), style=style, command=cmd).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == len(row1) - 1 else 4))

        b2 = ttk.Frame(root, padding=(14, 4, 14, 10))
        b2.pack(fill="x")
        row2 = [("test_btn", self.run_tests), ("undo", self.undo),
                ("history", lambda: self.start("history")), ("journal", self.open_audit),
                ("wallet", self.wallet), ("ping", lambda: self.start("ping")), ("models_btn", self.open_models),
                ("github_btn", self.open_github), ("flash_to", lambda: self.flash_keys("to")),
                ("flash_from", lambda: self.flash_keys("from")), ("keys", self.show_help)]
        for i, (key, cmd) in enumerate(row2):
            b2.columnconfigure(i, weight=1, uniform="b2")
            ttk.Button(b2, text=t(lg, key), command=cmd, style="Small.TButton").grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 3, 0 if i == len(row2) - 1 else 3))

        logf = ttk.Frame(root, padding=(14, 0, 14, 14))
        logf.pack(fill="both", expand=True)
        lb = self._reg(tk.Frame(logf, padx=1, pady=1), bg="BORDER")
        lb.pack(fill="both", expand=True)
        self.log = self._reg(tk.Text(lb, wrap="word", font=self.F(11, mono=True), relief="flat", padx=10, pady=8,
                                     highlightthickness=0, selectbackground=ACCENT, selectforeground=ACCENT_FG),
                             bg="LOG_BG", fg="LOG_FG", insertbackground="LOG_FG")
        sb = ttk.Scrollbar(lb, command=self.log.yview, style="Vertical.TScrollbar")
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self._tag_colours()

        keys = {"<Control-Return>": lambda: self.start("run"), "<Control-p>": lambda: self.start("plan"),
                "<Control-t>": self.run_tests, "<Escape>": self.stop, "<F1>": self.show_help,
                "<Control-m>": self.open_models, "<Control-g>": self.open_github}
        for seq, fn in keys.items():
            handler = (lambda f: (lambda e: (f(), "break")[1]))(fn)
            root.bind(seq, handler)
            self.task.bind(seq, handler)  # widget binding first, so the text box does not act on these keys
        self._bind_any_layout(root, {"plan": lambda: self.start("plan"), "tests": self.run_tests,
                                     "models": self.open_models, "github": self.open_github})

    def _bind_any_layout(self, root, actions: dict) -> None:
        """Copy/paste/cut/select-all and window keys by PHYSICAL key, so they work in the Ukrainian layout too;
        plus a right-click menu in every text field.
        Копіювати/вставити/вирізати/виділити все і клавіші вікна за ФІЗИЧНОЮ клавішею — працюють і в українській
        розкладці; плюс меню правої кнопки в кожному текстовому полі."""
        def edit_key(e):
            ev = L.edit_event(e.keycode, e.keysym)
            if ev:
                e.widget.event_generate(ev)
                return "break"
            act = L.window_action(e.keycode, e.keysym)
            if act and act in actions:
                actions[act]()
                return "break"
            return None

        def menu(e):
            w = e.widget
            try:
                w.focus_set()
            except Exception:
                pass
            m = self.tk.Menu(root, tearoff=0)
            for label, ev in L.context_menu(self.lang):
                m.add_command(label=label, command=lambda ev=ev, w=w: w.event_generate(ev))
            try:
                m.tk_popup(e.x_root, e.y_root)
            finally:
                m.grab_release()

        for cls in ("Text", "Entry", "TEntry", "TCombobox"):
            root.bind_class(cls, "<Control-KeyPress>", edit_key, add="+")
            root.bind_class(cls, "<Button-3>", menu, add="+")

        def window_key(e):
            act = L.window_action(e.keycode, e.keysym)
            if act and act in actions:
                actions[act]()
                return "break"
            return None
        root.bind("<Control-KeyPress>", window_key, add="+")

    def rebuild(self, note: str = "") -> None:
        """Rebuild the whole window (language, contrast or font changed); keeps the log and inputs."""
        self.read_state()
        old_log = self.log.get("1.0", "end-1c")
        for w in self.root.winfo_children():
            w.destroy()
        self.P = palette_for(self.theme_mode, self.state.contrast)
        self._style()
        self.build()
        self.log.insert("1.0", old_log + "\n")
        self.log.see("end")
        if note:
            self.say(note)

    def cycle_theme(self) -> None:
        """Day -> Night -> As in Windows; saved in ui.json. / День -> Ніч -> Як у Windows; зберігається в ui.json."""
        modes = ui_theme.MODES
        self.theme_mode = modes[(modes.index(self.theme_mode) + 1) % len(modes)] if self.theme_mode in modes else "night"
        try:
            ui_theme.save_mode(UI_JSON, self.theme_mode)
        except Exception:
            pass
        self.rebuild(ui_theme.mode_label(self.theme_mode, self.lang))

    def change_language(self, _e=None) -> None:
        new = next((k for k, v in LANGS.items() if v == self.lang_box.get()), "uk")
        if new == self.lang:
            return
        self.state.lang = new
        self.rebuild(t(new, "lang_note"))

    def _reg(self, widget, **roles):
        """Remember which colour role each option of a tk widget uses, and paint it now."""
        self._paint.append((widget, roles))
        widget.configure(**{opt: self.P[key] for opt, key in roles.items()})
        return widget

    def _tag_colours(self) -> None:
        P = self.P
        self.log.tag_configure("warn", foreground=P["WARN"])
        self.log.tag_configure("ok", foreground=P["OK"])
        self.log.tag_configure("bad", foreground=P["ERR"])
        self.log.tag_configure("head", foreground=P["ACCENT"])
        self.log.tag_configure("cmd", foreground=PS_YELLOW)  # like a command typed in PowerShell

    def change_contrast(self, value: int) -> None:
        """Live: ttk styles and every registered tk widget get the new colours — no rebuild, no flicker."""
        if value == self.state.contrast:
            return
        self.state.contrast = value
        self.P = palette_for(self.theme_mode, value)
        self._style()
        self.root.configure(bg=self.P["BG"])
        for w, roles in self._paint:
            try:
                w.configure(**{opt: self.P[key] for opt, key in roles.items()})
            except Exception:  # a widget that no longer exists
                pass
        self._tag_colours()
        self.slider.P = self.P
        self.slider.draw()
        L.save_state(self.state)

    def change_font(self) -> None:
        self.state.draft_font = bool(self.draft.get())
        self.setup_fonts()
        self.root.after_idle(lambda: self.rebuild(f"{t(self.lang, 'font_now')}: {self.font}"))

    # ---------- helpers
    def say(self, text: str, tag: str = "") -> None:
        s = text.strip()
        if tag:
            pass
        elif s.startswith("⚠"):
            tag = "warn"
        elif s.startswith("===") or s.startswith("ЦІЛЬ") or s.startswith("GOAL"):
            tag = "head"
        elif s.startswith(("SUCCESS", "ГОТОВО", "УСІ КРОКИ", "ПЛАН ПОГОДЖЕНО", "OK")):
            tag = "ok"
        elif s.startswith(("FAILED", "■", "НЕ ВДАЛОСЯ", "Traceback")):
            tag = "bad"
        self.log.insert("end", text if text.endswith("\n") else text + "\n", tag)
        self.log.see("end")

    def set_status(self, key: str) -> None:
        self.status_key = key
        self.status.configure(text=t(self.lang, "st_" + key), bg=STATUS.get(key, STATUS["ready"]))

    def read_state(self) -> L.State:
        st = self.state
        st.project = self.project.get().strip().strip('"')
        st.task = self.task.get("1.0", "end").strip()
        st.test = self.test.get().strip()
        st.agent = L.agent_id(self.lang, self.agent.get())
        st.protect_tests = bool(self.protect.get())
        L.save_state(st)
        self.project_box.configure(values=st.recent)
        return st

    def busy(self) -> bool:
        if self.proc and self.proc.poll() is None:
            self.say(t(self.lang, "busy"))
            return True
        return False

    # ---------- actions
    def start(self, action: str) -> None:
        if self.busy():
            return
        try:
            args = L.dante_args(action, self.read_state())
        except L.InputError as e:
            self.set_status("you")
            self.say("⚠ " + str(e))
            return
        self.launch(L.python_command(args), f"{t(self.lang, 'launch')}: {action}", action)

    def launch(self, cmd: list[str] | str, title: str, action: str, cwd: Path | None = None) -> None:
        shown = cmd if isinstance(cmd, str) else "dante " + " ".join(
            (a if " " not in a else f'"{a}"') for a in cmd[3:])
        self.say(f"\nPS {cwd or L.DANTE_ROOT}> {shown}", tag="cmd")
        self.set_status("working")
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        try:
            self.proc = subprocess.Popen(cmd, cwd=str(cwd or L.DANTE_ROOT), stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         env=L.child_env(), creationflags=flags,
                                         shell=isinstance(cmd, str), start_new_session=os.name != "nt")
        except OSError as e:
            self.set_status("failed")
            self.say(t(self.lang, "cannot_start", e=e))
            return
        proc = self.proc

        def pump() -> None:
            for raw in iter(proc.stdout.readline, b""):
                self.events.put(("log", raw.decode("utf-8", errors="replace").rstrip("\r\n")))
            self.events.put(("done", (proc, action, proc.wait())))

        threading.Thread(target=pump, daemon=True).start()

    def finished(self, proc, action: str, code: int) -> None:
        if proc is not self.proc:  # a late message from an older (stopped) run
            return
        if self.stopped:
            self.set_status("stopped")
        elif action == "plan" and code == 3:
            self.set_status("waiting")
            self.say("\n" + t(self.lang, "plan_wait"))
        elif code == 0:
            self.set_status("done")
            if action == "approve":
                self.say(t(self.lang, "approve_next"))
            if action in ("run", "do") and self.state.github_auto:  # auto-publish / автовикладання
                self.root.after(300, lambda: self.publish(ask=False))
        else:
            self.set_status("failed")
            self.say(t(self.lang, "exit_code", code=code))
        self.stopped = False

    def stop(self) -> None:
        if not (self.proc and self.proc.poll() is None):
            self.say(t(self.lang, "nothing_running"))
            return
        self.stopped = True
        pid = self.proc.pid
        if os.name == "nt":  # end the whole tree (DANTE + agent + tests)
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                           creationflags=0x08000000)
        else:  # the whole process group
            import signal
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                self.proc.kill()
        self.set_status("stopped")
        self.say(t(self.lang, "stopped_msg"))

    def run_tests(self) -> None:
        if self.busy():
            return
        st = self.read_state()
        if not st.project or not Path(st.project).is_dir():
            self.say("⚠ " + t(self.lang, "need_project"))
            return
        if not st.test:
            self.say("⚠ " + t(self.lang, "need_test"))
            return
        self.launch(st.test, f"{t(self.lang, 'testing')}: {st.test}", "test", cwd=Path(st.project))

    def undo(self) -> None:
        from tkinter import messagebox
        if self.busy():
            return
        if messagebox.askyesno(t(self.lang, "undo_title"), t(self.lang, "undo_q"), parent=self.root):
            self.start("undo")

    def pick_folder(self) -> None:
        from tkinter import filedialog
        d = filedialog.askdirectory(title=t(self.lang, "folder_title"),
                                    initialdir=self.project.get() or str(L.DANTE_ROOT.parent), parent=self.root)
        if d:
            self.project.set(str(Path(d)))
            self.read_state()

    def open_folder(self) -> None:
        p = self.project.get().strip() or str(L.DANTE_ROOT)
        if os.name == "nt" and Path(p).is_dir():
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            self.say(p)

    def open_audit(self) -> None:
        a = L.latest_audit()
        if not a:
            self.say(t(self.lang, "no_audit"))
        elif os.name == "nt":
            subprocess.Popen(["notepad.exe", str(a)])
        else:
            self.say(str(a))

    def wallet(self) -> None:
        try:
            self.say(f"\n=== {t(self.lang, 'wallet_title')} ===\n" + L.wallet_summary(self.lang))
        except Exception as e:  # never let the wallet view crash the window
            self.say(t(self.lang, "wallet_na", e=e))

    def open_models(self) -> None:
        """The "AI models" window (only one at a time)."""
        mw = getattr(self, "models_win", None)
        try:
            if mw and mw.win.winfo_exists():
                mw.win.lift()
                return
        except Exception:
            pass
        from dante.gui_models import ModelsWindow
        self.models_win = ModelsWindow(self)

    def flash_keys(self, mode: str) -> None:
        """Keys to / from a USB flash drive in a console window (the passphrase is typed there).
        Ключі на флешку / з флешки у вікні консолі (фразу вводять там)."""
        exe = Path(sys.executable)
        con = exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        try:
            subprocess.Popen([str(con), "-m", "dante.flash_keys", mode], cwd=str(Path(__file__).resolve().parents[1]),
                             creationflags=flags)
            self.say(t(self.lang, "flash_to" if mode == "to" else "flash_from") + " …")
        except Exception as e:  # never crash the window / вікно не падає
            self.say(f"flash: {e}")

    def open_github(self) -> None:
        """The GitHub window (one at a time) / Вікно GitHub (одне)."""
        gw = getattr(self, "github_win", None)
        try:
            if gw and gw.win.winfo_exists():
                gw.win.lift()
                return
        except Exception:
            pass
        from dante.gui_github import GithubWindow
        self.github_win = GithubWindow(self)

    def publish(self, ask: bool = False) -> None:
        """Publish the project; a NEW repository only after the author's yes.
        Викласти проєкт; НОВИЙ репозиторій — лише після «так» автора."""
        if self.busy():
            return
        st = self.read_state()
        if not st.project or not Path(st.project).is_dir():
            self.say("⚠ " + t(self.lang, "need_project"))
            return
        from dante import github_ops as O
        root = Path(st.project)
        has_remote = (root / ".git").exists() and O.run(["git", "remote", "get-url", "origin"], cwd=root)[0] == 0
        args = ["publish", "--project", str(root), "--task", st.task.strip()[:300]]
        if st.github_public:
            args.append("--public")
        if not has_remote:
            if not ask:
                self.say(t(self.lang, "github_first"), "warn")
                return
            from dante.gui_github import confirm_new_repo
            if not confirm_new_repo(self, self.lang):
                return
            args.append("--new-ok")
        self.launch(L.python_command(args), "GitHub", "publish")

    def show_help(self) -> None:
        self.say("\n" + L.help_text(self.lang))

    def use_template(self, _e=None) -> None:
        self.task.delete("1.0", "end")
        self.task.insert("1.0", L.template_text(self.lang, self.template.get()))
        self.task.focus_set()
        self.task.mark_set("insert", "end")

    def toggle(self) -> None:
        if self.root.state() in ("withdrawn", "iconic"):
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        else:
            self.root.withdraw()

    def on_hotkey(self, action: str) -> None:
        if action == "toggle":
            self.toggle()
            return
        self.root.deiconify()
        self.root.lift()
        if action == "stop":
            self.stop()
        elif action == "approve":
            self.start("approve")
        elif action == "undo":
            self.undo()
        elif action == "reader":
            self.say(t(self.lang, "reader_wip"))

    def poll(self) -> None:
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.say(data)
                elif kind == "done":
                    self.finished(*data)
                elif kind == "hotkey":
                    self.on_hotkey(data)
                elif kind == "busy_keys":
                    self.say("⚠ " + t(self.lang, "hotkeys_busy", keys=data))
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            from tkinter import messagebox
            if not messagebox.askyesno(t(self.lang, "exit_title"), t(self.lang, "exit_q"), parent=self.root):
                return
            self.stop()
        self.read_state()
        self.hotkeys.stop()
        self.root.destroy()


def _hide_console() -> None:
    if os.name == "nt":
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)


def main() -> int:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("No tkinter: install Python from python.org or Microsoft Store (with Tcl/Tk).")
        return 2
    if "--keep-console" not in sys.argv:
        _hide_console()
    try:
        DanteWindow().root.mainloop()
    except Exception:  # the console may be hidden: keep the error in a file
        import traceback
        (L.DANTE_ROOT / "gui-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
