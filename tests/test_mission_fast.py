"""Spec (Claude, 23.11.2026): the Planner must not waste free quota.
1) EARLY FINISH: after every successful step that is not the last, run_mission runs the REAL test command; if it passes
   (and tests really ran), the mission is finished: plan.done = number of steps, saved; audit event "mission_early_done".
2) CRITIC ONCE: steps run without the critic; when run_mission(..., critic=True) finishes successfully (last step or
   early finish) the critic is asked exactly ONCE for the whole mission (all files touched by all steps).
3) SHORT PLANS: plan_prompt asks for the FEWEST steps; a bug fix or a change in 1-2 files is 1-3 steps.
Специфікація: Планувальник не марнує безкоштовні ліміти: раннє завершення, коли справжні тести вже проходять;
критик лише один раз у кінці місії; план — найменша кількість кроків."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from dante import loop as L
from dante import mission_plan as M
from dante.audit import AuditLog
from dante.config import Settings
from dante.workspace import Workspace
from tests.test_academy import Fake

PLAN6 = "\n".join(f"{i}. part {i}" for i in range(1, 7))
HALF = "=== FILE: calc.py ===\ndef add(a, b):\n    return a + b\n=== END FILE ==="
FULL = ("=== FILE: calc.py ===\ndef add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
        "=== END FILE ===")
CRITIC = '{"score": 9, "issues": ["fine"]}'


def project(t):
    p = Path(t) / "p"
    (p / "tests").mkdir(parents=True)
    (p / "tests" / "test_calc.py").write_text(
        "import unittest\nfrom calc import add, sub\nclass T(unittest.TestCase):\n"
        "    def test(self):\n        self.assertEqual(add(2, 3), 5)\n        self.assertEqual(sub(5, 3), 2)\n",
        encoding="utf-8")
    return p


def mission(t, main, **kw):
    p = project(t)
    r = L.run_mission("Write calc.add and calc.sub", f'"{sys.executable}" -m unittest discover -s tests',
                      Workspace(p, ("tests",)), main, Settings(max_fix_attempts=2, planner_always=True),
                      AuditLog(Path(t) / "audit"), read_only_files=["tests/test_calc.py"], **kw)
    return p, r


def events(t):
    out = []
    for f in (Path(t) / "audit").glob("*.jsonl"):
        out += [json.loads(x)["event"] for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    return out


class MissionFast(unittest.TestCase):
    def test_early_finish_after_first_step(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([PLAN6, FULL])
            p, r = mission(t, main)
            self.assertTrue(r.success)
            self.assertEqual(len(main.calls), 2)          # plan + one step / план + один крок
            saved = json.loads((p / ".dante" / "mission.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["done"], 6)
            self.assertIn("mission_early_done", events(t))

    def test_no_early_finish_while_real_tests_fail(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([PLAN6, HALF, HALF, FULL])
            p, r = mission(t, main)
            self.assertTrue(r.success)
            self.assertEqual(len(main.calls), 4)
            self.assertIn("WORK ONLY ON STEP 3 of 6", main.calls[3][1])
            self.assertEqual(json.loads((p / ".dante" / "mission.json").read_text(encoding="utf-8"))["done"], 6)

    def test_critic_only_once_for_the_mission(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([PLAN6, HALF, FULL, CRITIC])
            p, r = mission(t, main, critic=True)
            self.assertTrue(r.success)
            systems = [c[0] for c in main.calls]
            self.assertEqual(systems.count(L.CRITIC_SYSTEM), 1)
            self.assertEqual(systems[-1], L.CRITIC_SYSTEM)
            self.assertEqual(r.critic_score, 9.0)
            self.assertIn("calc.py", main.calls[-1][1])
            self.assertEqual(events(t).count("critic"), 1)

    def test_no_critic_when_mission_fails(self):
        with tempfile.TemporaryDirectory() as t:
            broken = "=== FILE: calc.py ===\ndef add(a, b)\n    return\n=== END FILE ==="
            main = Fake([PLAN6, broken, broken])
            p, r = mission(t, main, critic=True)
            self.assertFalse(r.success)
            self.assertNotIn(L.CRITIC_SYSTEM, [c[0] for c in main.calls])

    def test_plan_prompt_prefers_few_steps(self):
        p = M.plan_prompt("TASK-Q")
        self.assertIn("FEWEST", p)
        self.assertIn("1-3", p)
        self.assertIn("200", p)
        self.assertIn("TASK-Q", p)


if __name__ == "__main__":
    unittest.main()
