"""Loop + lessons: DANTE reads lessons before work and learns after a fixed mistake.
Цикл + уроки: Данте читає уроки перед роботою і вчиться після виправленої помилки."""
import json, sys, tempfile, unittest
from pathlib import Path

from dante import lessons as Ls
from dante.audit import AuditLog
from dante.config import Settings
from dante.llm import LLMResponse
from dante.loop import run_task
from dante.workspace import Workspace


class FakeLLM:
    """Scripted answers, records system prompts / Заготовлені відповіді, запам'ятовує системні підказки."""
    def __init__(self, answers):
        self.answers, self.systems = list(answers), []

    def complete(self, system, user):
        self.systems.append(system)
        self.prompts = getattr(self, "prompts", []) + [user]
        return LLMResponse(self.answers.pop(0), "fake:m", 1, 1, 0.0)


def edit(code):
    return f"=== FILE: calc.py ===\n{code}\n=== END FILE ==="


class LoopLessonsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        self.proj = self.d / "p"; (self.proj / "tests").mkdir(parents=True)
        (self.proj / "tests" / "test_calc.py").write_text(
            "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
            "    def test(self):\n        self.assertEqual(add(2, 3), 5)\n", encoding="utf-8")
        self.lp = self.d / "lessons.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self, llm):
        ws = Workspace(self.proj, ("tests",))
        return run_task("Write calc.add for the calculator", f'"{sys.executable}" -m unittest discover -s tests',
                        ws, llm, Settings(), AuditLog(self.d / "audit"), lessons_path=self.lp)

    def test_learns_after_fixed_mistake_and_uses_it_next_time(self):
        llm = FakeLLM([edit("def add(a, b):\n    return a - b"), edit("def add(a, b):\n    return a + b"),
                       json.dumps({"mistake": "add() subtracted", "rule": "Read the test before writing the calculator"})])
        r = self.run_it(llm)
        self.assertTrue(r.success)
        self.assertEqual([x["rule"] for x in Ls.load(self.lp)], ["Read the test before writing the calculator"])
        self.assertIn("calculator", Ls.load(self.lp)[0]["tags"])
        llm2 = FakeLLM([edit("def add(a, b):\n    return a + b")])
        self.assertTrue(self.run_it(llm2).success)
        self.assertIn("Read the test before writing the calculator", llm2.systems[0])
        self.assertIn("Ukrainian", llm2.systems[0])

    def test_no_lesson_on_first_try_and_bad_answer_ignored(self):
        self.assertTrue(self.run_it(FakeLLM([edit("def add(a, b):\n    return a + b")])).success)
        self.assertEqual(Ls.load(self.lp), [])
        r = self.run_it(FakeLLM([edit("def add(a, b):\n    return 0"), edit("def add(a, b):\n    return a + b"), "no json"]))
        self.assertTrue(r.success)
        self.assertEqual(Ls.load(self.lp), [])




class ZeroTestsTest(unittest.TestCase):
    """A check that ran no tests is not a pass / Перевірка без тестів — не успіх."""

    def test_detects(self):
        from dante.loop import no_tests_ran
        self.assertTrue(no_tests_ran("running 0 tests\ntest result: ok. 0 passed; 0 failed; 0 ignored; 3 filtered out"))
        self.assertTrue(no_tests_ran("Ran 0 tests in 0.000s\n\nOK"))
        self.assertFalse(no_tests_ran("test result: ok. 3 passed; 0 failed\ntest result: ok. 0 passed; 0 failed"))
        self.assertFalse(no_tests_ran("Ran 5 tests in 0.1s\nOK"))

    def test_loop_retries_when_zero_tests(self):
        d = Path(tempfile.mkdtemp()); (d / "tests").mkdir()
        (d / "tests" / "test_x.py").write_text("", encoding="utf-8")  # no tests yet / ще без тестів
        llm = FakeLLM([edit("x = 1"), edit("x = 2"), edit("x = 3")])
        r = run_task("t", f'"{sys.executable}" -m unittest discover -s tests', Workspace(d, ("tests",)), llm,
                     Settings(), AuditLog(d / "audit"))
        self.assertFalse(r.success)
        self.assertIn("NO TESTS RAN", llm.prompts[-1] if hasattr(llm, "prompts") else "NO TESTS RAN")




class StepContextTest(unittest.TestCase):
    """A plan step sees the project's existing code / Крок плану бачить наявний код проєкту."""

    def test_sources_listed_smallest_first_within_budget(self):
        from dante.planner import project_sources
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir(); (d / "target").mkdir()
        (d / "src" / "protocol.rs").write_text("pub fn format_line() {}\n" * 10, encoding="utf-8")
        (d / "src" / "lib.rs").write_text("pub mod protocol;\n", encoding="utf-8")
        (d / "target" / "junk.rs").write_text("x", encoding="utf-8")
        (d / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
        self.assertEqual(project_sources(d), ["Cargo.toml", "src/lib.rs", "src/protocol.rs"])
        self.assertEqual(project_sources(d, exclude={"src/lib.rs"}, budget=40), ["Cargo.toml"])




class TimeoutTreeTest(unittest.TestCase):
    """A hung test with a child process must not hang DANTE / Завислий тест з дочірнім процесом не вішає Данте."""

    def test_grandchild_holding_pipe(self):
        import time
        from dante.runner import run_command
        code = ("import subprocess, sys, time; "
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)")
        t = time.monotonic()
        r = run_command(f'"{sys.executable}" -c "{code}"', Path(tempfile.gettempdir()), timeout_s=2)
        self.assertEqual(r.exit_code, 124)
        self.assertLess(time.monotonic() - t, 15)


if __name__ == "__main__":
    unittest.main()
