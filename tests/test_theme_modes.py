"""Spec: Day / Night / As in Windows in the MAIN window. dante/theme.py keeps palette(level) (night, contrast knob)
and gets palette_for(mode, level, read_windows_light) with the SAME keys; day colours come from dante.ui_theme.
Специфікація: День / Ніч / Як у Windows у ГОЛОВНОМУ вікні; ті самі ключі кольорів; денні кольори — з dante.ui_theme."""
import unittest

from dante import theme as TH
from dante import ui_theme as U

KEYS = set(TH.palette(85))


class ThemeModes(unittest.TestCase):
    def test_same_keys_in_every_mode(self):
        for mode in ("day", "night", "system"):
            self.assertEqual(set(TH.palette_for(mode, 85, lambda: True)), KEYS, mode)

    def test_night_is_the_old_palette(self):
        self.assertEqual(TH.palette_for("night", 70, lambda: True), TH.palette(70))

    def test_day_is_light_and_readable(self):
        p = TH.palette_for("day", 85, lambda: False)
        self.assertGreater(U.luminance(p["BG"]), 0.8)
        for fg, bg in (("FG", "BG"), ("FG", "SURFACE"), ("LOG_FG", "LOG_BG"), ("FG2", "SURFACE")):
            self.assertGreaterEqual(U.contrast(p[fg], p[bg]), 4.5, (fg, bg))

    def test_system_follows_windows(self):
        self.assertEqual(TH.palette_for("system", 85, lambda: True), TH.palette_for("day", 85, lambda: True))
        self.assertEqual(TH.palette_for("system", 85, lambda: False), TH.palette(85))

    def test_old_functions_still_there(self):
        for name in ("CAMPBELL", "palette", "step", "value_from_x", "x_from_value", "contrast_ratio"):
            self.assertTrue(hasattr(TH, name), name)


if __name__ == "__main__":
    unittest.main()
