"""Specification: DANTE measures himself — how much faster and more often he solves tasks after a change (e.g. the
Academy), from his own audit logs. Специфікація: Данте сам себе вимірює — наскільки швидше й частіше він
розв'язує завдання після зміни (напр. Академії), за власними журналами аудиту.
(Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/perf.py (stdlib only):
  def summarize_run(events: list[dict]) -> dict | None
      events of ONE audit file (each has "ts" ISO time and "event"). None when there is neither "task_success"
      nor "task_failed". Else {"start": datetime of the first event, "seconds": last ts - first ts (float),
      "success": bool, "attempts": attempts of task_success/task_failed, "academy": any "academy_hints" event}.
  def load_runs(audit_dir: Path) -> list[dict]
      every *.jsonl (broken lines skipped, files without a result skipped), sorted by start.
  def stats(runs: list[dict]) -> dict
      {"runs": n, "solved": k, "solve_rate": k/n, "first_try": (successes with attempts == 1)/n,
       "avg_attempts": mean attempts of successes, "avg_seconds": mean seconds of successes}; no runs -> all 0.
  def compare(runs, split: datetime) -> dict    # {"before": stats(start < split), "after": stats(start >= split)}
  def report(cmp: dict) -> str
      Ukrainian + English lines with both stats; when both avg_seconds > 0 a line containing "швидше" or "повільніше"
      and the ratio formatted like "1.8×".
dante/cli.py: `python -m dante perf --since <ISO time> [--audit-dir DIR]` prints report(compare(load_runs(DIR), since));
  DIR defaults to the audit folder next to the dante package.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dante import perf as P

T0 = datetime(2026, 11, 20, 4, 0, tzinfo=timezone.utc)


def write_run(d, name, start, seconds, result, attempts, academy=False):
    ev = [{"ts": start.isoformat(), "event": "task_start"}]
    if academy:
        ev.append({"ts": (start + timedelta(seconds=1)).isoformat(), "event": "academy_hints", "hints": ["x"]})
    if result:
        ev.append({"ts": (start + timedelta(seconds=seconds)).isoformat(), "event": result, "attempts": attempts})
    (d / f"{name}.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\nnot json\n", encoding="utf-8")


class TestPerf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        write_run(self.d, "a", T0, 300, "task_failed", 5)
        write_run(self.d, "b", T0 + timedelta(minutes=10), 120, "task_success", 3)
        write_run(self.d, "c", T0 + timedelta(minutes=20), 0, None, 0)
        write_run(self.d, "d", T0 + timedelta(hours=2), 60, "task_success", 1, academy=True)
        write_run(self.d, "e", T0 + timedelta(hours=3), 60, "task_success", 2, academy=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_summarize_and_load(self):
        runs = P.load_runs(self.d)
        self.assertEqual(len(runs), 4)
        self.assertEqual([r["success"] for r in runs], [False, True, True, True])
        self.assertEqual(runs[1]["seconds"], 120.0)
        self.assertTrue(runs[2]["academy"])
        self.assertIsNone(P.summarize_run([{"ts": T0.isoformat(), "event": "task_start"}]))

    def test_compare_and_report(self):
        cmp = P.compare(P.load_runs(self.d), T0 + timedelta(hours=1))
        b, a = cmp["before"], cmp["after"]
        self.assertEqual((b["runs"], b["solved"], b["solve_rate"]), (2, 1, 0.5))
        self.assertEqual((a["runs"], a["solved"], a["solve_rate"], a["first_try"]), (2, 2, 1.0, 0.5))
        self.assertEqual(b["avg_seconds"], 120.0)
        self.assertEqual(a["avg_attempts"], 1.5)
        text = P.report(cmp)
        self.assertIn("швидше", text)
        self.assertIn("2.0×", text)
        self.assertEqual(P.stats([])["runs"], 0)

    def test_cli(self):
        from dante import cli
        self.assertEqual(cli.main(["perf", "--since", (T0 + timedelta(hours=1)).isoformat(), "--audit-dir", str(self.d)]), 0)


if __name__ == "__main__":
    unittest.main()
