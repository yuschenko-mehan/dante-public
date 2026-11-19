"""The "Моделі ШІ" window: see every model DANTE knows and add a new one in a few clicks.

1. Choose a service (or "Own service") — the address and the key name fill in by themselves.
2. Paste the key (it goes to keys.txt only; never shown in the log). "Де взяти ключ" opens the sign-up page.
3. "Отримати список" asks the service which models it has (free); pick one.
4. "Перевірити" sends one tiny question (free models only); "Зберегти" adds it to models.json.
"""

from __future__ import annotations

import queue
import threading
import webbrowser
from pathlib import Path

from dante import config, models_hub
from dante import models_ui as U

TX = {
    "uk": {
        "title": "Моделі ШІ — додати або змінити", "all": "Усі моделі, які знає Данте",
        "legend": "✓ є ключ   - немає ключа   $ платна   ★ ваша",
        "new": "Нова", "delete": "Видалити", "service": "Сервіс", "url": "Адреса (URL)",
        "key": "Ключ", "show": "показати", "where": "Де взяти ключ", "key_env": "Назва ключа",
        "model": "Модель", "fetch": "Отримати список", "name": "Назва в Данте", "paid": "Платна модель",
        "price": "Ціна, $ / 1 млн", "price_in": "питання", "price_out": "відповідь", "note": "Примітка",
        "check": "Перевірити", "save": "Зберегти", "close": "Закрити",
        "hint": "Оберіть сервіс, вставте ключ, натисніть «Отримати список» і виберіть модель.",
        "key_saved": "✓ ключ збережено",
        "no_key_needed": "ключ не потрібен (модель на цьому ПК)",
        "fetching": "Питаю сервіс про список моделей…", "fetched": "Знайдено моделей: {n}. Виберіть у полі «Модель».",
        "checking": "Надсилаю одне коротке питання…", "check_ok": "Працює. Відповідь: «{a}»",
        "check_paid": "Це платна модель: перевірка з вікна не робиться (кожен запит коштує грошей).",
        "fail": "Не вийшло: {e}", "need_key": "Потрібен ключ: вставте його в поле «Ключ».",
        "bad": "Перевірте поля: {f}", "saved": "Збережено «{n}». Данте братиме її в наступних задачах.",
        "builtin": "«{n}» — вбудована модель. Можна додати іншу модель цього ж сервісу: змініть модель і назву.",
        "removed": "Видалено «{n}».", "only_own": "Видаляти можна лише ваші моделі (★).",
        "paid_warn": "Платна: Данте не витратить ні копійки без двох ваших підтверджень із сумою.",
        "fields": {"name": "Назва в Данте", "base_url": "Адреса", "model": "Модель", "key_env": "Назва ключа",
                   "price_in": "ціна питання", "price_out": "ціна відповіді", "note": "Примітка",
                   "needs_key": "ключ", "paid": "платна"},
    },
    "en": {
        "title": "AI models — add or change", "all": "All models DANTE knows",
        "legend": "✓ key set   - no key   $ paid   ★ yours",
        "new": "New", "delete": "Delete", "service": "Service", "url": "Address (URL)",
        "key": "Key", "show": "show", "where": "Get a key", "key_env": "Key name",
        "model": "Model", "fetch": "Get list", "name": "Name in DANTE", "paid": "Paid model",
        "price": "Price, $ / 1M", "price_in": "input", "price_out": "output", "note": "Note",
        "check": "Check", "save": "Save", "close": "Close",
        "hint": "Choose a service, paste the key, press “Get list” and pick a model.",
        "key_saved": "✓ key saved",
        "no_key_needed": "no key needed (model on this PC)",
        "fetching": "Asking the service for its models…", "fetched": "Models found: {n}. Pick one in “Model”.",
        "checking": "Sending one short question…", "check_ok": "Works. Answer: “{a}”",
        "check_paid": "Paid model: no check from this window (every request costs money).",
        "fail": "Did not work: {e}", "need_key": "A key is needed: paste it into “Key”.",
        "bad": "Please check: {f}", "saved": "Saved “{n}”. DANTE will use it in the next tasks.",
        "builtin": "“{n}” is built in. You can add another model of the same service: change the model and name.",
        "removed": "Deleted “{n}”.", "only_own": "Only your models (★) can be deleted.",
        "paid_warn": "Paid: DANTE spends nothing without your two confirmations with the sum.",
        "fields": {"name": "Name in DANTE", "base_url": "Address", "model": "Model", "key_env": "Key name",
                   "price_in": "input price", "price_out": "output price", "note": "Note",
                   "needs_key": "key", "paid": "paid"},
    },
}


class ModelsWindow:
    def __init__(self, app, models_path: Path | None = None, keys_path: Path | None = None) -> None:
        self.app, self.tk, self.ttk = app, app.tk, app.ttk
        self.models_path = models_path or config.MODELS_FILE
        self.keys_path = keys_path or config.KEYS_FILE
        self.T = TX.get(app.lang, TX["uk"])
        self.q: queue.Queue = queue.Queue()
        self.name_touched = False
        self.editing: str | None = None  # name of the own model being edited
        tk, ttk, T, P = self.tk, self.ttk, self.T, app.P

        w = self.win = tk.Toplevel(app.root)
        w.title(f"DANTE — {T['title']}")
        w.configure(bg=P["BG"])
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        W, H = min(sw - 40, 1280), min(sh - 80, 700)
        w.geometry(f"{W}x{H}+{max(0, (sw - W) // 2)}+30")
        w.transient(app.root)
        try:
            from dante.gui import _dark_title_bar
            _dark_title_bar(w)
        except Exception:
            pass

        body = ttk.Frame(w, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=5, uniform="c")
        body.columnconfigure(1, weight=6, uniform="c")
        body.rowconfigure(0, weight=1)

        # ----- left: list of every model
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(left, text=T["all"], font=app.F(12, bold=True)).pack(anchor="w")
        ttk.Label(left, text=T["legend"], font=app.F(10), wraplength=int(W * 0.45)).pack(anchor="w", pady=(0, 4))
        frame = tk.Frame(left, bg=P["BORDER"], padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        self.lst = tk.Listbox(frame, bg=P["LOG_BG"], fg=P["LOG_FG"], selectbackground=P["ACCENT"],
                              selectforeground="#000000", highlightthickness=0, relief="flat",
                              font=(app.mono, 11), activestyle="none", exportselection=False)
        sb = ttk.Scrollbar(frame, command=self.lst.yview, style="Vertical.TScrollbar")
        self.lst.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.lst.pack(side="left", fill="both", expand=True)
        self.lst.bind("<<ListboxSelect>>", self.on_pick)
        lb = ttk.Frame(left)
        lb.pack(fill="x", pady=(8, 0))
        ttk.Button(lb, text=T["new"], command=self.new).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(lb, text=T["delete"], command=self.delete).pack(side="left", expand=True, fill="x", padx=(4, 0))

        # ----- right: the form
        f = ttk.Frame(body)
        f.grid(row=0, column=1, sticky="nsew")
        f.columnconfigure(1, weight=1)
        self.labels: dict[str, object] = {}
        r = 0

        def label(key: str, field: str | None = None):
            nonlocal r
            lab = ttk.Label(f, text=T[key])
            lab.grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
            if field:
                self.labels[field] = lab
            return lab

        label("service")
        self.preset_box = ttk.Combobox(f, values=[p.label(app.lang) for p in U.PRESETS], state="readonly")
        self.preset_box.grid(row=r, column=1, columnspan=2, sticky="ew", pady=4)
        self.preset_box.bind("<<ComboboxSelected>>", lambda e: self.apply_preset())
        r += 1
        label("url", "base_url")
        self.url = tk.StringVar()
        ttk.Entry(f, textvariable=self.url).grid(row=r, column=1, columnspan=2, sticky="ew", pady=4)
        r += 1
        label("key")
        self.key = tk.StringVar()
        self.key_entry = ttk.Entry(f, textvariable=self.key, show="•")
        self.key_entry.grid(row=r, column=1, columnspan=2, sticky="ew", pady=4)
        r += 1
        kb = ttk.Frame(f)
        kb.grid(row=r, column=1, columnspan=2, sticky="ew")
        self.show = tk.IntVar(value=0)
        ttk.Checkbutton(kb, text=T["show"], variable=self.show,
                        command=lambda: self.key_entry.configure(show="" if self.show.get() else "•")).pack(side="left")
        ttk.Button(kb, text=T["where"], command=self.open_signup).pack(side="left", padx=(8, 8))
        self.key_note = ttk.Label(kb, text="", font=app.F(10))
        self.key_note.pack(side="left")
        r += 1
        label("key_env", "key_env")
        self.key_env = tk.StringVar()
        ttk.Entry(f, textvariable=self.key_env).grid(row=r, column=1, columnspan=2, sticky="ew", pady=4)
        self.key_env.trace_add("write", lambda *a: self.update_key_note())
        r += 1
        label("model", "model")
        self.model = tk.StringVar()
        self.model_box = ttk.Combobox(f, textvariable=self.model, values=[])
        self.model_box.grid(row=r, column=1, sticky="ew", pady=4)
        self.model_box.bind("<<ComboboxSelected>>", lambda e: self.auto_name())
        self.model.trace_add("write", lambda *a: self.auto_name())
        ttk.Button(f, text=T["fetch"], command=self.fetch).grid(row=r, column=2, sticky="ew", padx=(6, 0))
        r += 1
        label("name", "name")
        self.name = tk.StringVar()
        ne = ttk.Entry(f, textvariable=self.name)
        ne.grid(row=r, column=1, columnspan=2, sticky="ew", pady=4)
        ne.bind("<Key>", lambda e: setattr(self, "name_touched", True))
        r += 1
        self.paid = tk.IntVar(value=0)
        ttk.Checkbutton(f, text=T["paid"], variable=self.paid, command=self.paid_changed).grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(8, 2))
        r += 1
        ttk.Label(f, text=T["price"]).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
        pf = ttk.Frame(f)
        pf.grid(row=r, column=1, columnspan=2, sticky="w")
        self.labels["price_in"] = ttk.Label(pf, text=T["price_in"])
        self.labels["price_in"].pack(side="left")
        self.price_in, self.price_out = tk.StringVar(value="0"), tk.StringVar(value="0")
        self.pin = ttk.Entry(pf, textvariable=self.price_in, width=8)
        self.pin.pack(side="left", padx=6)
        self.labels["price_out"] = ttk.Label(pf, text=T["price_out"])
        self.labels["price_out"].pack(side="left", padx=(10, 0))
        self.pout = ttk.Entry(pf, textvariable=self.price_out, width=8)
        self.pout.pack(side="left", padx=6)
        r += 1
        label("note", "note")
        self.note = tk.StringVar()
        ttk.Entry(f, textvariable=self.note).grid(row=r, column=1, columnspan=2, sticky="ew", pady=4)
        r += 1
        bb = ttk.Frame(f)
        bb.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(14, 6))
        for i in range(3):
            bb.columnconfigure(i, weight=1, uniform="bb")
        ttk.Button(bb, text=T["check"], style="Big.TButton", command=self.check).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(bb, text=T["save"], style="Accent.TButton", command=self.save).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(bb, text=T["close"], style="Big.TButton", command=self.close).grid(row=0, column=2, sticky="ew", padx=(4, 0))
        r += 1
        f.rowconfigure(r, weight=1)
        self.status = tk.Label(f, text=T["hint"], bg=P["BG"], fg=P["FG"], font=app.F(11), justify="left",
                               anchor="nw", wraplength=int(W * 0.47))
        self.status.grid(row=r, column=0, columnspan=3, sticky="nsew", pady=(6, 0))

        w.bind("<Escape>", lambda e: self.close())
        w.bind("<Control-s>", lambda e: (self.save(), "break")[1])
        w.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.new()
        w.after(100, self.poll)

    # ---------- helpers
    def say(self, text: str, kind: str = "") -> None:
        P = self.app.P
        colour = {"ok": P["OK"], "bad": P["ERR"], "warn": P["WARN"]}.get(kind, P["FG"])
        self.status.configure(text=text, fg=colour)

    def current_preset(self) -> U.Preset:
        labels = [p.label(self.app.lang) for p in U.PRESETS]
        v = self.preset_box.get()
        return U.PRESETS[labels.index(v)] if v in labels else U.PRESETS[0]

    def own(self) -> list[dict]:
        return models_hub.load(self.models_path)

    def refresh(self, select: str | None = None) -> None:
        self.rows = U.rows(self.models_path, self.keys_path)
        self.lst.delete(0, "end")
        for i, row in enumerate(self.rows):
            mark = ("✓" if row.has_key else "-") + ("$" if row.paid else " ") + ("★" if row.own else " ")
            self.lst.insert("end", f"{mark} {row.name:<22} {row.model}")
            if row.name == select:
                self.lst.selection_set(i)
                self.lst.see(i)

    def update_key_note(self) -> None:
        env = self.key_env.get().strip()
        if not env:
            text = self.T["no_key_needed"]
        elif models_hub.has_key(self.keys_path, env):
            text = self.T["key_saved"]
        else:
            text = ""
        self.key_note.configure(text=text)

    def paid_changed(self) -> None:
        st = "normal" if self.paid.get() else "disabled"
        self.pin.configure(state=st)
        self.pout.configure(state=st)
        if self.paid.get():
            self.say(self.T["paid_warn"], "warn")

    def auto_name(self) -> None:
        if self.name_touched or self.editing:
            return
        taken = {m["name"] for m in self.own()}
        model = self.model.get().strip()
        self.name.set(U.suggest_name(self.current_preset(), model, taken) if model else "")

    # ---------- form actions
    def new(self) -> None:
        self.editing, self.name_touched = None, False
        self.lst.selection_clear(0, "end")
        self.preset_box.set(U.PRESETS[0].label(self.app.lang))
        self.apply_preset()
        self.say(self.T["hint"])

    def apply_preset(self) -> None:
        p = self.current_preset()
        self.url.set(p.base_url)
        self.key_env.set(p.key_env)
        self.key.set("")
        self.paid.set(1 if p.paid else 0)
        self.paid_changed()
        self.model.set("")
        self.model_box.configure(values=[])
        self.note.set("")
        self.price_in.set("0")
        self.price_out.set("0")
        if not self.editing:
            self.name_touched = False
            self.name.set("")
        self.update_key_note()

    def on_pick(self, _e=None) -> None:
        sel = self.lst.curselection()
        if not sel:
            return
        row = self.rows[sel[0]]
        own = {m["name"]: m for m in self.own()}
        if row.own:
            m = own[row.name]
            self.editing, self.name_touched = row.name, True
            match = next((p for p in U.PRESETS[1:] if p.base_url and p.base_url == m["base_url"]), U.PRESETS[0])
            self.preset_box.set(match.label(self.app.lang))
            self.url.set(m["base_url"])
            self.key_env.set(m["key_env"])
            self.key.set("")
            self.model.set(m["model"])
            self.name.set(m["name"])
            self.paid.set(1 if m["paid"] else 0)
            self.price_in.set(str(m["price_in"]))
            self.price_out.set(str(m["price_out"]))
            self.note.set(m["note"])
            self.paid_changed()
            self.say("")
        else:
            prov = next(p for p in config.load_settings(Path("__no_toml__"), self.models_path).providers if p.name == row.name)
            self.editing, self.name_touched = None, False
            match = next((p for p in U.PRESETS[1:] if p.base_url == prov.base_url), U.PRESETS[0])
            self.preset_box.set(match.label(self.app.lang))
            self.url.set(prov.base_url)
            self.key_env.set(prov.api_key_env if prov.needs_key else "")
            self.key.set("")
            self.paid.set(1 if prov.paid else 0)
            self.paid_changed()
            self.model.set(prov.model)
            self.name.set("")
            self.auto_name()
            self.say(self.T["builtin"].format(n=row.name))
        self.update_key_note()

    def entry(self) -> dict:
        def num(v: str):
            try:
                return float(v.replace(",", ".").strip() or 0)
            except ValueError:
                return v  # validate() reports it
        env = self.key_env.get().strip()
        return {"name": self.name.get().strip(), "base_url": self.url.get().strip(), "model": self.model.get().strip(),
                "key_env": env, "needs_key": bool(env), "paid": bool(self.paid.get()),
                "price_in": num(self.price_in.get()) if self.paid.get() else 0.0,
                "price_out": num(self.price_out.get()) if self.paid.get() else 0.0,
                "note": self.note.get().strip()}

    def key_value(self) -> str:
        """Key from the field, else the saved one (never shown)."""
        typed = self.key.get().strip()
        if typed:
            return typed
        env = self.key_env.get().strip()
        return config._file_keys(self.keys_path).get(env, "") if env else ""

    def mark_errors(self, bad: list[str]) -> None:
        P = self.app.P
        for field, lab in self.labels.items():
            try:
                lab.configure(foreground=P["ERR"] if field in bad else P["FG2"])
            except Exception:
                pass

    def save(self) -> bool:
        e = self.entry()
        taken = {m["name"] for m in self.own() if m["name"] != self.editing}
        bad = models_hub.validate(e, taken)
        if e["needs_key"] and not self.key.get().strip() and not models_hub.has_key(self.keys_path, e["key_env"]):
            bad.append("key")
        self.mark_errors(bad)
        if bad:
            names = self.T["fields"]
            if bad == ["key"]:
                self.say(self.T["need_key"], "bad")
            else:
                self.say(self.T["bad"].format(f=", ".join(names.get(b, b) for b in bad if b != "key")), "bad")
            return False
        try:
            if self.key.get().strip():
                models_hub.set_key(self.keys_path, e["key_env"], self.key.get())
            if self.editing and self.editing != e["name"]:
                models_hub.remove(self.models_path, self.editing)
            models_hub.upsert(self.models_path, e)
        except (ValueError, OSError) as ex:
            self.say(self.T["fail"].format(e=ex), "bad")
            return False
        self.key.set("")
        self.editing, self.name_touched = e["name"], True
        self.refresh(select=e["name"])
        self.update_key_note()
        self.say(self.T["saved"].format(n=e["name"]), "ok")
        self.app.say(self.T["saved"].format(n=e["name"]), "ok")
        return True

    def delete(self) -> None:
        sel = self.lst.curselection()
        row = self.rows[sel[0]] if sel else None
        if not row or not row.own:
            self.say(self.T["only_own"], "warn")
            return
        models_hub.remove(self.models_path, row.name)
        self.refresh()
        self.new()
        self.say(self.T["removed"].format(n=row.name), "ok")

    def open_signup(self) -> None:
        url = self.current_preset().signup
        if url:
            webbrowser.open(url)

    # ---------- network (in a thread; the window never freezes)
    def _bg(self, kind: str, fn) -> None:
        def run():
            try:
                self.q.put((kind, True, fn()))
            except Exception as ex:  # shown in the window
                self.q.put((kind, False, ex))
        threading.Thread(target=run, daemon=True).start()

    def fetch(self) -> None:
        url, env = self.url.get().strip(), self.key_env.get().strip()
        if "base_url" in models_hub.validate({"base_url": url}, set()):
            self.mark_errors(["base_url"])
            self.say(self.T["bad"].format(f=self.T["fields"]["base_url"]), "bad")
            return
        key = self.key_value()
        if env and not key:
            self.say(self.T["need_key"], "bad")
            return
        self.say(self.T["fetching"])
        self._bg("fetch", lambda: U.fetch_models(url, key))

    def check(self) -> None:
        e = self.entry()
        if e["paid"]:
            self.say(self.T["check_paid"], "warn")
            return
        key = self.key_value()
        if e["needs_key"] and not key:
            self.say(self.T["need_key"], "bad")
            return
        bad = [b for b in models_hub.validate(e, set()) if b in ("base_url", "model")]
        if bad:
            self.mark_errors(bad)
            self.say(self.T["bad"].format(f=", ".join(self.T["fields"][b] for b in bad)), "bad")
            return
        self.say(self.T["checking"])
        self._bg("check", lambda: U.ping(e["base_url"], e["model"], key, paid=False))

    def poll(self) -> None:
        try:
            while True:
                kind, ok, val = self.q.get_nowait()
                if not ok:
                    self.say(self.T["fail"].format(e=val), "bad")
                elif kind == "fetch":
                    self.model_box.configure(values=val)
                    if val and not self.model.get().strip():
                        self.model.set(val[0])
                    self.say(self.T["fetched"].format(n=len(val)), "ok")
                else:
                    self.say(self.T["check_ok"].format(a=val), "ok")
        except queue.Empty:
            pass
        try:
            self.win.after(150, self.poll)
        except Exception:  # window closed
            pass

    def close(self) -> None:
        self.win.destroy()
