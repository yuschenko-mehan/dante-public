"""Specification (Claude, 19.11.2026): idle-time full load + watchdog. Do not edit — DANTE makes it pass.
Специфікація: повне навантаження в простої + сторож. Не змінювати — Данте має пройти.

dante/idle_policy.py (stdlib only):
  DEFAULTS = {"enabled": True, "idle_minutes": 10, "max_temp": 83, "busy_parallel": 2, "train_every_minutes": 120}
  load_settings(path) -> dict: DEFAULTS updated with valid values from a JSON file; missing/bad file -> DEFAULTS copy;
      a wrong value (wrong type, bool where int expected, out of range) keeps the default for that key only.
      Ranges: idle_minutes 1..240, max_temp 50..95, busy_parallel 1..32, train_every_minutes 10..1440; enabled must be bool.
  save_settings(path, settings) -> None: writes JSON (UTF-8), creating folders.
  plan_load(idle_seconds, settings, cpu_threads, gpu_temp) -> {"parallel": int, "train": bool, "reason": str}
      gpu_temp is int or None (unknown). Rules in this order:
      1) gpu_temp is not None and gpu_temp >= max_temp  -> parallel 1, train False, reason "hot"
      2) not enabled                                    -> parallel busy_parallel, train False, reason "off"
      3) idle_seconds < idle_minutes * 60               -> parallel busy_parallel, train False, reason "user"
      4) otherwise                                      -> parallel max(2, cpu_threads // 2), train True, reason "idle"
  should_train(last_train_ts, now, settings, inbox_jobs) -> bool:
      True only when inbox_jobs == 0 and (last_train_ts is None or now - last_train_ts >= train_every_minutes * 60)

dante/watchdog_logic.py (stdlib only):
  check(now, heartbeat_ts, alive, limit_s=180) -> "ok" | "restart"
      "restart" if not alive, or heartbeat_ts is None, or now - heartbeat_ts > limit_s; else "ok"
  allow_restart(history, now, max_per_hour=6) -> bool: True if fewer than max_per_hour restarts in history
      happened within the last 3600 s (history = list of timestamps)
  overdue_jobs(running, now, limits, default_limit=7200) -> list[str]: running = {job name: start ts};
      limits = {job name: seconds}; names whose run time is over their limit (or default), sorted
"""
import json
import tempfile
import unittest
from pathlib import Path

from dante import idle_policy as I
from dante import watchdog_logic as W


class IdleSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = Path(self.tmp.name) / "sub" / "idle.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults(self):
        self.assertEqual(I.DEFAULTS, {"enabled": True, "idle_minutes": 10, "max_temp": 83, "busy_parallel": 2,
                                      "train_every_minutes": 120})
        s = I.load_settings(self.p)
        self.assertEqual(s, I.DEFAULTS)
        s["enabled"] = False
        self.assertTrue(I.DEFAULTS["enabled"], "load_settings must return a copy")

    def test_roundtrip_and_partial(self):
        I.save_settings(self.p, {"enabled": False, "idle_minutes": 5})
        s = I.load_settings(self.p)
        self.assertEqual((s["enabled"], s["idle_minutes"], s["max_temp"]), (False, 5, 83))

    def test_bad_values_keep_defaults(self):
        self.p.parent.mkdir(parents=True)
        self.p.write_text(json.dumps({"enabled": "yes", "idle_minutes": 0, "max_temp": 120, "busy_parallel": True,
                                      "train_every_minutes": 30}), encoding="utf-8")
        s = I.load_settings(self.p)
        self.assertEqual(s, dict(I.DEFAULTS, train_every_minutes=30))
        self.p.write_text("{broken", encoding="utf-8")
        self.assertEqual(I.load_settings(self.p), I.DEFAULTS)


class PlanTest(unittest.TestCase):
    S = dict(I.DEFAULTS)

    def test_order_of_rules(self):
        self.assertEqual(I.plan_load(99999, self.S, 12, 85), {"parallel": 1, "train": False, "reason": "hot"})
        self.assertEqual(I.plan_load(99999, dict(self.S, enabled=False), 12, 50),
                         {"parallel": 2, "train": False, "reason": "off"})
        self.assertEqual(I.plan_load(599, self.S, 12, 50), {"parallel": 2, "train": False, "reason": "user"})
        self.assertEqual(I.plan_load(600, self.S, 12, 50), {"parallel": 6, "train": True, "reason": "idle"})
        self.assertEqual(I.plan_load(600, self.S, 12, None)["reason"], "idle")
        self.assertEqual(I.plan_load(600, self.S, 2, None)["parallel"], 2)
        self.assertEqual(I.plan_load(600, self.S, 32, 82)["parallel"], 16)

    def test_should_train(self):
        self.assertTrue(I.should_train(None, 1000.0, self.S, 0))
        self.assertFalse(I.should_train(None, 1000.0, self.S, 1))
        self.assertFalse(I.should_train(1000.0, 1000.0 + 7199, self.S, 0))
        self.assertTrue(I.should_train(1000.0, 1000.0 + 7200, self.S, 0))


class WatchdogTest(unittest.TestCase):
    def test_check(self):
        self.assertEqual(W.check(1000.0, 900.0, True), "ok")
        self.assertEqual(W.check(1000.0, 700.0, True), "restart")
        self.assertEqual(W.check(1000.0, 999.0, False), "restart")
        self.assertEqual(W.check(1000.0, None, True), "restart")
        self.assertEqual(W.check(1000.0, 980.0, True, limit_s=10), "restart")

    def test_allow_restart(self):
        now = 10000.0
        self.assertTrue(W.allow_restart([], now))
        self.assertTrue(W.allow_restart([now - 4000] * 10 + [now - 10] * 5, now))
        self.assertFalse(W.allow_restart([now - 10] * 6, now))
        self.assertTrue(W.allow_restart([now - 10] * 2, now, max_per_hour=3))

    def test_overdue(self):
        now = 10000.0
        running = {"b.json": now - 100, "a.json": now - 8000, "c.json": now - 50}
        self.assertEqual(W.overdue_jobs(running, now, {"c.json": 30}), ["a.json", "c.json"])
        self.assertEqual(W.overdue_jobs({}, now, {}), [])


if __name__ == "__main__":
    unittest.main()
