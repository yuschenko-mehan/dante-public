"""Specification: the critic is ON by default — after the tests pass, one model reviews the solution (score 0-10 and
issues). It can be switched off (critic.json or --no-critic).
Специфікація: критик типово УВІМКНЕНИЙ — після проходження тестів модель оцінює рішення (бал 0-10 і зауваження).
Можна вимкнути (critic.json або --no-critic).
(Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/critic.py — already present (critic_prompt, parse_critic, rank_solutions, best).
dante/gui_logic.py, add (like contest_enabled / set_contest):
  CRITIC_FILE = Path(__file__).resolve().parents[1] / "critic.json"
  critic_enabled(path=None) -> bool        # {"enabled": bool}; missing or broken file -> True
  set_critic(on: bool, path=None) -> None  # keeps other keys in the file
dante/loop.py:
  LoopResult gets: critic_score: float | None = None, critic_issues: list[str] = field(default_factory=list)
  run_task(..., critic: bool = False): when the tests pass and critic is True, make ONE extra call
      llm.complete(CRITIC_SYSTEM, critic.critic_prompt(task, text)) where text joins "=== <path> ===\\n<content>" of every
      touched file (at most 8000 characters); review = critic.parse_critic(resp.content) -> critic_score, critic_issues;
      audit.log("critic", score=..., issues=...). Any exception in the critic -> critic_score None, still a success.
      critic False -> no extra call.
dante/cli.py, command run: new flag --no-critic; critic = gui_logic.critic_enabled() and not args.no_critic;
  after the run prints "Critic / Критик: <score>/10" and each issue on its own line (when there is a score).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from dante import gui_logic as G
from dante.audit import AuditLog
from dante.config import Settings
from dante.llm import LLMError, LLMResponse
from dante.loop import run_task
from dante.workspace import Workspace

ANSWER = "=== FILE: calc.py ===\ndef add(a, b):\n    return a + b\n=== END FILE ==="


class FakeLLM:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def complete(self, system, user):
        self.calls.append((system, user))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return LLMResponse(a, "fake:m", 1, 1, 0.0)


def project(t):
    p = Path(t) / "p"
    (p / "tests").mkdir(parents=True)
    (p / "tests" / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
        "    def test(self):\n        self.assertEqual(add(2, 3), 5)\n", encoding="utf-8")
    return p


def run(t, llm, critic):
    return run_task("Write calc.add", f'"{sys.executable}" -m unittest discover -s tests',
                    Workspace(project(t), ("tests",)), llm, Settings(), AuditLog(Path(t) / "audit"),
                    read_only_files=["tests/test_calc.py"], critic=critic)


class TestCriticLoop(unittest.TestCase):
    def test_critic_scores_a_passing_solution(self):
        with tempfile.TemporaryDirectory() as t:
            llm = FakeLLM([ANSWER, 'Sure: {"score": 7, "issues": ["no docstring", 3]}'])
            res = run(t, llm, critic=True)
            self.assertTrue(res.success)
            self.assertEqual(res.critic_score, 7.0)
            self.assertEqual(res.critic_issues, ["no docstring"])
            self.assertEqual(len(llm.calls), 2)
            self.assertIn("def add", llm.calls[1][1])
            self.assertIn("score", llm.calls[1][1])

    def test_no_critic_no_extra_call(self):
        with tempfile.TemporaryDirectory() as t:
            llm = FakeLLM([ANSWER])
            res = run(t, llm, critic=False)
            self.assertTrue(res.success)
            self.assertIsNone(res.critic_score)
            self.assertEqual(len(llm.calls), 1)

    def test_critic_failure_does_not_break_success(self):
        with tempfile.TemporaryDirectory() as t:
            res = run(t, FakeLLM([ANSWER, LLMError("all models failed")]), critic=True)
            self.assertTrue(res.success)
            self.assertIsNone(res.critic_score)


class TestCriticSwitch(unittest.TestCase):
    def test_default_on_and_toggle(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "critic.json"
            self.assertTrue(G.critic_enabled(f))
            f.write_text("{broken", encoding="utf-8")
            self.assertTrue(G.critic_enabled(f))
            f.write_text(json.dumps({"enabled": True, "note": "keep"}), encoding="utf-8")
            G.set_critic(False, f)
            self.assertFalse(G.critic_enabled(f))
            self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["note"], "keep")
            G.set_critic(True, f)
            self.assertTrue(G.critic_enabled(f))

    def test_cli_wiring(self):
        cli = (Path(__file__).resolve().parents[1] / "dante" / "cli.py").read_text(encoding="utf-8")
        for s in ("--no-critic", "critic_enabled", "critic="):
            self.assertIn(s, cli)


if __name__ == "__main__":
    unittest.main()
