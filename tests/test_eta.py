"""Specification: DANTE predicts when its queue will be finished (from its own measured history).
Специфікація: Данте прогнозує, коли закінчить чергу (за власною виміряною історією).
(Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/eta.py (stdlib only):
  DEFAULTS = {"code": (90, 360), "dante": (60, 600), "notify": (35, 60), "cmd": (5, 300), "train": (800, 1500)}
      kind -> (typical seconds, worst seconds) used while there is too little history; unknown kind -> DEFAULTS["cmd"].
  kind_of(job: dict, name: str = "") -> str
      name starting with "zz-train" -> "train"; job["kind"] == "dante": "code" if "run" is in job["args"] else "dante";
      otherwise "notify" if "notify.ps1" is in job["command"] else "cmd". Missing fields never raise.
  record(hist: dict, kind: str, seconds: float, keep: int = 50) -> dict   # appends, keeps only the last `keep`; returns hist
  typical(hist, kind) -> float    # median of hist[kind] if it has >= 1 value, else DEFAULTS
  worst(hist, kind) -> float      # max of hist[kind] if it has >= 3 values, else DEFAULTS worst
  estimate(lanes: dict[str, list[str]], running: dict[str, tuple[str, float]], hist) -> tuple[float, float]
      lanes = lane -> kinds still waiting (in order); running = lane -> (kind, seconds already running).
      Per lane: the running job adds max(typical - elapsed, 5) (worst: max(worst - elapsed, 5)), plus the sum for waiting ones.
      Lanes run in parallel: the result is (max over lanes of typical sums, max over lanes of worst sums); nothing -> (0, 0).
  eta_text(now: datetime, typical_s: float, worst_s: float, jobs: int) -> str
      jobs == 0 -> "Черга порожня / Queue is empty"
      else f"Завдань: {jobs} · готово ≈ {HH:MM} (не пізніше {HH:MM}) / Jobs: {jobs} · done ≈ {HH:MM} (at the latest {HH:MM})"
      where the times are now + typical_s and now + worst_s.
dante/pult.py, Scheduler:
  when a job starts remember (kind_of(job), start time) per lane; when it is seen finished, record its duration
  and save the history to outbox/"durations.json" ({kind: [seconds, ...]}, loaded at start if present);
  at the end of every tick() write outbox/"eta.txt" = eta_text(...) for the running + waiting jobs (all *.json in inbox).
"""
import json
import os
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from dante import eta as E
from dante import pult as P


class TestEta(unittest.TestCase):
    def test_kind_of(self):
        self.assertEqual(E.kind_of({"kind": "dante", "args": ["--config", "x", "run", "--project", "p"]}), "code")
        self.assertEqual(E.kind_of({"kind": "dante", "args": ["selftest"]}), "dante")
        self.assertEqual(E.kind_of({"kind": "cmd", "command": "powershell -File C:\\DANTE\\dante\\notify.ps1 -Text x"}), "notify")
        self.assertEqual(E.kind_of({"kind": "cmd", "command": "move a b"}), "cmd")
        self.assertEqual(E.kind_of({"kind": "dante", "args": ["bench"]}, "zz-train-20261119-2151.json"), "train")
        self.assertEqual(E.kind_of({}), "cmd")

    def test_history(self):
        h = {}
        for s in (40, 60, 300):
            E.record(h, "code", s)
        self.assertEqual(E.typical(h, "code"), 60)
        self.assertEqual(E.worst(h, "code"), 300)
        self.assertEqual(E.typical({}, "code"), 90)
        self.assertEqual(E.worst({"code": [10, 20]}, "code"), 360)  # too little history / замало історії
        self.assertEqual(E.typical({}, "weird"), 5)
        h2 = {}
        for i in range(60):
            E.record(h2, "cmd", i, keep=50)
        self.assertEqual(len(h2["cmd"]), 50)
        self.assertEqual(h2["cmd"][0], 10)

    def test_estimate_parallel_lanes(self):
        h = {"code": [60, 60, 120], "cmd": [3, 3, 3], "notify": [30, 30, 30]}
        typ, wst = E.estimate({"m": ["cmd", "code", "notify"], "g": ["code"]}, {"m": ("code", 50)}, h)
        self.assertEqual(typ, 10 + 3 + 60 + 30)
        self.assertEqual(wst, 70 + 3 + 120 + 30)
        self.assertEqual(E.estimate({}, {}, h), (0, 0))
        self.assertEqual(E.estimate({}, {"x": ("code", 500)}, h), (5, 5))

    def test_text(self):
        now = datetime(2026, 11, 19, 22, 10)
        self.assertEqual(E.eta_text(now, 0, 0, 0), "Черга порожня / Queue is empty")
        self.assertEqual(E.eta_text(now, 30 * 60, 55 * 60, 7),
                         "Завдань: 7 · готово ≈ 22:40 (не пізніше 23:05) / Jobs: 7 · done ≈ 22:40 (at the latest 23:05)")


def fake_runner(cmd, **kw):
    time.sleep(0.05)
    return subprocess.CompletedProcess(cmd, 0, "ok", "")


class TestPultEta(unittest.TestCase):
    def test_pult_writes_eta_and_durations(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            inbox, outbox = base / "inbox", base / "outbox"
            inbox.mkdir()
            jobs = {"a1.json": {"kind": "cmd", "command": "echo 1", "lane": "x"},
                    "a2.json": {"kind": "cmd", "command": "echo 2", "lane": "x"},
                    "b1.json": {"kind": "dante", "args": ["run", "--task", "t"], "lane": "y"}}
            old = time.time() - 10
            for n, j in jobs.items():
                (inbox / n).write_text(json.dumps(j), encoding="utf-8")
                os.utime(inbox / n, (old, old))
            s = P.Scheduler(inbox, outbox, base, max_parallel=1, runner=fake_runner, temp=lambda: None, say=lambda m: None)
            s.tick()
            self.assertIn("Завдань: ", (outbox / "eta.txt").read_text(encoding="utf-8"))
            t0 = time.time()
            while (list(inbox.glob("*.json")) or s.running) and time.time() - t0 < 20:
                time.sleep(0.1)
                s.tick()
            s.tick()
            self.assertEqual((outbox / "eta.txt").read_text(encoding="utf-8"), "Черга порожня / Queue is empty")
            d = json.loads((outbox / "durations.json").read_text(encoding="utf-8"))
            self.assertEqual(len(d["cmd"]), 2)
            self.assertEqual(len(d["code"]), 1)
            # history survives a restart / історія переживає перезапуск
            s2 = P.Scheduler(inbox, outbox, base, max_parallel=1, runner=fake_runner, temp=lambda: None, say=lambda m: None)
            (inbox / "c.json").write_text(json.dumps({"kind": "cmd", "command": "echo 3", "lane": "x"}), encoding="utf-8")
            os.utime(inbox / "c.json", (old, old))
            t0 = time.time()
            while (list(inbox.glob("*.json")) or s2.running) and time.time() - t0 < 20:
                time.sleep(0.1)
                s2.tick()
            s2.tick()
            d = json.loads((outbox / "durations.json").read_text(encoding="utf-8"))
            self.assertEqual(len(d["cmd"]), 3)


if __name__ == "__main__":
    unittest.main()
