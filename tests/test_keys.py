"""Specification: copy, paste, cut and select-all work in ANY keyboard layout (Ukrainian too),
plus a right-click menu in every text field; window hotkeys also work in the Ukrainian layout.
Специфікація: копіювати, вставити, вирізати й виділити все працюють у БУДЬ-ЯКІЙ розкладці (і українській),
плюс меню правої кнопки в кожному текстовому полі; клавіші вікна теж працюють в українській розкладці.
(Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

Why / чому: Tk binds Ctrl+C to the Latin letter "c". In the Ukrainian layout the same key gives "с" (Cyrillic_es),
so Tk ignores it. The fix uses the physical key (Windows virtual key code), not the letter.

dante/gui_logic.py, add:
  EDIT_KEYS = {67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>", 65: "<<SelectAll>>"}   # C V X A
  WINDOW_KEYS_BY_CODE = {80: "plan", 84: "tests", 77: "models", 71: "github"}          # P T M G
  def edit_event(keycode: int, keysym: str) -> str | None
      None if keysym (lower-case) is one of "c", "v", "x", "a" (Latin layout: Tk already handles it — no double paste);
      otherwise EDIT_KEYS.get(keycode).
  def window_action(keycode: int, keysym: str) -> str | None
      None if keysym (lower-case) is one of "p", "t", "m", "g" (the normal bindings already work);
      otherwise WINDOW_KEYS_BY_CODE.get(keycode).
  def context_menu(lang: str) -> list[tuple[str, str]]
      [(label, virtual event)] in this order: Cut, Copy, Paste, Select all.
      uk: "Вирізати", "Копіювати", "Вставити", "Виділити все"; any other language: "Cut", "Copy", "Paste", "Select all".
dante/gui.py, wire it (checked in review):
  root.bind_class for "Text", "Entry", "TEntry", "TCombobox": "<Control-KeyPress>" -> ev = edit_event(e.keycode, e.keysym);
  if ev: e.widget.event_generate(ev); return "break".  "<Button-3>" -> focus the widget and show a tk.Menu from context_menu(lang).
  root.bind("<Control-KeyPress>") -> window_action(...) -> run plan / tests / models / github like the existing hotkeys.
"""
import unittest

from dante import gui_logic as L


class TestKeys(unittest.TestCase):
    def test_edit_keys_any_layout(self):
        self.assertEqual(L.edit_event(67, "Cyrillic_es"), "<<Copy>>")
        self.assertEqual(L.edit_event(86, "Cyrillic_em"), "<<Paste>>")
        self.assertEqual(L.edit_event(88, "Cyrillic_che"), "<<Cut>>")
        self.assertEqual(L.edit_event(65, "Cyrillic_ef"), "<<SelectAll>>")
        for sym in ("c", "v", "x", "a", "C", "V"):
            self.assertIsNone(L.edit_event(67, sym))   # Latin: Tk does it itself / латиниця: Tk сам
        self.assertIsNone(L.edit_event(81, "Cyrillic_shorti"))

    def test_window_keys_any_layout(self):
        self.assertEqual(L.window_action(80, "Cyrillic_ze"), "plan")
        self.assertEqual(L.window_action(84, "Cyrillic_ie"), "tests")
        self.assertEqual(L.window_action(77, "Cyrillic_softsign"), "models")
        self.assertEqual(L.window_action(71, "Cyrillic_pe"), "github")
        self.assertIsNone(L.window_action(80, "p"))
        self.assertIsNone(L.window_action(67, "Cyrillic_es"))

    def test_menu(self):
        self.assertEqual(L.context_menu("uk"), [("Вирізати", "<<Cut>>"), ("Копіювати", "<<Copy>>"),
                                                ("Вставити", "<<Paste>>"), ("Виділити все", "<<SelectAll>>")])
        self.assertEqual([x[0] for x in L.context_menu("en")], ["Cut", "Copy", "Paste", "Select all"])
        self.assertEqual(L.context_menu("de"), L.context_menu("en"))


if __name__ == "__main__":
    unittest.main()
