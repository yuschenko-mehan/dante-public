"""DANTE progress window: a thin always-on-top bar in the bottom-right corner; click to unfold details.
It never takes the keyboard focus, so it does not disturb your work.
Вікно прогресу Данте: тонка смужка поверх вікон у правому нижньому куті; клік — розгорнути. Фокус не забирає."""
from __future__ import annotations

import json
import time
import tkinter as tk
from pathlib import Path

from dante import progress

ROOT = Path(__file__).resolve().parents[1]          # C:\DANTE\dante
POS_FILE = ROOT / "progress-pos.json"               # C:\DANTE\progress-pos.json
LOG_PATH = ROOT.parent / "outbox" / "pult.log"      # C:\DANTE\outbox\pult.log
OUTBOX = LOG_PATH.parent
HEARTBEAT = OUTBOX / "pult.heartbeat"
AUDIT_DIR = ROOT / "audit"
REFRESH_MS = 2000
BAR_HEIGHT = 30
WIDTH = 460
DETAIL_LINES = 14
DRAG_MIN = 4
COLORS = {"bg": "#1b1f24", "fg": "#e2e5ea", "muted": "#a9b4bf", "green": "#3fb950", "amber": "#d29922", "grey": "#6e7681"}


def clamp_pos(x: int, y: int, w: int, h: int, sw: int, sh: int) -> tuple[int, int]:
    """Keep the window fully on screen. / Тримати вікно повністю на екрані."""
    x = max(0, min(x, sw - w))
    y = max(0, min(y, sh - h))
    return x, y


def load_pos(path: Path | None = None) -> tuple[int, int] | None:
    """Load the saved window position, or None if broken/missing. / Завантажити збережену позицію вікна."""
    p = path or POS_FILE
    try:
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "x" in data and "y" in data:
            return int(data["x"]), int(data["y"])
    except Exception:
        pass
    return None


def save_pos(x: int, y: int, path: Path | None = None) -> None:
    """Save the window position to JSON. / Зберегти позицію вікна у JSON."""
    p = path or POS_FILE
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"x": x, "y": y}), encoding="utf-8")
    except Exception:
        pass


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


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _audit_events(n: int = 300) -> list:
    """Events of the newest DANTE audit log (the job working now). / Події найновішого журналу аудиту."""
    try:
        newest = max(AUDIT_DIR.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
    except (ValueError, OSError):
        return []
    out = []
    for line in (_read(newest) or "").splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _result(name: str) -> str:
    try:
        return (OUTBOX / f"{name}.txt").read_text(encoding="utf-8", errors="replace")[:20]
    except OSError:
        return ""


class ProgressWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root, self.open, self.hidden_until = root, False, 0.0
        self.lang = _lang()
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.win_start_x = 0
        self.win_start_y = 0
        self.dragging = False
        
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
        self.pult = tk.Label(bar, bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 9))
        self.pult.pack(side="right", padx=(4, 0))
        self.btn = tk.Label(bar, text="▸", bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 11), cursor="hand2")
        self.btn.pack(side="right", padx=8)
        
        # Details text widget instead of label / Текстовий віджет подробиць замість мітки
        self.details = tk.Text(root, bg=COLORS["bg"], fg=COLORS["muted"], font=("Consolas", 9),
                               height=DETAIL_LINES, width=55, bd=0, highlightthickness=0, wrap="word")
        
        for w in (bar, self.text, self.dot, self.btn, self.pult):
            w.bind("<ButtonPress-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_motion)
            w.bind("<ButtonRelease-1>", self.on_release)
            w.bind("<Button-3>", self.menu)
            
        # Bind mouse wheel on text widget for scrolling / Прив'язка коліщатка миші на тексті для прокрутки
        self.details.bind("<MouseWheel>", self.on_mouse_wheel)
        self.details.bind("<Button-3>", self.menu)

        uk = self.lang == "uk"
        self.m = tk.Menu(root, tearoff=0)
        self.m.add_command(label="Повернути в кут" if uk else "Back to the corner", command=self.back_to_corner)
        self.m.add_command(label="Сховати на годину" if uk else "Hide for 1 hour", command=self.hide_hour)
        self.m.add_command(label="Закрити" if uk else "Close", command=root.destroy)
        
        self.place()
        self.refresh()

    def on_press(self, e) -> None:
        """Handle mouse press on bar / Обробка натискання миші на смузі."""
        self.drag_start_x = e.x_root
        self.drag_start_y = e.y_root
        self.win_start_x = self.root.winfo_x()
        self.win_start_y = self.root.winfo_y()
        self.dragging = False

    def on_motion(self, e) -> None:
        """Handle mouse drag / Обробка перетягування миші."""
        dx = e.x_root - self.drag_start_x
        dy = e.y_root - self.drag_start_y
        if not self.dragging and (abs(dx) > DRAG_MIN or abs(dy) > DRAG_MIN):
            self.dragging = True
        if self.dragging:
            nx = self.win_start_x + dx
            ny = self.win_start_y + dy
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            nx, ny = clamp_pos(nx, ny, w, h, sw, sh)
            self.root.geometry(f"+{nx}+{ny}")

    def on_release(self, e) -> None:
        """Handle mouse release / Обробка відпускання миші."""
        if not self.dragging:
            self.toggle()
        else:
            save_pos(self.root.winfo_x(), self.root.winfo_y())
        self.dragging = False

    def on_mouse_wheel(self, e) -> None:
        """Scroll details text with mouse wheel / Прокручування детального тексту коліщатком миші."""
        if e.delta:
            self.details.yview_scroll(int(-1 * (e.delta / 120)), "units")
        elif e.num == 4:
            self.details.yview_scroll(-1, "units")
        elif e.num == 5:
            self.details.yview_scroll(1, "units")

    def place(self) -> None:
        """Position the window using saved pos or bottom-right corner / Розмістити вікно за збереженою позицією або в кутку."""
        self.root.update_idletasks()
        w = WIDTH
        h = BAR_HEIGHT + (self.details.winfo_reqheight() if self.open else 0)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        
        pos = load_pos()
        if pos is not None:
            x, y = clamp_pos(pos[0], pos[1], w, h, sw, sh)
        else:
            x = sw - w - 12
            y = sh - h - 56
            x, y = clamp_pos(x, y, w, h, sw, sh)
            
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def back_to_corner(self) -> None:
        """Forget saved position and return to corner / Забути збережену позицію і повернутися в кут."""
        try:
            if POS_FILE.exists():
                POS_FILE.unlink()
        except Exception:
            pass
        self.place()

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
        try:
            self._refresh()
        except Exception as e:  # never freeze: show the problem and keep going / не застигати
            self.text.configure(text=f"! {type(e).__name__}: {e}"[:80])
        self.root.after(REFRESH_MS, self.refresh)

    def _refresh(self) -> None:
        if self.hidden_until and time.time() >= self.hidden_until:
            self.hidden_until = 0.0
            self.root.deiconify()
        lines = _tail(LOG_PATH)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        s = progress.status_from_log(lines, now, _result)
        color = COLORS["grey"] if not s.alive else (COLORS["green"] if s.running else COLORS["amber"])
        self.dot.itemconfigure(self.dot_id, fill=color)
        self.text.configure(text=progress.bar_text(s, self.lang).lstrip("●○ "))
        ptxt = progress.pult_text(_read(HEARTBEAT), now, self.lang)
        self.pult.configure(text=ptxt.split(" (")[0], fg=COLORS["green"] if "●" in ptxt else COLORS["grey"])
        if self.open:
            # Check if user is currently at the bottom of the text widget / Перевірка, чи користувач на самому низу тексту
            at_bottom = self.details.yview()[1] >= 0.99
            
            live = progress.live_lines(_audit_events(), self.lang) if s.running else []
            last = [ln[11:] for ln in lines[-40:]]
            text_content = "\n".join([ptxt] + live + ["—"] + progress.detail_lines(s, self.lang) + ["—"] + last)
            
            self.details.configure(state="normal")
            self.details.delete("1.0", tk.END)
            self.details.insert("1.0", text_content)
            self.details.configure(state="disabled")
            
            if at_bottom:
                self.details.see(tk.END)
                
            self.place()


def main() -> None:
    root = tk.Tk()
    pw = ProgressWindow(root)
    try:  # drag files straight onto the bar / перетягувати файли прямо на смужку
        from dante import dropzone
        dropzone.enable(root, on_status=lambda m: pw.text.configure(text=m))
    except Exception:
        pass
    root.mainloop()


if __name__ == "__main__":
    main()
