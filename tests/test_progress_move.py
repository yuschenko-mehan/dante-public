"""Spec (Claude, 24.11.2026, author's wish): the progress bar can be dragged anywhere and stays on screen;
the place is remembered; details scroll. / Смужку прогресу можна перетягнути куди завгодно, місце запам'ятовується."""
import tempfile
import unittest
from pathlib import Path

from dante import progress_window as W


class Move(unittest.TestCase):
    def test_clamp_inside_screen(self):
        self.assertEqual(W.clamp_pos(100, 200, 460, 30, 1920, 1080), (100, 200))
        self.assertEqual(W.clamp_pos(-50, -9, 460, 30, 1920, 1080), (0, 0))
        self.assertEqual(W.clamp_pos(1800, 1070, 460, 30, 1920, 1080), (1460, 1050))

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "pos.json"
            self.assertIsNone(W.load_pos(f))
            W.save_pos(10, 20, f)
            self.assertEqual(W.load_pos(f), (10, 20))
            f.write_text("broken", encoding="utf-8")
            self.assertIsNone(W.load_pos(f))

    def test_window_has_drag_and_scroll(self):
        src = Path(W.__file__).read_text(encoding="utf-8")
        for k in ("<B1-Motion>", "<ButtonRelease-1>", "<MouseWheel>", "tk.Text(", "DETAIL_LINES", "progress-pos.json"):
            self.assertIn(k, src)


if __name__ == "__main__":
    unittest.main()
