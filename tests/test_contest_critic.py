"""Specification (Claude, 19.11.2026): LIMITED contest, critic, smart model routing. Do not edit — DANTE makes it pass.
Специфікація: ОБМЕЖЕНИЙ конкурс, критик, розумний розподіл моделей. Не змінювати — Данте має пройти.

dante/contest.py (stdlib only) — a contest wastes resources, so it is strictly limited:
  DEFAULTS = {"enabled": True, "max_models": 2, "per_day": 10, "after_failures": 1}
  should_contest(failures, used_today, settings) -> bool:
      True only if enabled and failures >= after_failures and used_today < per_day
  pick_contestants(ranked_models, already_tried, settings) -> list[str]:
      models from ranked_models (best first) that are not in already_tried, at most max_models (never more than 3
      even if settings say more); [] when the contest is not allowed by max_models <= 0

dante/critic.py (stdlib only) — a part of DANTE that criticises solutions and picks the best:
  critic_prompt(task, diff) -> str: contains the task, the diff and asks for ONLY JSON {"score": 0-10, "issues": [...]}
      (the words "score" and "issues" and "JSON" must be in the prompt)
  parse_critic(text) -> {"score": float, "issues": list[str]}: takes the first {...} JSON object in text;
      score clamped to 0..10; missing/bad -> {"score": 0.0, "issues": ["critic answer unreadable"]}; issues = strings only
  rank_solutions(cands) -> list of the same dicts, best first. A cand: {"model", "passed": bool, "score": float,
      "lines": int (changed lines), "warnings": int}. Order: passed first; then higher score; then fewer lines;
      then fewer warnings; then model name (stable, alphabetical)
  best(cands) -> dict | None: the first of rank_solutions among PASSED ones; None if none passed

dante/routing.py (stdlib only) — which model is best, from training results:
  rank_models(rows) -> list[str]: rows = [{"model", "task", "solved": bool, "attempts": int, "time_s": float}, ...]
      per model: solve rate (solved/rows); first-try rate (solved with attempts == 1 / rows); avg time of solved
      (missing -> very large). Order: solve rate desc, first-try rate desc, avg time asc, name asc.
      Rows with model "team" or starting with "team(" are ignored.
  reorder(order, ranked) -> list[str]: models of `ranked` that are in `order` come first (in ranked order),
      then the rest of `order` in its old order; nothing added, nothing lost
"""
import unittest

from dante import contest as K, critic as C, routing as R


class ContestTest(unittest.TestCase):
    S = dict(K.DEFAULTS)

    def test_defaults(self):
        self.assertEqual(K.DEFAULTS, {"enabled": True, "max_models": 2, "per_day": 10, "after_failures": 1})

    def test_should(self):
        self.assertFalse(K.should_contest(0, 0, self.S))
        self.assertTrue(K.should_contest(1, 0, self.S))
        self.assertFalse(K.should_contest(3, 10, self.S))
        self.assertFalse(K.should_contest(3, 0, dict(self.S, enabled=False)))
        self.assertFalse(K.should_contest(1, 0, dict(self.S, after_failures=2)))

    def test_pick(self):
        ranked = ["groq", "gemini", "nemotron", "qwen-groq"]
        self.assertEqual(K.pick_contestants(ranked, {"groq"}, self.S), ["gemini", "nemotron"])
        self.assertEqual(K.pick_contestants(ranked, set(), dict(self.S, max_models=9)), ranked[:3])
        self.assertEqual(K.pick_contestants(ranked, set(), dict(self.S, max_models=0)), [])
        self.assertEqual(K.pick_contestants(ranked, set(ranked), self.S), [])


class CriticTest(unittest.TestCase):
    def test_prompt(self):
        p = C.critic_prompt("Add calc", "+def add(a, b): return a + b")
        for w in ("Add calc", "+def add", "score", "issues", "JSON"):
            self.assertIn(w, p)

    def test_parse(self):
        self.assertEqual(C.parse_critic('ok {"score": 7.5, "issues": ["no docstring", 3]} end'),
                         {"score": 7.5, "issues": ["no docstring"]})
        self.assertEqual(C.parse_critic('{"score": 15}')["score"], 10.0)
        self.assertEqual(C.parse_critic('{"score": -2, "issues": []}')["score"], 0.0)
        self.assertEqual(C.parse_critic("no json here"), {"score": 0.0, "issues": ["critic answer unreadable"]})
        self.assertEqual(C.parse_critic('{"score": "high"}')["score"], 0.0)

    def test_rank_and_best(self):
        c = [{"model": "b", "passed": True, "score": 7, "lines": 30, "warnings": 0},
             {"model": "a", "passed": False, "score": 10, "lines": 5, "warnings": 0},
             {"model": "c", "passed": True, "score": 7, "lines": 12, "warnings": 2},
             {"model": "d", "passed": True, "score": 9, "lines": 80, "warnings": 5},
             {"model": "e", "passed": True, "score": 7, "lines": 12, "warnings": 1}]
        self.assertEqual([x["model"] for x in C.rank_solutions(c)], ["d", "e", "c", "b", "a"])
        self.assertEqual(C.best(c)["model"], "d")
        self.assertIsNone(C.best([c[1]]))
        self.assertIsNone(C.best([]))


class RoutingTest(unittest.TestCase):
    ROWS = [{"model": "groq", "task": "t1", "solved": True, "attempts": 1, "time_s": 5},
            {"model": "groq", "task": "t2", "solved": True, "attempts": 2, "time_s": 15},
            {"model": "gemini", "task": "t1", "solved": True, "attempts": 1, "time_s": 90},
            {"model": "gemini", "task": "t2", "solved": True, "attempts": 1, "time_s": 110},
            {"model": "qwen", "task": "t1", "solved": False, "attempts": 3, "time_s": 200},
            {"model": "qwen", "task": "t2", "solved": True, "attempts": 1, "time_s": 10},
            {"model": "team(groq+gemini)", "task": "t1", "solved": True, "attempts": 1, "time_s": 1}]

    def test_rank(self):
        self.assertEqual(R.rank_models(self.ROWS), ["gemini", "groq", "qwen"])
        self.assertEqual(R.rank_models([]), [])

    def test_ties_by_time_then_name(self):
        rows = [{"model": "b", "task": "t", "solved": True, "attempts": 1, "time_s": 5},
                {"model": "a", "task": "t", "solved": True, "attempts": 1, "time_s": 5},
                {"model": "c", "task": "t", "solved": True, "attempts": 1, "time_s": 1}]
        self.assertEqual(R.rank_models(rows), ["c", "a", "b"])

    def test_reorder(self):
        order = ["gemini", "groq", "openrouter", "local", "local-7b"]
        self.assertEqual(R.reorder(order, ["groq", "unknown", "gemini"]),
                         ["groq", "gemini", "openrouter", "local", "local-7b"])
        self.assertEqual(R.reorder(order, []), order)


if __name__ == "__main__":
    unittest.main()
