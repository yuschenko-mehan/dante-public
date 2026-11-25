"""Spec (Claude, 23.11.2026): the phone panel must never break a connection on a POST it rejects.
Root cause of the flaky test_post_task: on 401/404/400 the handler answered WITHOUT reading the request body;
Windows then resets the socket (WinError 10053/10054) and the phone sees a broken page.
Rule: do_POST first reads the whole body (Content-Length), at most MAX_BODY = 1_000_000 bytes; a bigger body gets
413 without reading it and "Connection: close". Every error answer sends "Content-Length: 0".
Специфікація: панель телефона не рве з'єднання на відхиленому POST: спершу дочитати тіло запиту (до 1 МБ),
більше — 413 і закрити з'єднання; кожна відповідь-помилка має Content-Length: 0."""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from dante import panel as P
from tests.test_panel import setup_base

PCODE = "-".join(["test", "panel", "code"])  # fake test code, not a secret / тестовий код, не секрет


class PanelPost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        setup_base(self.d)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), P.make_handler(self.d, PCODE, "C:\\proj"))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def post(self, path, body):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            c.request("POST", path, body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
            r = c.getresponse()
            data = r.read()
            return r.status, r.getheader("Content-Length"), data
        finally:
            c.close()

    def test_max_body_constant(self):
        self.assertEqual(P.MAX_BODY, 1_000_000)

    def test_bad_token_with_big_body_never_breaks(self):
        body = b"task=" + b"a" * 200_000
        for _ in range(25):
            status, length, _ = self.post("/task?t=wrong", body)
            self.assertEqual(status, 401)
            self.assertEqual(length, "0")

    def test_unknown_path_with_body_never_breaks(self):
        body = b"x=" + b"b" * 150_000
        for _ in range(25):
            status, length, _ = self.post(f"/nothing?t={PCODE}", body)
            self.assertEqual(status, 404)
            self.assertEqual(length, "0")

    def test_bad_task_answer_has_zero_length(self):
        status, length, _ = self.post(f"/task?t={PCODE}", b"task=")
        self.assertEqual(status, 400)
        self.assertEqual(length, "0")

    def test_too_big_body_is_413(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            c.putrequest("POST", f"/task?t={PCODE}")
            c.putheader("Content-Length", str(P.MAX_BODY + 1))
            c.endheaders()
            r = c.getresponse()
            self.assertEqual(r.status, 413)
            self.assertEqual((r.getheader("Connection") or "").lower(), "close")
        finally:
            c.close()
        self.assertEqual(list((self.d / "inbox").glob("web-*.json")), [])

    def test_good_task_still_works(self):
        status, _, _ = self.post(f"/task?t={PCODE}", "task=Привіт".encode("utf-8").replace(
            "Привіт".encode("utf-8"), b"%D0%9F%D1%80%D0%B8%D0%B2%D1%96%D1%82"))
        self.assertEqual(status, 303)
        jobs = list((self.d / "inbox").glob("web-*.json"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(json.loads(jobs[0].read_text(encoding="utf-8"))["args"][-1], "Привіт")


if __name__ == "__main__":
    unittest.main()
