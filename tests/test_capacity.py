"""Spec: daily CAPACITY of every free AI — requests and tokens per minute/day, how much is left (author, 21.11.2026).
Специфікація: щоденна ПОТУЖНІСТЬ кожного безкоштовного ШІ — запити й токени, скільки лишилось."""
import csv
import tempfile
import unittest
from pathlib import Path

from dante import capacity as C


class HeadersTest(unittest.TestCase):
    def test_groq_style_headers(self):
        h = {"X-RateLimit-Limit-Requests": "14400", "x-ratelimit-remaining-requests": "14370",
             "x-ratelimit-limit-tokens": "6000", "x-ratelimit-remaining-tokens": "5810", "x-ratelimit-reset-requests": "2m59s"}
        r = C.parse_headers(h)
        self.assertEqual((r["requests_limit"], r["requests_remaining"]), (14400, 14370))
        self.assertEqual((r["tokens_limit"], r["tokens_remaining"]), (6000, 5810))
        self.assertEqual(r["reset"], "2m59s")

    def test_openrouter_style_and_garbage(self):
        r = C.parse_headers({"x-ratelimit-limit": "20", "x-ratelimit-remaining": "19"})
        self.assertEqual((r["requests_limit"], r["requests_remaining"]), (20, 19))
        r = C.parse_headers({"x-ratelimit-limit-requests": "lots"})
        self.assertIsNone(r["requests_limit"])
        self.assertEqual(C.parse_headers({}), {"requests_limit": None, "requests_remaining": None,
                                               "tokens_limit": None, "tokens_remaining": None, "reset": None})


class KnownTest(unittest.TestCase):
    def test_known_limits_have_sources(self):
        self.assertIn("gemini", C.KNOWN_LIMITS)
        for name, v in C.KNOWN_LIMITS.items():
            self.assertTrue(v.get("source"), name)


class ProbeTest(unittest.TestCase):
    def test_probe_skips_paid_and_records_errors(self):
        provs = [{"name": "groq", "paid": False}, {"name": "claude", "paid": True}, {"name": "glm", "paid": False}]

        def call(p):
            if p["name"] == "glm":
                raise RuntimeError("HTTP 429")
            return {"x-ratelimit-remaining-requests": "99", "x-ratelimit-limit-requests": "100"}, 0.5

        rows = C.probe(provs, call)
        self.assertEqual([r["name"] for r in rows], ["groq", "glm"])
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["requests_remaining"], 99)
        self.assertFalse(rows[1]["ok"])
        self.assertIn("429", rows[1]["error"])

    def test_known_limit_fills_gap(self):
        rows = C.probe([{"name": "gemini", "paid": False}], lambda p: ({}, 1.0))
        self.assertEqual(rows[0]["source"], C.KNOWN_LIMITS["gemini"]["source"])


class ReportTest(unittest.TestCase):
    def test_csv_history_grows_and_md_is_ukrainian_with_claude_line(self):
        with tempfile.TemporaryDirectory() as t:
            rows = [{"name": "groq", "ok": True, "latency_s": 0.5, "requests_limit": 100, "requests_remaining": 99,
                     "tokens_limit": None, "tokens_remaining": None, "reset": None, "error": "", "source": "headers"}]
            c, m = Path(t) / "h.csv", Path(t) / "r.md"
            C.write_report(rows, c, m, now="2026-11-23T09:50:00", claude_percent=37)
            C.write_report(rows, c, m, now="2026-11-24T09:50:00")
            hist = list(csv.DictReader(c.open(encoding="utf-8")))
            self.assertEqual(len(hist), 2)
            self.assertEqual(hist[0]["name"], "groq")
            md = m.read_text(encoding="utf-8")
            self.assertIn("Потужність ШІ", md)
            self.assertIn("groq", md)

    def test_claude_percent_from_file(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "claude.txt"
            self.assertIsNone(C.claude_percent(p))
            p.write_text("37 %\n", encoding="utf-8")
            self.assertEqual(C.claude_percent(p), 37)
            p.write_text("abc", encoding="utf-8")
            self.assertIsNone(C.claude_percent(p))

    def test_md_claude_line(self):
        with tempfile.TemporaryDirectory() as t:
            m = Path(t) / "r.md"
            C.write_report([], Path(t) / "h.csv", m, now="2026-11-23T09:50:00", claude_percent=37)
            self.assertIn("Claude: 37 %", m.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
