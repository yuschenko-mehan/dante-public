"""Spec: NETWORK PING after power-on. The internet may come minutes after the PC; the pult first checks the network
(several hosts, short TCP connects), waits with a visible note in pult.log, and starts anyway after a time limit
(local models still work).
Специфікація: ПРОЗВІН МЕРЕЖІ після ввімкнення; пульт спершу перевіряє мережу, чекає з записом у pult.log,
а після ліміту часу все одно стартує (локальні моделі працюють і без інтернету)."""
import unittest

from dante import netwait as N


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class NetwaitTest(unittest.TestCase):
    def test_hosts(self):
        hosts = [h for h, _ in N.HOSTS]
        self.assertGreaterEqual(len(hosts), 3)
        self.assertIn("github.com", hosts)

    def test_online_when_any_host_answers(self):
        self.assertTrue(N.online(connect=lambda h, p, t: h == "github.com"))
        self.assertFalse(N.online(connect=lambda h, p, t: False))

    def test_connect_exception_counts_as_down(self):
        def boom(h, p, t):
            raise OSError("no route")
        self.assertFalse(N.online(connect=boom))

    def test_waits_until_network_appears(self):
        c, notes = Clock(), []
        up_at = 95
        ok = N.wait_for_network(probe=lambda: c.now() >= up_at, sleep=c.sleep, now=c.now, say=notes.append,
                                timeout=600, interval=10)
        self.assertTrue(ok)
        self.assertGreaterEqual(c.now(), up_at)
        self.assertLess(c.now(), up_at + 11)
        self.assertTrue(any("мереж" in n.lower() for n in notes))

    def test_gives_up_after_timeout(self):
        c, notes = Clock(), []
        ok = N.wait_for_network(probe=lambda: False, sleep=c.sleep, now=c.now, say=notes.append, timeout=120, interval=10)
        self.assertFalse(ok)
        self.assertGreaterEqual(c.now(), 120)
        self.assertLess(c.now(), 140)
        self.assertTrue(any("без мережі" in n.lower() or "offline" in n.lower() for n in notes))

    def test_already_online_does_not_sleep(self):
        c = Clock()
        self.assertTrue(N.wait_for_network(probe=lambda: True, sleep=c.sleep, now=c.now, say=lambda m: None))
        self.assertEqual(c.now(), 0)

    def test_quiet_log(self):
        c, notes = Clock(), []
        N.wait_for_network(probe=lambda: False, sleep=c.sleep, now=c.now, say=notes.append, timeout=600, interval=10)
        self.assertLessEqual(len(notes), 12)          # a note about once a minute, not every 10 s


if __name__ == "__main__":
    unittest.main()
