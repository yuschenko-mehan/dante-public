"""Specification: the ACADEMY. After a failed attempt (not the last one) DANTE shows the task, the current code and the
error to SEVERAL other free models at once (up to 3, in parallel); each gives the root cause and one precise hint;
the next attempt sees all hints. One teacher may fail — the others still help.
Специфікація: АКАДЕМІЯ. Після невдалої спроби (не останньої) Данте одночасно показує завдання, код і помилку
КІЛЬКОМ іншим безкоштовним моделям (до 3, паралельно); кожна дає причину й одну точну підказку; наступна спроба
бачить усі підказки. Один учитель може не впоратися — інші допоможуть.
(Claude, 20.11.2026.)

dante/loop.py: TEACHER_SYSTEM, teacher_prompt(task, code, error) (code <= 6000 chars, error = last 3000 chars,
  mentions "root cause" and "hint"); run_task(..., teacher=None) where teacher is one LLM or a list of LLMs (max 3 used,
  asked in parallel threads); hints that fail or are empty are skipped; the next prompt contains
  "ACADEMY HINTS (from other models):" and "1) <hint>", "2) <hint>" ... ; audit event "academy_hints".
dante/cli.py run: academy ON by default — up to 3 single-model LLMs for the models after the first one in the
  routing order (each built with dataclasses.replace(s, order=(name,))); --no-teacher switches it off.
"""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from dante import loop as L
from dante.audit import AuditLog
from dante.config import Settings
from dante.llm import LLMError, LLMResponse
from dante.workspace import Workspace

BAD = "=== FILE: calc.py ===\ndef add(a, b):\n    return a - b\n=== END FILE ==="
GOOD = "=== FILE: calc.py ===\ndef add(a, b):\n    return a + b\n=== END FILE ==="


class Fake:
    def __init__(self, answers, delay=0.0):
        self.answers, self.calls, self.delay = list(answers), [], delay

    def complete(self, system, user):
        self.calls.append((system, user))
        time.sleep(self.delay)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return LLMResponse(a, "fake:m", 1, 1, 0.0)


def go(t, main, teacher, attempts=3, solo=1, briefing=False):
    p = Path(t) / "p"
    (p / "tests").mkdir(parents=True)
    (p / "tests" / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
        "    def test(self):\n        self.assertEqual(add(2, 3), 5)\n", encoding="utf-8")
    return L.run_task("Write calc.add", f'"{sys.executable}" -m unittest discover -s tests', Workspace(p, ("tests",)),
                      main, Settings(max_fix_attempts=attempts, solo_attempts=solo, academy_briefing=briefing), AuditLog(Path(t) / "audit"),
                      read_only_files=["tests/test_calc.py"], teacher=teacher)


class TestAcademy(unittest.TestCase):
    def test_prompt(self):
        p = L.teacher_prompt("TASK-X", "c" * 9000, "e" * 5000 + "TAIL")
        self.assertIn("TASK-X", p)
        self.assertIn("root cause", p.lower())
        self.assertIn("hint", p.lower())
        self.assertIn("TAIL", p)
        self.assertLess(p.count("c"), 6100)
        self.assertLess(p.count("e"), 3100)

    def test_several_teachers_in_parallel(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([BAD, GOOD])
            a = Fake(["Root cause: minus. Hint: use a + b."], delay=0.4)
            b = Fake([LLMError("quota")], delay=0.4)
            c = Fake(["Hint: addition, not subtraction."], delay=0.4)
            t0 = time.time()
            res = go(t, main, [a, b, c, Fake(["never asked"])])
            self.assertTrue(res.success)
            self.assertLess(time.time() - t0, 3.0)
            p = main.calls[1][1]
            self.assertIn("ACADEMY HINTS (from other models):", p)
            self.assertIn("use a + b", p)
            self.assertIn("addition, not subtraction", p)
            self.assertIn("return a - b", a.calls[0][1])
            self.assertIn("AssertionError", a.calls[0][1])
            log = next((Path(t) / "audit").glob("*.jsonl")).read_text(encoding="utf-8")
            self.assertIn("academy_hints", log)

    def test_single_teacher_and_not_after_last(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([BAD, BAD])
            one = Fake(["Hint: plus", "never"])
            res = go(t, main, one, attempts=2)
            self.assertFalse(res.success)
            self.assertEqual(len(one.calls), 1)

    def test_no_teacher(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([BAD, GOOD])
            self.assertTrue(go(t, main, None).success)
            self.assertNotIn("ACADEMY HINTS", main.calls[1][1])

    def test_cli_wiring(self):
        cli = (Path(__file__).resolve().parents[1] / "dante" / "cli.py").read_text(encoding="utf-8")
        for s in ("--no-teacher", "teacher="):
            self.assertIn(s, cli)


class TestSoloAttempts(unittest.TestCase):
    """Two own mistakes first; the Academy is asked only before the third attempt. / Дві власні помилки, Академія — на третю."""

    def test_default_is_two_solo_attempts(self):
        self.assertEqual(Settings().solo_attempts, 2)

    def test_academy_not_asked_after_first_failure(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([BAD, BAD, GOOD])
            teacher = Fake(["Root cause: minus. Hint: use a + b."])
            r = go(t, main, teacher, attempts=3, solo=2)
            self.assertTrue(r.success)
            self.assertEqual(r.attempts, 3)
            self.assertEqual(len(teacher.calls), 1)          # asked once: after the 2nd failure
            self.assertNotIn("ACADEMY HINTS", main.calls[1][1])         # 2nd attempt had no hints
            self.assertIn("ACADEMY HINTS", main.calls[2][1])            # 3rd attempt got the hint

    def test_one_solo_attempt_keeps_old_behaviour(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([BAD, GOOD])
            teacher = Fake(["Root cause: minus. Hint: use a + b."])
            r = go(t, main, teacher, attempts=3, solo=1)
            self.assertTrue(r.success)
            self.assertEqual(len(teacher.calls), 1)


if __name__ == "__main__":
    unittest.main()
