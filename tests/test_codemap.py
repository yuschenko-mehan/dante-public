"""Specification: DANTE looks at a MAP of the project (Graphify knowledge graph) instead of reading every file.
Специфікація: Данте дивиться на КАРТУ проєкту (граф знань Graphify), а не читає кожен файл.
(Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/codemap.py (stdlib only; Graphify is an optional external tool, `pip install graphifyy`):
  GRAPHIFY = [sys.executable, "-m", "graphify"]  # works even when Scripts/ is not on PATH (Store Python)
  def available() -> bool                        # importlib.util.find_spec("graphify") is not None
  def refresh(root: Path, run=subprocess.run, timeout: int = 120) -> bool
      run(GRAPHIFY + ["update", "."], cwd=str(root), capture_output=True, text=True, encoding="utf-8",
          errors="replace", timeout=timeout); True if returncode == 0 and root/"graphify-out"/"graph.json" exists.
      Any exception -> False.
  def context(root: Path, query: str, budget_tokens: int = 1500, run=subprocess.run, timeout: int = 120) -> str
      "" if refresh(...) is False. Otherwise
      run(GRAPHIFY + ["query", query, "--budget", str(budget_tokens)], cwd=str(root), same keywords);
      returncode not 0, an exception or empty output -> "".
      Else "PROJECT MAP (Graphify: functions, files, line numbers, calls):\n" + stdout.strip(),
      cut to at most budget_tokens * 4 characters in total.
dante/loop.py: run_task(..., map_text: str = "") — when map_text is not empty, the user prompt contains it
  (after the TEST COMMAND line, before READ-ONLY FILES).
dante/cli.py, command `run`: map_text = codemap.context(root, task) and passed to run_task.
dante/planner.py, execute_plan: map_text = codemap.context(root, step title + " " + description);
  when it is not empty, read-only sources use project_sources(root, exclude=..., budget=8000); pass map_text to run_task.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dante import codemap as C
from dante.audit import AuditLog
from dante.config import Settings
from dante.llm import LLMResponse
from dante.loop import run_task
from dante.workspace import Workspace


class FakeRun:
    """Pretends to be graphify / Удає graphify."""
    def __init__(self, root, ok=True, query_out="NODE add() [src=calc.py loc=L1]\n"):
        self.root, self.ok, self.query_out, self.calls = root, ok, query_out, []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if cmd[:4] == [sys.executable, "-m", "graphify", "update"]:
            if self.ok:
                (Path(kw["cwd"]) / "graphify-out").mkdir(exist_ok=True)
                (Path(kw["cwd"]) / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0 if self.ok else 1, "", "")
        if cmd[:4] == [sys.executable, "-m", "graphify", "query"]:
            return subprocess.CompletedProcess(cmd, 0, self.query_out, "")
        raise AssertionError(cmd)


class FakeLLM:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def complete(self, system, user):
        self.prompts.append(user)
        return LLMResponse(self.answers.pop(0), "fake:m", 1, 1, 0.0)


class TestCodemap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_available(self):
        with mock.patch("importlib.util.find_spec", return_value=None):
            self.assertFalse(C.available())
        with mock.patch("importlib.util.find_spec", return_value=object()):
            self.assertTrue(C.available())

    def test_refresh(self):
        r = FakeRun(self.root)
        self.assertTrue(C.refresh(self.root, run=r))
        cmd, kw = r.calls[0]
        self.assertEqual(cmd, [sys.executable, "-m", "graphify", "update", "."])
        self.assertEqual(kw["cwd"], str(self.root))
        self.assertFalse(C.refresh(self.root / "nope", run=FakeRun(self.root, ok=False)))
        def boom(cmd, **kw):
            raise FileNotFoundError("graphify")
        self.assertFalse(C.refresh(self.root, run=boom))

    def test_context(self):
        r = FakeRun(self.root)
        text = C.context(self.root, "how does add work", budget_tokens=500, run=r)
        self.assertTrue(text.startswith("PROJECT MAP (Graphify"))
        self.assertIn("NODE add()", text)
        self.assertEqual(r.calls[1][0], [sys.executable, "-m", "graphify", "query", "how does add work", "--budget", "500"])
        long = C.context(self.root, "q", budget_tokens=10, run=FakeRun(self.root, query_out="x" * 500))
        self.assertLessEqual(len(long), 40)
        self.assertEqual(C.context(self.root, "q", run=FakeRun(self.root, ok=False)), "")
        self.assertEqual(C.context(self.root, "q", run=FakeRun(self.root, query_out="   ")), "")


class TestLoopUsesMap(unittest.TestCase):
    def test_map_in_prompt(self):
        with tempfile.TemporaryDirectory() as t:
            proj = Path(t) / "p"
            (proj / "tests").mkdir(parents=True)
            (proj / "tests" / "test_calc.py").write_text(
                "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
                "    def test(self):\n        self.assertEqual(add(2, 3), 5)\n", encoding="utf-8")
            llm = FakeLLM(["=== FILE: calc.py ===\ndef add(a, b):\n    return a + b\n=== END FILE ==="])
            res = run_task("Write calc.add", f'"{sys.executable}" -m unittest discover -s tests',
                           Workspace(proj, ("tests",)), llm, Settings(), AuditLog(Path(t) / "audit"),
                           read_only_files=["tests/test_calc.py"], map_text="PROJECT MAP (Graphify: x)\nNODE add()")
            self.assertTrue(res.success)
            p = llm.prompts[0]
            self.assertIn("NODE add()", p)
            self.assertLess(p.index("TEST COMMAND"), p.index("PROJECT MAP"))
            self.assertLess(p.index("PROJECT MAP"), p.index("READ-ONLY FILES"))


class TestWiring(unittest.TestCase):
    def test_cli_and_planner_use_codemap(self):
        root = Path(__file__).resolve().parents[1] / "dante"
        cli = (root / "cli.py").read_text(encoding="utf-8")
        planner = (root / "planner.py").read_text(encoding="utf-8")
        self.assertIn("codemap", cli)
        self.assertIn("map_text", cli)
        self.assertIn("codemap", planner)
        self.assertIn("map_text", planner)


if __name__ == "__main__":
    unittest.main()
