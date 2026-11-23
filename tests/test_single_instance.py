"""Spec: dante/single_instance.py - one copy of a program (watchdog) via an OS file lock.
Специфікація: dante/single_instance.py - лише одна копія програми (сторожа) через замок файлу ОС."""
import tempfile
import unittest
from pathlib import Path

from dante import single_instance as S


class SingleInstance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lock = Path(self.tmp.name) / "sub" / "watchdog.lock"

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_acquire_works_and_creates_folder(self):
        h = S.acquire(self.lock)
        self.assertIsNotNone(h)
        self.assertTrue(self.lock.exists())
        S.release(h)

    def test_second_acquire_refused_while_held(self):
        h = S.acquire(self.lock)
        self.assertIsNotNone(h)
        self.assertIsNone(S.acquire(self.lock))
        S.release(h)

    def test_acquire_again_after_release(self):
        h = S.acquire(self.lock)
        S.release(h)
        h2 = S.acquire(self.lock)
        self.assertIsNotNone(h2)
        S.release(h2)

    def test_release_none_is_safe(self):
        S.release(None)

    def test_release_twice_is_safe(self):
        h = S.acquire(self.lock)
        S.release(h)
        S.release(h)

    def test_watchdog_uses_lock(self):
        src = (Path(S.__file__).parent / "watchdog.py").read_text(encoding="utf-8")
        self.assertIn("single_instance", src)
        self.assertIn("watchdog.lock", src)
        self.assertIn("already", src)


if __name__ == "__main__":
    unittest.main()
