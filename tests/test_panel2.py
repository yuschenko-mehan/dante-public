"""Specification: «Панель Данте» v2 — beautiful, adapts to phone / tablet / PC screens, shows the queue forecast,
switches the critic and the contest from the phone, and starts together with the pult.
Специфікація: «Панель Данте» v2 — гарна, підлаштовується під телефон / планшет / ПК, показує прогноз черги,
перемикає критика й конкурс з телефона і запускається разом із пультом.
(Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/panel.py (stdlib only; keeps everything from tests/test_panel.py) — add:
  collect_state(base) also returns:
      "eta": text of base/"outbox"/"eta.txt" stripped ("" if missing)
      "critic": gui_logic.critic_enabled(base/"dante"/"critic.json")
      "contest": gui_logic.contest_enabled(base/"dante"/"contest.json")
  status_html(state, token) — new look (all texts still HTML-escaped):
      one <style> block; cards (class "card"); a responsive grid: "@media (min-width: 700px)" and
      "@media (min-width: 1100px)"; light theme via "prefers-color-scheme"; buttons at least 44px high ("min-height: 44px");
      shows the eta text; two switch buttons in forms POSTing to "/toggle?name=critic&t=<token>" and
      "/toggle?name=contest&t=<token>" whose labels say "Критик: увімкнено"/"Критик: вимкнено" and
      "Конкурс: увімкнено"/"Конкурс: вимкнено" according to the state.
  handler: POST /toggle?name=critic|contest&t=<token> -> flips the switch (gui_logic.set_critic / set_contest with
      base/"dante"/"critic.json" or "contest.json"), 303 redirect to "/?t=<token>"; other names -> 400; no token -> 401.
  TOKEN_FILE_NAME = "panel-token.txt"
  load_or_make_token(base) -> str     # reads base/"panel-token.txt" (stripped, >= 16 chars) or makes a new one and saves it
  start(base, port=47950, project=None, host="0.0.0.0") -> (server, thread, token)
      ThreadingHTTPServer((host, port), make_handler(base, token, project or str(base / "dante"))) in a daemon thread.
dante/pult.py: main() starts the panel once (panel.start(base)), failures only logged; the pult keeps working.
"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from dante import panel as P


def base_dir(t):
    b = Path(t)
    for d in ("outbox", "inbox", "dante"):
        (b / d).mkdir()
    (b / "outbox" / "eta.txt").write_text("Завдань: 2 · готово ≈ 07:10 (не пізніше 07:25)\n", encoding="utf-8")
    return b


class TestPanel2(unittest.TestCase):
    def test_state_and_look(self):
        with tempfile.TemporaryDirectory() as t:
            b = base_dir(t)
            st = P.collect_state(b)
            self.assertTrue(st["eta"].startswith("Завдань: 2"))
            self.assertTrue(st["critic"])
            self.assertFalse(st["contest"])
            html = P.status_html(st, "TOKEN1234567890abcd")
            for s in ("<style", "class=\"card\"", "@media (min-width: 700px)", "@media (min-width: 1100px)",
                      "prefers-color-scheme", "min-height: 44px", "готово ≈ 07:10",
                      "/toggle?name=critic&amp;t=TOKEN1234567890abcd", "/toggle?name=contest&amp;t=TOKEN1234567890abcd",
                      "Критик: увімкнено", "Конкурс: вимкнено"):
                self.assertIn(s, html.replace("/toggle?name=critic&t=", "/toggle?name=critic&amp;t=")
                                     .replace("/toggle?name=contest&t=", "/toggle?name=contest&amp;t="))
            st["eta"] = "<script>x</script>"
            self.assertNotIn("<script>x", P.status_html(st, "TOKEN1234567890abcd"))

    def test_token_file(self):
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            a = P.load_or_make_token(b)
            self.assertGreaterEqual(len(a), 16)
            self.assertEqual((b / P.TOKEN_FILE_NAME).read_text(encoding="utf-8").strip(), a)
            self.assertEqual(P.load_or_make_token(b), a)

    def test_server_and_toggles(self):
        with tempfile.TemporaryDirectory() as t:
            b = base_dir(t)
            server, thread, token = P.start(b, port=0, project="C:/p", host="127.0.0.1")
            try:
                port = server.server_address[1]
                url = f"http://127.0.0.1:{port}"
                page = urllib.request.urlopen(f"{url}/?t={token}", timeout=5).read().decode("utf-8")
                self.assertIn("Критик: увімкнено", page)

                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, *a, **k):
                        return None
                op = urllib.request.build_opener(NoRedirect)
                for name, file, want in (("critic", "critic.json", False), ("contest", "contest.json", True)):
                    with self.assertRaises(urllib.error.HTTPError) as c:
                        op.open(urllib.request.Request(f"{url}/toggle?name={name}&t={token}", data=b"", method="POST"), timeout=5)
                    self.assertEqual(c.exception.code, 303)
                    self.assertEqual(json.loads((b / "dante" / file).read_text(encoding="utf-8"))["enabled"], want)
                for bad, code in ((f"{url}/toggle?name=evil&t={token}", 400), (f"{url}/toggle?name=critic", 401)):
                    with self.assertRaises(urllib.error.HTTPError) as c:
                        op.open(urllib.request.Request(bad, data=b"", method="POST"), timeout=5)
                    self.assertEqual(c.exception.code, code)
                page = urllib.request.urlopen(f"{url}/?t={token}", timeout=5).read().decode("utf-8")
                self.assertIn("Критик: вимкнено", page)
                self.assertIn("Конкурс: увімкнено", page)
            finally:
                server.shutdown()

    def test_pult_starts_panel(self):
        src = (Path(__file__).resolve().parents[1] / "dante" / "pult.py").read_text(encoding="utf-8")
        self.assertIn("panel", src)
        self.assertIn(".start(", src)


if __name__ == "__main__":
    unittest.main()
