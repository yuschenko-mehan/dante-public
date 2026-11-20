"""Spec: Day / Night / As in Windows themes in the Material Design 3 spirit, plain engineering look,
accessible contrast (WCAG 2.2 AA), big targets, saved choice.
Специфікація: теми День / Ніч / Як у Windows у дусі Material Design 3, стриманий інженерний вигляд,
доступний контраст (WCAG 2.2 AA), великі кнопки, збереження вибору."""
import tempfile
import unittest
from pathlib import Path

from dante import ui_theme as T

ROLES = ("bg", "surface", "surface_alt", "on_bg", "on_surface", "muted", "primary", "on_primary",
         "outline", "focus", "error", "on_error", "success", "warning", "danger_btn", "on_danger_btn")


class PaletteTest(unittest.TestCase):
    def test_both_palettes_have_every_role_as_hex(self):
        for name in ("day", "night"):
            p = T.palette(name)
            for r in ROLES:
                self.assertRegex(p[r], r"^#[0-9a-f]{6}$", (name, r))

    def test_text_contrast_meets_wcag_aa(self):
        for name in ("day", "night"):
            p = T.palette(name)
            for fg, bg in (("on_bg", "bg"), ("on_surface", "surface"), ("muted", "surface"), ("on_primary", "primary"),
                           ("on_error", "error"), ("on_danger_btn", "danger_btn"), ("on_surface", "surface_alt")):
                self.assertGreaterEqual(T.contrast(p[fg], p[bg]), 4.5, (name, fg, bg))

    def test_focus_and_outline_are_visible(self):
        for name in ("day", "night"):
            p = T.palette(name)
            self.assertGreaterEqual(T.contrast(p["focus"], p["surface"]), 3.0, name)
            self.assertGreaterEqual(T.contrast(p["outline"], p["surface"]), 3.0, name)

    def test_day_is_light_and_night_is_dark(self):
        self.assertGreater(T.luminance(T.palette("day")["bg"]), 0.8)
        self.assertLess(T.luminance(T.palette("night")["bg"]), 0.05)

    def test_contrast_math(self):
        self.assertAlmostEqual(T.contrast("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(T.contrast("#777777", "#777777"), 1.0, places=3)

    def test_unknown_palette_is_an_error(self):
        with self.assertRaises(KeyError):
            T.palette("sepia")


class ModeTest(unittest.TestCase):
    def test_modes_and_labels_in_two_languages(self):
        self.assertEqual(T.MODES, ("day", "night", "system"))
        self.assertEqual(T.mode_label("day", "uk"), "День")
        self.assertEqual(T.mode_label("night", "uk"), "Ніч")
        self.assertEqual(T.mode_label("system", "uk"), "Як у Windows")
        self.assertEqual(T.mode_label("system", "en"), "As in Windows")

    def test_system_mode_follows_windows(self):
        self.assertEqual(T.resolve("system", read_windows_light=lambda: True), "day")
        self.assertEqual(T.resolve("system", read_windows_light=lambda: False), "night")

    def test_system_mode_when_windows_cannot_be_read_is_night(self):
        def broken():
            raise OSError("no registry")
        self.assertEqual(T.resolve("system", read_windows_light=broken), "night")

    def test_explicit_modes_ignore_windows(self):
        self.assertEqual(T.resolve("day", read_windows_light=lambda: False), "day")
        self.assertEqual(T.resolve("night", read_windows_light=lambda: True), "night")

    def test_bad_mode_falls_back_to_system(self):
        self.assertEqual(T.resolve("purple", read_windows_light=lambda: True), "day")


class PrefsTest(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "ui.json"
            self.assertEqual(T.load_mode(p), "system")
            T.save_mode(p, "day")
            self.assertEqual(T.load_mode(p), "day")
            p.write_text("{broken", encoding="utf-8")
            self.assertEqual(T.load_mode(p), "system")

    def test_save_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                T.save_mode(Path(t) / "ui.json", "pink")

    def test_save_keeps_other_settings(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "ui.json"
            p.write_text('{"lang": "uk"}', encoding="utf-8")
            T.save_mode(p, "night")
            self.assertIn('"lang"', p.read_text(encoding="utf-8"))


class MetricsTest(unittest.TestCase):
    def test_spacing_grid_is_multiple_of_4_and_targets_are_big(self):
        m = T.METRICS
        for k in ("space_xs", "space_s", "space_m", "space_l", "space_xl"):
            self.assertEqual(m[k] % 4, 0, k)
        self.assertGreaterEqual(m["button_height"], 40)
        self.assertGreaterEqual(m["min_target"], 24)
        self.assertGreaterEqual(m["corner"], 4)
        self.assertLessEqual(m["corner"], 16)

    def test_type_scale_is_readable(self):
        t = T.TYPE_SCALE
        self.assertGreaterEqual(t["body"], 11)
        self.assertGreater(t["title"], t["body"])
        self.assertGreater(t["headline"], t["title"])
        self.assertGreaterEqual(t["label"], 10)


if __name__ == "__main__":
    unittest.main()
