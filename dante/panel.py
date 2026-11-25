"""
Panel module for Dante – provides token handling, state collection, HTML rendering,
task parsing, job creation and an HTTP request handler.

Модуль панелі для Данте – забезпечує роботу з токеном, збір стану, рендеринг HTML,
парсинг завдань, створення роботи та HTTP‑обробник запитів.

Only the Python standard library is used.
"""

import html
import hmac
import json
import secrets
import urllib.parse
from datetime import datetime
from pathlib import Path
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional

# Maximum allowed request body size (1 MB) / Максимально дозволений розмір тіла запиту (1 МБ)
MAX_BODY = 1_000_000

# ----------------------------------------------------------------------
# Token utilities
# ----------------------------------------------------------------------
def make_token() -> str:
    """
    Generate a random URL‑safe token with at least 16 characters.
    Generate a token using secrets.token_urlsafe and ensure the length.
    Створює випадковий URL‑безпечний токен довжиною не менше 16 символів.
    Генерує токен за допомогою secrets.token_urlsafe і гарантує довжину.
    """
    # token_urlsafe may return shorter strings; loop until length >= 16
    # token_urlsafe may return empty string only for nbytes=0, which we never use.
    # Ensure at least 16 characters.
    token = secrets.token_urlsafe()
    while len(token) < 16:
        token = secrets.token_urlsafe()
    return token

def check_token(given: Optional[str], real: Optional[str]) -> bool:
    """
    Securely compare two tokens using hmac.compare_digest.
    Returns False if either token is empty or None.
    Порівнює два токени безпечно за допомогою hmac.compare_digest.
    Повертає False, якщо будь‑який токен порожній або None.
    """
    if not given or not real:
        return False
    return hmac.compare_digest(given, real)

# ----------------------------------------------------------------------
# State collection
# ----------------------------------------------------------------------
def collect_state(base: Path) -> Dict[str, Any]:
    """
    Collect the current state of the Dante system from the given base directory.
    Returns a dictionary with keys: running, results, log, notes, lessons, queued.
    Збирає поточний стан системи Данте з вказаної базової теки.
    Повертає словник з ключами: running, results, log, notes, lessons, queued.
    """
    outbox = base / "outbox"
    inbox = base / "inbox"
    dante_dir = base / "dante"

    # Running files: *.running, stem only, sorted
    running = sorted(p.stem for p in outbox.glob("*.running") if p.is_file())

    # Results: up to 10 newest *.txt starting with "EXIT n"
    txt_files = [p for p in outbox.glob("*.txt") if p.is_file()]
    results: List[Dict[str, Any]] = []
    for p in sorted(txt_files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            first_line = p.read_text(encoding="utf-8").splitlines()[0]
        except Exception:
            continue
        if first_line.startswith("EXIT "):
            try:
                exit_code = int(first_line.split()[1])
            except Exception:
                continue
            results.append({"name": p.stem, "exit": exit_code})
            if len(results) >= 10:
                break

    # Log: last 15 lines of pult.log
    log_path = outbox / "pult.log"
    if log_path.is_file():
        log_lines = log_path.read_text(encoding="utf-8").splitlines()
        log = log_lines[-15:]
    else:
        log = []

    # Notes: last 10 lines of notifications.log
    notes_path = outbox / "notifications.log"
    if notes_path.is_file():
        notes_lines = notes_path.read_text(encoding="utf-8").splitlines()
        notes = notes_lines[-10:]
    else:
        notes = []

    # Lessons count
    lessons_path = dante_dir / "lessons.json"
    lessons = 0
    if lessons_path.is_file():
        try:
            data = json.loads(lessons_path.read_text(encoding="utf-8"))
            lessons = len(data.get("lessons", []))
        except Exception:
            lessons = 0

    # Queued count
    queued = len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0

    # ETA forecast and switches (v2) / Прогноз черги і перемикачі (v2)
    try:
        eta = (outbox / "eta.txt").read_text(encoding="utf-8").strip()
    except OSError:
        eta = ""
    from dante import gui_logic as _G
    critic = _G.critic_enabled(dante_dir / "critic.json")
    contest = _G.contest_enabled(dante_dir / "contest.json")

    return {
        "eta": eta,
        "critic": critic,
        "contest": contest,
        "running": running,
        "results": results,
        "log": log,
        "notes": notes,
        "lessons": lessons,
        "queued": queued,
    }

# ----------------------------------------------------------------------
# HTML rendering
# ----------------------------------------------------------------------
STYLE = """
:root { color-scheme: dark light; --bg:#0f1419; --card:#1a222c; --text:#e6edf3; --muted:#8b98a5; --accent:#4cc38a; --bad:#f0616d; --line:#2b3642; }
@media (prefers-color-scheme: light) { :root { --bg:#f3f5f8; --card:#ffffff; --text:#17202a; --muted:#5b6b7a; --accent:#1a8f5a; --bad:#c9323f; --line:#d8dee6; } }
* { box-sizing: border-box; }
body { margin:0; padding:12px; background:var(--bg); color:var(--text); font:16px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
h1 { font-size:1.4rem; margin:4px 4px 12px; }
h2 { font-size:1rem; margin:0 0 8px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
.grid { display:grid; grid-template-columns:1fr; gap:12px; }
@media (min-width: 700px) { .grid { grid-template-columns:1fr 1fr; } body { padding:20px; } }
@media (min-width: 1100px) { .grid { grid-template-columns:1fr 1fr 1fr; } body { max-width:1400px; margin:0 auto; } }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px; overflow:auto; }
.wide { grid-column:1 / -1; }
ul { margin:0; padding-left:1.1em; } li { margin:2px 0; word-break:break-word; }
pre { margin:0; font:13px/1.4 ui-monospace, Consolas, monospace; white-space:pre-wrap; word-break:break-word; }
.ok { color:var(--accent); } .bad { color:var(--bad); }
.eta { font-size:1.1rem; font-weight:600; }
form { margin:0; }
button, input[type=submit] { min-height: 44px; min-width: 44px; padding:10px 16px; border-radius:12px; border:1px solid var(--line); background:var(--bg); color:var(--text); font:inherit; cursor:pointer; width:100%; }
button.on { border-color:var(--accent); } button.off { border-color:var(--bad); }
textarea { width:100%; min-height:96px; padding:10px; border-radius:12px; border:1px solid var(--line); background:var(--bg); color:var(--text); font:inherit; margin-bottom:8px; }
.row { display:grid; gap:8px; grid-template-columns:1fr; } @media (min-width: 700px) { .row { grid-template-columns:1fr 1fr; } }
"""


def status_html(state: Dict[str, Any], token: str) -> str:
    """
    Render the panel page: adaptive cards for phone / tablet / PC, dark and light theme.
    All dynamic text is HTML-escaped.
    Рендерить сторінку панелі: адаптивні картки для телефона / планшета / ПК, темна і світла тема.
    Весь динамічний текст екранується.
    """
    esc = html.escape
    tk = esc(token)

    def switch(name: str, label: str, on: bool) -> str:
        state_txt = "увімкнено" if on else "вимкнено"
        cls = "on" if on else "off"
        return (f'<form method="POST" action="/toggle?name={name}&amp;t={tk}">'
                f'<button class="{cls}" type="submit">{label}: {state_txt}</button></form>')

    def lines(items, empty):
        if not items:
            return f"<p>{empty}</p>"
        return "<pre>" + "\n".join(esc(x) for x in items) + "</pre>"

    parts = [
        "<!DOCTYPE html>", '<html lang="uk">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '<meta http-equiv="refresh" content="15">',
        "<title>Данте – статус</title>", f"<style>{STYLE}</style>", "</head>", "<body>",
        "<h1>Данте – статус</h1>", '<div class="grid">',
    ]

    eta = state.get("eta") or ""
    parts.append('<div class="card wide"><h2>Прогноз черги</h2>'
                 + (f'<p class="eta">{esc(eta)}</p>' if eta else "<p>Прогнозу ще немає.</p>")
                 + f"<p>У черзі: {state.get('queued', 0)} · Уроки: {state.get('lessons', 0)}</p></div>")

    parts.append('<div class="card"><h2>Перемикачі</h2><div class="row">'
                 + switch("critic", "Критик", bool(state.get("critic", True)))
                 + switch("contest", "Конкурс", bool(state.get("contest", False))) + "</div></div>")

    run = state.get("running") or []
    parts.append('<div class="card"><h2>Запущені</h2>'
                 + ("<ul>" + "".join(f"<li>{esc(n)}</li>" for n in run) + "</ul>" if run else "<p>Немає запущених процесів.</p>")
                 + "</div>")

    res = state.get("results") or []
    items = "".join(
        f'<li class="{"ok" if r.get("exit") == 0 else "bad"}">{esc(str(r.get("name", "")))}: '
        f'{"✓" if r.get("exit") == 0 else "✗"} (exit {esc(str(r.get("exit")))})</li>' for r in res)
    parts.append('<div class="card"><h2>Результати</h2>' + (f"<ul>{items}</ul>" if res else "<p>Немає результатів.</p>") + "</div>")

    parts.append('<div class="card"><h2>Нове завдання</h2>'
                 f'<form method="POST" action="/task?t={tk}"><textarea name="task" rows="4"></textarea>'
                 '<input type="submit" value="Відправити"></form></div>')
    parts.append('<div class="card"><h2>Повідомлення</h2>' + lines(state.get("notes"), "Немає повідомлень.") + "</div>")
    parts.append('<div class="card wide"><h2>Останні рядки журналу</h2>' + lines(state.get("log"), "Журнал порожній.") + "</div>")
    parts.append("</div></body></html>")
    return "\n".join(parts)

# ----------------------------------------------------------------------
# Task parsing
# ----------------------------------------------------------------------
def parse_task(body: bytes) -> Optional[str]:
    """
    Parse an application/x-www-form-urlencoded body and extract the 'task' field.
    Returns the UTF‑8 decoded, stripped string, or None if missing/empty/too long.
    Парсить тіло application/x-www-form-urlencoded і витягує поле 'task'.
    Повертає декодований UTF‑8 рядок без пробілів, або None, якщо відсутній/порожній/завеликий.
    """
    try:
        parsed = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    except Exception:
        return None
    tasks = parsed.get("task")
    if not tasks:
        return None
    task = tasks[0].strip()
    if not task or len(task) > 2000:
        return None
    return task

# ----------------------------------------------------------------------
# Job description
# ----------------------------------------------------------------------
def job_for_task(task: str, project: str) -> Dict[str, Any]:
    """
    Build a job dictionary for the given task and project.
    Створює словник роботи для заданого завдання та проекту.
    """
    return {
        "kind": "dante",
        "args": ["run", "--project", project, "--task", task],
        "timeout": 3600,
    }

# ----------------------------------------------------------------------
# HTTP handler factory
# ----------------------------------------------------------------------
def make_handler(base: Path, token: str, project: str):
    """
    Create a subclass of BaseHTTPRequestHandler that serves the Dante panel.
    The handler checks the token, serves status page, accepts tasks, etc.
    Створює підклас BaseHTTPRequestHandler, який обслуговує панель Данте.
    Перевіряє токен, повертає сторінку статусу, приймає завдання тощо.
    """
    class DanteHandler(BaseHTTPRequestHandler):
        # Suppress default logging (which prints to stderr)
        def log_message(self, format: str, *args: Any) -> None:
            # Override to stay silent – never print the token.
            # Перевизначено, щоб не виводити нічого – ніколи не друкує токен.
            return

        def _check_token(self) -> bool:
            """Validate the 't' query parameter against the expected token."""
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            t_vals = params.get("t")
            if not t_vals:
                return False
            return check_token(t_vals[0], token)

        def do_GET(self):
            if not self._check_token():
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.end_headers()
                return

            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/":
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return

            state = collect_state(base)
            html_page = status_html(state, token)
            encoded = html_page.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_zero_length_response(self, status: HTTPStatus) -> None:
            """Send a response with Content-Length: 0. / Надіслати відповідь із Content-Length: 0."""
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except (TypeError, ValueError):
                content_length = 0

            if content_length > MAX_BODY:
                self.send_response(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                return

            try:
                body = self.rfile.read(content_length) if content_length > 0 else b""
            except Exception:
                body = b""

            if not self._check_token():
                self._send_zero_length_response(HTTPStatus.UNAUTHORIZED)
                return

            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/toggle":
                name = (urllib.parse.parse_qs(parsed.query).get("name") or [""])[0]
                if name not in ("critic", "contest"):
                    self._send_zero_length_response(HTTPStatus.BAD_REQUEST)
                    return
                from dante import gui_logic as _G
                f = base / "dante" / f"{name}.json"
                if name == "critic":
                    _G.set_critic(not _G.critic_enabled(f), f)
                else:
                    _G.set_contest(not _G.contest_enabled(f), f)
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", f"/?t={urllib.parse.quote(token)}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if parsed.path != "/task":
                self._send_zero_length_response(HTTPStatus.NOT_FOUND)
                return

            task = parse_task(body)
            if task is None:
                self._send_zero_length_response(HTTPStatus.BAD_REQUEST)
                return

            # Prepare job file name
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            rand_hex = secrets.token_hex(4)
            filename = f"web-{timestamp}-{rand_hex}.json"
            job_path = base / "inbox" / filename
            job_path.write_text(json.dumps(job_for_task(task, project), ensure_ascii=False), encoding="utf-8")

            # Redirect back to status page
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/?t={urllib.parse.quote(token)}")
            self.send_header("Content-Length", "0")
            self.end_headers()

    return DanteHandler


# ----------------------------------------------------------------------
# Token file and start (v2) / Файл токена і запуск (v2)
# ----------------------------------------------------------------------
TOKEN_FILE_NAME = "panel-token.txt"


def load_or_make_token(base: Path) -> str:
    """Read base/panel-token.txt (>= 16 chars) or make and save a new token.
    Прочитати base/panel-token.txt (>= 16 символів) або створити й зберегти новий токен."""
    path = Path(base) / TOKEN_FILE_NAME
    try:
        t = path.read_text(encoding="utf-8").strip()
        if len(t) >= 16:
            return t
    except OSError:
        pass
    t = make_token()
    path.write_text(t + "\n", encoding="utf-8")
    return t


def start(base: Path, port: int = 47950, project: Optional[str] = None, host: str = "0.0.0.0"):
    """Start the panel in a daemon thread. Returns (server, thread, token).
    Запустити панель у фоновому потоці. Повертає (server, thread, token)."""
    import threading
    from http.server import ThreadingHTTPServer
    base = Path(base)
    token = load_or_make_token(base)
    server = ThreadingHTTPServer((host, port), make_handler(base, token, project or str(base / "dante")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, token
