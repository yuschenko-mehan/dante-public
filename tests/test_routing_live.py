"""Specification: DANTE orders its models by real measured results (routing ON always).
Специфікація: Данте впорядковує моделі за реальними замірами (маршрутизація завжди УВІМКНЕНА).
(Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/routing.py (already has rank_models, reorder) — add (stdlib only):
  BENCH_RESULTS = Path(__file__).resolve().parents[2] / "bench" / "results"
  rows_from_bench(folder: Path) -> list[dict]
      all "bench-*.csv" files in folder (sorted by name), csv.DictReader. Skip a row when llm_failed is "True"/"true"/"1",
      when config contains "+" (a team, not one model), or when attempts/seconds are not numbers.
      Row -> {"model": config, "task": task, "solved": success in ("True", "true", "1"),
              "attempts": int(attempts), "time_s": float(seconds)}. Missing folder -> [].
  apply_routing(settings, folder: Path | None = None)
      rows = rows_from_bench(folder or BENCH_RESULTS); no rows -> the SAME settings object;
      else dataclasses.replace(settings, order=tuple(reorder(list(settings.order), rank_models(rows)))).
dante/config.py: load_settings(...) returns routing.apply_routing(<settings>) unless os.environ.get("DANTE_NO_ROUTING") == "1".
"""
import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dante import config, routing
from dante.config import Settings

FIELDS = ["config", "task", "run", "success", "attempts", "seconds", "prompt_tokens", "completion_tokens", "models", "llm_failed", "error"]


def write_csv(folder, name, rows):
    with (folder / name).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow(r)


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_from_bench(self):
        write_csv(self.d, "bench-2.csv", [["groq", "t1", 1, "True", 1, 4.5, 0, 0, "groq", "False", ""],
                                          ["groq+gemini", "t1", 1, "True", 1, 3, 0, 0, "", "False", ""],
                                          ["nemotron", "t2", 1, "False", 3, 60, 0, 0, "", "True", "quota"],
                                          ["qwen", "t2", 1, "False", "x", 60, 0, 0, "", "False", ""]])
        write_csv(self.d, "bench-1.csv", [["gemini", "t1", 1, "False", 3, 20.0, 0, 0, "", "False", ""]])
        (self.d / "notes.csv").write_text("junk", encoding="utf-8")
        rows = routing.rows_from_bench(self.d)
        self.assertEqual(rows, [
            {"model": "gemini", "task": "t1", "solved": False, "attempts": 3, "time_s": 20.0},
            {"model": "groq", "task": "t1", "solved": True, "attempts": 1, "time_s": 4.5}])
        self.assertEqual(routing.rows_from_bench(self.d / "missing"), [])

    def test_apply_routing(self):
        s = Settings()
        self.assertIs(routing.apply_routing(s, self.d), s)
        write_csv(self.d, "bench-1.csv", [["glm", "t1", 1, "True", 1, 5, 0, 0, "", "False", ""],
                                          ["gemini", "t1", 1, "False", 3, 9, 0, 0, "", "False", ""]])
        order = list(s.order)
        self.assertIn("glm", order)
        new = routing.apply_routing(s, self.d)
        self.assertIsInstance(new.order, tuple)
        self.assertEqual(new.order[0], "glm")
        self.assertEqual(sorted(new.order), sorted(order))

    def test_load_settings_routes(self):
        write_csv(self.d, "bench-1.csv", [["glm", "t1", 1, "True", 1, 5, 0, 0, "", "False", ""]])
        with mock.patch.object(routing, "BENCH_RESULTS", self.d), mock.patch.dict(os.environ, {"DANTE_NO_ROUTING": ""}):
            s = config.load_settings(self.d / "no.toml", self.d / "no-models.json")
            self.assertEqual(s.order[0], "glm")
        with mock.patch.object(routing, "BENCH_RESULTS", self.d), mock.patch.dict(os.environ, {"DANTE_NO_ROUTING": "1"}):
            s = config.load_settings(self.d / "no.toml", self.d / "no-models.json")
            self.assertEqual(list(s.order), list(Settings().order))


if __name__ == "__main__":
    unittest.main()
