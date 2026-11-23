"""Spec (Claude, 23.11.2026, author's wish): the network PULSE is not constant.
While the network is up DANTE checks it once every 30 minutes; when it is down - every minute until it is back.
The log gets a line only when the state CHANGES (no spam). The pult calls pulse.tick() every round; tick() is cheap
when nothing is due (no probe at all).
Специфікація: ПУЛЬС мережі не постійний: мережа є - перевірка раз на 30 хвилин; мережі немає - щохвилини, доки
не з'явиться. У журнал - лише зміна стану. Пульт викликає pulse.tick() щоразу; якщо ще не час - мережу не чіпає.

dante/netwait.py: class NetPulse(probe=online, say=print, now=time.monotonic, online_every=1800, offline_every=60,
  status_file=None, state=None, next_at=None). Attributes: state (True/False/None), next_at (float), probes (int).
  tick() -> None when now() < next_at (no probe); otherwise probe once, probes += 1, next_at = now + online_every
  (up) or offline_every (down), say a line if state changed ('мережа пропала' / 'network lost' and
  'мережа повернулась' / 'network is back'), write status_file (text starting with 'up' or 'down') if given, return state.
  A probe that raises counts as down.
dante/pult.py main(): keep the result of wait_for_network; create netwait.NetPulse(say=say, state=<that result>,
  next_at=time.monotonic() + (1800 if up else 60), status_file=outbox / "net.status"); in the main loop call
  pulse.tick() inside the same try as sched.tick().
"""
import tempfile
import unittest
from pathlib import Path

from dante import netwait as N


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class NetPulseTest(unittest.TestCase):
    def make(self, answers, **kw):
        self.clock, self.said, self.answers = Clock(), [], list(answers)
        def probe():
            a = self.answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        return N.NetPulse(probe=probe, say=self.said.append, now=self.clock, **kw)

    def test_first_tick_probes(self):
        p = self.make([True])
        self.assertTrue(p.tick())
        self.assertEqual(p.probes, 1)
        self.assertEqual(p.next_at, 1800)

    def test_online_checks_only_every_30_minutes(self):
        p = self.make([True, True])
        p.tick()
        for t in (1, 60, 600, 1799):
            self.clock.t = t
            self.assertIsNone(p.tick())
        self.assertEqual(p.probes, 1)
        self.clock.t = 1800
        self.assertTrue(p.tick())
        self.assertEqual(p.probes, 2)

    def test_offline_checks_every_minute_until_back(self):
        p = self.make([True, False, False, True])
        p.tick()
        self.clock.t = 1800
        self.assertFalse(p.tick())
        self.assertEqual(p.next_at, 1860)
        self.clock.t = 1830
        self.assertIsNone(p.tick())
        self.clock.t = 1860
        self.assertFalse(p.tick())
        self.clock.t = 1920
        self.assertTrue(p.tick())
        self.assertEqual(p.next_at, 1920 + 1800)

    def test_log_only_on_change(self):
        p = self.make([True, True, False, False, True], state=True)
        for t in (0, 1800, 3600, 3660, 3720):
            self.clock.t = t
            p.tick()
        self.assertEqual(len(self.said), 2)
        self.assertIn("network lost", self.said[0])
        self.assertIn("мережа пропала", self.said[0])
        self.assertIn("network is back", self.said[1])

    def test_probe_error_counts_as_down(self):
        p = self.make([OSError("boom")], state=True)
        self.assertFalse(p.tick())
        self.assertEqual(p.next_at, 60)

    def test_start_state_and_next_at_from_pult(self):
        p = self.make([], state=True, next_at=1800)
        self.clock.t = 100
        self.assertIsNone(p.tick())
        self.assertEqual(p.probes, 0)

    def test_custom_intervals(self):
        p = self.make([True, False], online_every=100, offline_every=5)
        p.tick()
        self.assertEqual(p.next_at, 100)
        self.clock.t = 100
        p.tick()
        self.assertEqual(p.next_at, 105)

    def test_status_file(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "net.status"
            p = self.make([True, False], status_file=f)
            p.tick()
            self.assertTrue(f.read_text(encoding="utf-8").startswith("up"))
            self.clock.t = 1800
            p.tick()
            self.assertTrue(f.read_text(encoding="utf-8").startswith("down"))

    def test_pult_uses_pulse(self):
        src = (Path(N.__file__).parent / "pult.py").read_text(encoding="utf-8")
        self.assertIn("NetPulse(", src)
        self.assertIn("net.status", src)
        self.assertIn(".tick()", src)


if __name__ == "__main__":
    unittest.main()
