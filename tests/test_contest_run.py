"""Specification: the CONTEST — several models solve the same task at the same time in separate copies of the project;
the critic picks the best passing solution. OFF by default (contest.json); strictly limited per day.
Специфікація: КОНКУРС — кілька моделей одночасно розв'язують те саме завдання в окремих копіях проєкту;
критик обирає найкраще рішення, що пройшло тести. Типово ВИМКНЕНО (contest.json); суворо обмежено на день.
(Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/contest.py — already present (DEFAULTS, should_contest, pick_contestants). The master switch is
  gui_logic.contest_enabled() (default False).
dante/contest_run.py (stdlib only):
  USAGE_FILE = Path(__file__).resolve().parents[1] / "contest-usage.json"     # {"YYYY-MM-DD": count}
  used_today(path: Path, today: str) -> int          # missing/broken file -> 0
  note_use(path: Path, today: str) -> int            # +1 for today, saves, returns the new count
  SKIP = (".git", "__pycache__", "graphify-out", "target", ".dante")
  run_contest(task, test_command, root: Path, models: list[str], run_one) -> dict
      At most 3 models. For each model, IN PARALLEL (threads): copy root to a fresh temp folder
      (shutil.copytree, ignoring SKIP names), then res = run_one(model, task, test_command, copy_root).
      res has .success (bool), .files (list of rel paths), .critic_score (float or None); an exception = failed.
      cands = [{"model", "passed": res.success, "score": critic_score or 0.0,
                "lines": total line count of res.files in the copy, "warnings": 0}]
      winner = critic.best(cands). If there is a winner, copy ONLY its res.files from its copy into root.
      All temp folders are removed. Returns {"winner": model or None,
                                             "results": [(model, passed, score) in the order of `models`]}.
dante/cli.py, command run: new flag --contest. When (args.contest or gui_logic.contest_enabled()) and
  contest_run.used_today(USAGE_FILE, today) < contest.DEFAULTS["per_day"]: models = the first contest.DEFAULTS["max_models"]
  usable models of the settings (in routing order); run_one builds an LLM for that single model and calls run_task in the
  copy (critic on); then note_use(...) and print "Contest / Конкурс: winner <model>" and every (model, passed, score).
  Otherwise the normal single run.
"""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from dante import contest_run as R


class TestUsage(unittest.TestCase):
    def test_usage_counter(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "u.json"
            self.assertEqual(R.used_today(f, "2026-11-20"), 0)
            self.assertEqual(R.note_use(f, "2026-11-20"), 1)
            self.assertEqual(R.note_use(f, "2026-11-20"), 2)
            self.assertEqual(R.used_today(f, "2026-11-21"), 0)
            f.write_text("{broken", encoding="utf-8")
            self.assertEqual(R.used_today(f, "2026-11-20"), 0)


def make_root(t):
    root = Path(t) / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "t.py").write_text("test", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (root / "calc.py").write_text("old\n", encoding="utf-8")
    return root


class TestContest(unittest.TestCase):
    def test_parallel_and_best_wins(self):
        seen, lock, started = {}, threading.Lock(), []

        def run_one(model, task, test, copy_root):
            with lock:
                started.append(time.time())
                seen[model] = copy_root
            time.sleep(0.3)
            assert not (copy_root / ".git").exists()
            assert (copy_root / "tests" / "t.py").exists()
            if model == "bad":
                return SimpleNamespace(success=False, files=[], critic_score=None)
            if model == "boom":
                raise RuntimeError("model crashed")
            text = {"short": "a = 1\n", "long": "a = 1\nb = 2\nc = 3\n"}[model]
            (copy_root / "calc.py").write_text(text, encoding="utf-8")
            (copy_root / "junk.txt").write_text("not a result file", encoding="utf-8")
            return SimpleNamespace(success=True, files=["calc.py"], critic_score=8.0)

        with tempfile.TemporaryDirectory() as t:
            root = make_root(t)
            t0 = time.time()
            out = R.run_contest("task", "test", root, ["long", "bad", "short", "boom"], run_one)
            self.assertLess(time.time() - t0, 0.85, "models must run in parallel / моделі мають працювати паралельно")
            self.assertEqual(set(seen), {"long", "bad", "short"})       # at most 3 / не більше 3
            self.assertEqual(out["winner"], "short")                    # same score, fewer lines / менше рядків
            self.assertEqual(out["results"], [("long", True, 8.0), ("bad", False, 0.0), ("short", True, 8.0)])
            self.assertEqual((root / "calc.py").read_text(encoding="utf-8"), "a = 1\n")
            self.assertFalse((root / "junk.txt").exists())
            self.assertTrue((root / ".git" / "HEAD").exists())
            for p in seen.values():
                self.assertFalse(Path(p).exists(), "temp copies removed / тимчасові копії видалено")

    def test_nobody_passed_root_unchanged(self):
        def run_one(model, task, test, copy_root):
            (copy_root / "calc.py").write_text("broken\n", encoding="utf-8")
            return SimpleNamespace(success=False, files=["calc.py"], critic_score=None)
        with tempfile.TemporaryDirectory() as t:
            root = make_root(t)
            out = R.run_contest("task", "test", root, ["a", "b"], run_one)
            self.assertIsNone(out["winner"])
            self.assertEqual((root / "calc.py").read_text(encoding="utf-8"), "old\n")


class TestCliWiring(unittest.TestCase):
    def test_cli_has_contest(self):
        cli = (Path(__file__).resolve().parents[1] / "dante" / "cli.py").read_text(encoding="utf-8")
        for s in ("--contest", "contest_run", "contest_enabled", "note_use"):
            self.assertIn(s, cli)


if __name__ == "__main__":
    unittest.main()
