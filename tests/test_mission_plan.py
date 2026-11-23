"""Spec: PLANNER always on. Before a mission DANTE makes ONE short plan (up to up to 200 steps) and saves it in the project
(.dante/mission.json). Every attempt and every model gets only the compact plan + current files + the last error —
never the whole history — so models do not re-read everything. The plan is reused after a restart (same task).
Специфікація: ПЛАНУВАЛЬНИК завжди ввімкнений: один короткий план (до 7 кроків) перед місією, зберігається в проєкті;
кожна спроба й модель отримує лише стислий план + поточні файли + останню помилку; після перезапуску план той самий."""
import json
import tempfile
import unittest
from pathlib import Path

from dante import mission_plan as M
from dante.config import Settings
from tests.test_academy import BAD, GOOD, Fake, go

PLAN_ANSWER = "1. Read the test to learn the expected API\n2. Write calc.add returning a + b\n3. Run the tests"


class PlanTest(unittest.TestCase):
    def test_parse_numbered_steps(self):
        steps = M.parse_steps(PLAN_ANSWER + "\n" + "\n".join(f"{i}. extra" for i in range(4, 12)))
        self.assertEqual(len(steps), 11)
        self.assertEqual(steps[1], "Write calc.add returning a + b")

    def test_parse_garbage_gives_one_step(self):
        self.assertEqual(M.parse_steps("just do it"), ["just do it"])
        self.assertEqual(M.parse_steps(""), [])

    def test_plan_prompt(self):
        p = M.plan_prompt("TASK-Z")
        self.assertIn("TASK-Z", p)
        self.assertIn("200", p)
        self.assertIn("numbered", p.lower())

    def test_render_is_compact(self):
        plan = M.MissionPlan("t" * 5000, ["a" * 400] * 7)
        txt = M.render(plan)
        self.assertTrue(txt.startswith("MISSION PLAN"))
        self.assertLessEqual(len(txt), 1800)

    def test_save_and_reuse_for_the_same_task_only(self):
        with tempfile.TemporaryDirectory() as t:
            calls = []
            def ask(prompt):
                calls.append(prompt); return PLAN_ANSWER
            p1 = M.get_or_make(Path(t), "task A", ask)
            p2 = M.get_or_make(Path(t), "task A", ask)
            self.assertEqual(len(calls), 1)
            self.assertEqual(p1.steps, p2.steps)
            self.assertTrue((Path(t) / ".dante" / "mission.json").exists())
            M.get_or_make(Path(t), "task B", ask)
            self.assertEqual(len(calls), 2)

    def test_planner_failure_gives_none(self):
        with tempfile.TemporaryDirectory() as t:
            def ask(prompt):
                raise RuntimeError("down")
            self.assertIsNone(M.get_or_make(Path(t), "x", ask))

    def test_broken_file_is_replaced(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / ".dante").mkdir()
            (Path(t) / ".dante" / "mission.json").write_text("{broken", encoding="utf-8")
            self.assertEqual(M.get_or_make(Path(t), "x", lambda p: PLAN_ANSWER).steps[0], "Read the test to learn the expected API")


class LoopTest(unittest.TestCase):
    def test_default_on_for_real_runs(self):
        import os
        from dante.config import load_settings
        with tempfile.TemporaryDirectory() as t:
            os.environ["DANTE_NO_ROUTING"] = "1"
            try:
                self.assertTrue(load_settings(Path(t) / "none.toml", Path(t) / "none.json").planner_always)
            finally:
                os.environ.pop("DANTE_NO_ROUTING", None)

    def test_plan_made_once_by_main_model_and_in_every_prompt(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([PLAN_ANSWER, BAD, GOOD])
            r = go(t, main, None, attempts=3, solo=5, planner=True)
            self.assertTrue(r.success)
            prompts = [u for _, u in main.calls]
            self.assertIn("numbered", prompts[0].lower())        # first call = the plan
            for u in prompts[1:]:
                self.assertIn("MISSION PLAN", u)
                self.assertIn("Write calc.add returning a + b", u)

    def test_planner_off(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([GOOD])
            go(t, main, None, attempts=1, planner=False)
            self.assertNotIn("MISSION PLAN", main.calls[0][1])


if __name__ == "__main__":
    unittest.main()


class BigMissionTest(unittest.TestCase):
    def test_many_steps_allowed(self):
        steps = M.parse_steps("\n".join(f"{i}. s{i}" for i in range(1, 260)))
        self.assertEqual(len(steps), M.MAX_STEPS)
        self.assertEqual(M.MAX_STEPS, 200)
        self.assertIn("as many steps", M.plan_prompt("x"))

    def test_render_window_shows_now_and_done(self):
        plan = M.MissionPlan("big", [f"step {i}" for i in range(1, 151)], done=40)
        txt = M.render(plan)
        self.assertIn("150 steps, done 40", txt)
        self.assertIn("Steps 1-40 are DONE.", txt)
        self.assertIn("41. [NOW] step 41", txt)
        self.assertNotIn("step 120", txt)

    def test_step_by_step_and_resume(self):
        import sys
        from dante import loop as L
        from dante.audit import AuditLog
        from dante.workspace import Workspace
        plan = "\n".join(f"{i}. part {i}" for i in range(1, 7))     # 6 steps > 5 inline
        # half-done code: compiles, but the real tests still fail (no sub) / наполовину: компілюється, тести ще ні
        step = "=== FILE: calc.py ===\ndef add(a, b):\n    return a + b\n=== END FILE ==="
        full = "=== FILE: calc.py ===\ndef add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n=== END FILE ==="
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "p"
            (p / "tests").mkdir(parents=True)
            (p / "tests" / "test_calc.py").write_text(
                "import unittest\nfrom calc import add, sub\nclass T(unittest.TestCase):\n"
                "    def test(self):\n        self.assertEqual(add(2, 3), 5)\n        self.assertEqual(sub(5, 3), 2)\n",
                encoding="utf-8")
            s = Settings(max_fix_attempts=2, planner_always=True)
            broken = "=== FILE: calc.py ===\ndef add(a, b)\n    return\n=== END FILE ==="
            main = Fake([plan, step, step, broken, broken])        # step 3 fails both attempts / 3-й крок двічі невдалий
            r = L.run_mission("Write calc.add and calc.sub", f'"{sys.executable}" -m unittest discover -s tests',
                              Workspace(p, ("tests",)), main, s, AuditLog(Path(t) / "audit"),
                              read_only_files=["tests/test_calc.py"])
            self.assertFalse(r.success)
            saved = json.loads((p / ".dante" / "mission.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["done"], 2)
            self.assertIn("WORK ONLY ON STEP 1 of 6", main.calls[1][1])
            self.assertIn("WORK ONLY ON STEP 2 of 6", main.calls[2][1])
            # restart: no new plan, continue from step 3 to the end / перезапуск: продовжує з 3-го кроку
            main2 = Fake([step, step, step, full])
            r2 = L.run_mission("Write calc.add and calc.sub", f'"{sys.executable}" -m unittest discover -s tests',
                               Workspace(p, ("tests",)), main2, s, AuditLog(Path(t) / "audit"),
                               read_only_files=["tests/test_calc.py"])
            self.assertTrue(r2.success)
            self.assertIn("WORK ONLY ON STEP 3 of 6", main2.calls[0][1])
            self.assertEqual(len(main2.calls), 4)
            self.assertEqual(json.loads((p / ".dante" / "mission.json").read_text(encoding="utf-8"))["done"], 6)

    def test_short_plan_stays_inline(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake(["1. a\n2. b", GOOD])
            r = go(t, main, None, attempts=1, planner=True)
            self.assertTrue(r.success)
            self.assertIn("MISSION PLAN (2 steps, done 0):", main.calls[1][1])
