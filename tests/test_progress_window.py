"""Spec: the progress window module exists, refreshes often, starts small and never steals focus.
Специфікація: модуль вікна прогресу є, часто оновлюється, стартує маленьким і не забирає фокус."""
import inspect
import unittest

from dante import progress_window as W


class WindowSpec(unittest.TestCase):
    def test_constants(self):
        self.assertLessEqual(W.REFRESH_MS, 3000)
        self.assertLessEqual(W.BAR_HEIGHT, 40)
        self.assertTrue(str(W.LOG_PATH).lower().endswith("pult.log"))

    def test_has_main_and_toggle(self):
        self.assertTrue(callable(W.main))
        src = inspect.getsource(W)
        self.assertIn("-topmost", src)
        self.assertIn("toggle", src)
        self.assertNotIn("focus_force", src)
        self.assertIn("progress.status_from_log", src)
        self.assertIn("bar_text", src)


if __name__ == "__main__":
    unittest.main()
