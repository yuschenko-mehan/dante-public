"""Specification (Claude, 19.11.2026): «Панель Данте» — DANTE's progress and tasks in any phone browser.
Специфікація: «Панель Данте» — прогрес і завдання Данте в браузері будь-якого телефона. Не змінювати — Данте має пройти.

dante/panel.py (stdlib only):
  make_token() -> str: random access code, at least 16 characters, URL-safe (secrets.token_urlsafe)
  check_token(given, real) -> bool: hmac.compare_digest; False if either is empty or None
  collect_state(base: Path) -> dict with keys:
      "running": sorted names (stem) of base/"outbox"/*.running
      "results": up to 10 newest base/"outbox"/*.txt that start with "EXIT n" (by mtime, newest first):
                 list of {"name": stem, "exit": int}; other .txt files are ignored
      "log": last 15 lines of base/"outbox"/"pult.log" (missing -> [])
      "notes": last 10 lines of base/"outbox"/"notifications.log" (missing -> [])
      "lessons": number of lessons in base/"dante"/"lessons.json" ({"lessons": [...]}; missing/bad -> 0)
      "queued": number of base/"inbox"/*.json
  status_html(state, token) -> str: a full HTML page in Ukrainian for a phone: <meta name="viewport" ...>,
      auto refresh every 15 s, title containing "Данте"; shows running, queued, results (✓ for exit 0, ✗ otherwise),
      lessons, last log lines, last notes, and a form POST "/task?t=<token>" with a textarea named "task".
      EVERY text from state is HTML-escaped (no raw "<" from data).
  parse_task(body: bytes) -> str | None: application/x-www-form-urlencoded, field "task", UTF-8; stripped;
      None if missing, empty or longer than 2000 characters
  job_for_task(task, project) -> dict: {"kind": "dante", "args": ["run", "--project", project, "--task", task],
      "timeout": 3600}
  make_handler(base: Path, token: str, project: str) -> a http.server.BaseHTTPRequestHandler subclass:
      every request needs ?t=<token> (else 401 and no data);
      GET /  -> 200, status_html(collect_state(base), token);
      POST /task -> parse_task; bad -> 400; good -> writes base/"inbox"/"web-<YYYYmmdd-HHMMSS>-<4 random hex>.json"
                    with job_for_task(task, project) and answers 303 redirect to "/?t=<token>";
      anything else -> 404. Never prints the token in logs (override log_message to stay silent).
"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from dante import panel as P


def setup_base(d: Path):
    (d / "outbox").mkdir(); (d / "inbox").mkdir(); (d / "dante").mkdir()
    (d / "outbox" / "a.running").write_text("", encoding="utf-8")
    (d / "outbox" / "ok.txt").write_text("EXIT 0\nfine", encoding="utf-8")
    (d / "outbox" / "bad.txt").write_text("EXIT 1\n<script>alert(1)</script>", encoding="utf-8")
    (d / "outbox" / "other.txt").write_text("hello", encoding="utf-8")
    (d / "outbox" / "pult.log").write_text("\n".join(f"line {i} <b>" for i in range(30)), encoding="utf-8")
    (d / "outbox" / "notifications.log").write_text("Мураха готова\n", encoding="utf-8")
    (d / "dante" / "lessons.json").write_text(json.dumps({"lessons": [{}, {}, {}]}), encoding="utf-8")
    (d / "inbox" / "q.json").write_text("{}", encoding="utf-8")


class PureTest(unittest.TestCase):
    def test_token(self):
        a, b = P.make_token(), P.make_token()
        self.assertGreaterEqual(len(a), 16); self.assertNotEqual(a, b)
        self.assertTrue(P.check_token(a, a))
        self.assertFalse(P.check_token("", a)); self.assertFalse(P.check_token(None, a)); self.assertFalse(P.check_token(a, ""))
        self.assertFalse(P.check_token(a + "x", a))

    def test_state(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); setup_base(d)
            s = P.collect_state(d)
            self.assertEqual(s["running"], ["a"])
            self.assertEqual(sorted((r["name"], r["exit"]) for r in s["results"]), [("bad", 1), ("ok", 0)])
            self.assertEqual(len(s["log"]), 15); self.assertEqual(s["log"][-1], "line 29 <b>")
            self.assertEqual(s["notes"], ["Мураха готова"])
            self.assertEqual((s["lessons"], s["queued"]), (3, 1))
            empty = Path(t) / "none"; empty.mkdir()
            s2 = P.collect_state(empty)
            self.assertEqual((s2["running"], s2["results"], s2["log"], s2["notes"], s2["lessons"], s2["queued"]), ([], [], [], [], 0, 0))

    def test_html_escapes_and_has_form(self):
        st = {"running": ["<x>"], "results": [{"name": "<y>", "exit": 0}, {"name": "z", "exit": 2}], "log": ["<b>bold</b>"],
              "notes": ["<i>"], "lessons": 5, "queued": 2}
        h = P.status_html(st, "TOK")
        self.assertIn("Данте", h); self.assertIn('name="viewport"', h); self.assertIn('name="task"', h)
        self.assertIn("/task?t=TOK", h); self.assertIn("✓", h); self.assertIn("✗", h)
        for raw in ("<x>", "<y>", "<b>bold</b>", "<i>"):
            self.assertNotIn(raw, h)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", h)

    def test_parse_task_and_job(self):
        self.assertEqual(P.parse_task("task=%D0%9F%D1%80%D0%B8%D0%B2%D1%96%D1%82+%D1%81%D0%B2%D1%96%D1%82".encode()), "Привіт світ")
        self.assertIsNone(P.parse_task(b"task=++"))
        self.assertIsNone(P.parse_task(b"other=1"))
        self.assertIsNone(P.parse_task(("task=" + "a" * 2001).encode()))
        self.assertEqual(P.job_for_task("t", "C:\\p"), {"kind": "dante", "args": ["run", "--project", "C:\\p", "--task", "t"], "timeout": 3600})


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name); setup_base(self.d)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), P.make_handler(self.d, "SECRETTOKEN12345", "C:\\proj"))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.tmp.cleanup()

    def code(self, path, data=None):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = urllib.request.build_opener(NoRedirect)
        try:
            r = op.open(urllib.request.Request(self.url + path, data=data), timeout=5)
            return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def test_needs_token(self):
        c, body = self.code("/")
        self.assertEqual(c, 401); self.assertNotIn("Мураха готова", body)
        self.assertEqual(self.code("/?t=wrong")[0], 401)

    def test_status_page(self):
        c, body = self.code("/?t=SECRETTOKEN12345")
        self.assertEqual(c, 200); self.assertIn("Данте", body); self.assertIn("Мураха готова", body)

    def test_post_task(self):
        data = urllib.parse.urlencode({"task": "Додай кнопку"}).encode()
        c, _ = self.code("/task?t=SECRETTOKEN12345", data)
        self.assertEqual(c, 303)
        jobs = list((self.d / "inbox").glob("web-*.json"))
        self.assertEqual(len(jobs), 1)
        job = json.loads(jobs[0].read_text(encoding="utf-8"))
        self.assertEqual(job["args"], ["run", "--project", "C:\\proj", "--task", "Додай кнопку"])
        self.assertEqual(self.code("/task?t=SECRETTOKEN12345", b"task=")[0], 400)
        self.assertEqual(self.code("/task?t=bad", data)[0], 401)
        self.assertEqual(self.code("/nothing?t=SECRETTOKEN12345")[0], 404)


if __name__ == "__main__":
    unittest.main()
