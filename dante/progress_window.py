"""DANTE progress window: a thin always-on-top bar in the bottom-right corner; click to unfold details.
It never takes the keyboard focus, so it does not disturb your work.
Вікно прогресу Данте: тонка смужка поверх вікон у правому нижньому куті; клік — розгорнути. Фокус не забирає."""
from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path

from dante import progress

ROOT = Path(__file__).resolve().parents[1]          # C:\DANTE\dante
LOG_PATH = ROOT.parent / "outbox" / "pult.log"      # C:\DANTE\outbox\pult.log
OUTBOX = LOG_PATH.parent
REFRESH_MS = 2000
BAR_HEIGHT = 30
WIDTH = 460
COLORS = {"bg": "#1b1f24", "fg": "#e2e5ea", "muted": "#a9b4bf", "green": "#3fb950", "amber": "#d29922", "grey": "#6e7681"}


def _lang() -> str:
    """Language of the main DANTE window / мова головного вікна Данте."""
    try:
        from dante import gui_logic
        return gui_logic.load_state().lang or "uk"
    except Exception:
        return "uk"


def _tail(path: Path, n: int = 400) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def _result(name: str) -> str:
    try:
        return (OUTBOX / f"{name}.txt").read_text(encoding="utf-8", errors="replace")[:20]
    except OSError:
        return ""


class ProgressWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root, self.open, self.hidden_until = root, False, 0.0
        self.lang = _lang()
        root.overrideredirect(True)                  # no title bar, no taskbar button / без заголовка
        root.attributes("-topmost", True)
        try:
            root.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        root.configure(bg=COLORS["bg"])
        bar = tk.Frame(root, bg=COLORS["bg"], height=BAR_HEIGHT)
        bar.pack(fill="x")
        self.dot = tk.Canvas(bar, width=14, height=14, bg=COLORS["bg"], highlightthickness=0)
        self.dot_id = self.dot.create_oval(2, 2, 12, 12, fill=COLORS["grey"], outline="")
        self.dot.pack(side="left", padx=(8, 4), pady=8)
        self.text = tk.Label(bar, bg=COLORS["bg"], fg=COLORS["fg"], anchor="w", font=("Segoe UI", 10))
        self.text.pack(side="left", fill="x", expand=True)
        self.btn = tk.Label(bar, text="▸", bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 11), cursor="hand2")
        self.btn.pack(side="right", padx=8)
        self.details = tk.Label(root, bg=COLORS["bg"], fg=COLORS["muted"], justify="left", anchor="nw",
                                font=("Consolas", 9), wraplength=WIDTH - 16)
        for w in (bar, self.text, self.dot, self.btn):
            w.bind("<Button-1>", lambda _e: self.toggle())
            w.bind("<Button-3>", self.menu)
        uk = self.lang == "uk"
        self.m = tk.Menu(root, tearoff=0)
        self.m.add_command(label="Сховати на годину" if uk else "Hide for 1 hour", command=self.hide_hour)
        self.m.add_command(label="Закрити" if uk else "Close", command=root.destroy)
        self.place()
        self.refresh()

    def place(self) -> None:
        """Bottom-right corner above the taskbar / правий нижній кут над панеллю задач."""
        self.root.update_idletasks()
        h = BAR_HEIGHT + (self.details.winfo_reqheight() if self.open else 0)
        x = self.root.winfo_screenwidth() - WIDTH - 12
        y = self.root.winfo_screenheight() - h - 56
        self.root.geometry(f"{WIDTH}x{h}+{x}+{y}")

    def toggle(self) -> None:
        """Fold / unfold the details / згорнути або розгорнути подробиці."""
        self.open = not self.open
        self.btn.configure(text="▾" if self.open else "▸")
        if self.open:
            self.details.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        else:
            self.details.pack_forget()
        self.place()

    def menu(self, e) -> None:
        self.m.tk_popup(e.x_root, e.y_root)

    def hide_hour(self) -> None:
        self.hidden_until = time.time() + 3600
        self.root.withdraw()

    def refresh(self) -> None:
        if self.hidden_until and time.time() >= self.hidden_until:
            self.hidden_until = 0.0
            self.root.deiconify()
        lines = _tail(LOG_PATH)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        s = progress.status_from_log(lines, now, _result)
        color = COLORS["grey"] if not s.alive else (COLORS["green"] if s.running else COLORS["amber"])
        self.dot.itemconfigure(self.dot_id, fill=color)
        self.text.configure(text=progress.bar_text(s, self.lang).lstrip("●○ "))
        if self.open:
            last = [ln[11:] for ln in lines[-8:]]
            self.details.configure(text="\n".join(progress.detail_lines(s, self.lang) + ["—"] + last))
            self.place()
        self.root.after(REFRESH_MS, self.refresh)


def main() -> None:
    root = tk.Tk()
    ProgressWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
