"""Spec: SCREEN READER — VISION 2 for the Writer. DANTE takes a screenshot of the whole screen or of any program window
(not only Chrome), asks the local vision model and gets back: exact CODE as files, plain TEXT, or a PHYSICAL description
of real objects (what they are, materials, sizes, forces, how they move, what is unsafe).
Специфікація: ЧИТАЧ ЕКРАНА — Зір 2 для Писаря. Знімок усього екрана чи будь-якого вікна, локальна модель повертає:
точний КОД як файли, ТЕКСТ, або ФІЗИЧНИЙ опис реальних об'єктів (що це, матеріали, розміри, сили, рух, небезпеки)."""
import tempfile
import unittest
from pathlib import Path

from dante import screen_read as S


class FakeLook:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, image, question, model=None):
        self.calls.append((Path(image), question, model))
        return self.answer


def fake_capture(out_path, window=None):
    Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 10)
    return Path(out_path)


CODE_ANSWER = "calc.py\n\npython\ndef add(a, b):\n    return a + b\n"


class PromptTest(unittest.TestCase):
    def test_three_modes_with_clear_prompts(self):
        self.assertEqual(S.MODES, ("code", "text", "physics"))
        p = S.prompt("code")
        self.assertIn("exactly", p.lower()); self.assertIn("indentation", p.lower()); self.assertIn("file name", p.lower())
        self.assertIn("transcribe", S.prompt("text").lower())
        ph = S.prompt("physics").lower()
        for w in ("material", "size", "force", "motion", "safety"):
            self.assertIn(w, ph)
        with self.assertRaises(ValueError):
            S.prompt("magic")

    def test_extra_question_is_added(self):
        self.assertIn("What is the gear ratio?", S.prompt("physics", "What is the gear ratio?"))


class ReadTest(unittest.TestCase):
    def test_code_mode_returns_files(self):
        with tempfile.TemporaryDirectory() as t:
            look = FakeLook(CODE_ANSWER)
            r = S.read_screen("code", Path(t), capture=fake_capture, look=look, now="20261123-1100")
            self.assertEqual(r.mode, "code")
            self.assertEqual(r.files, {"calc.py": "def add(a, b):\n    return a + b"})
            self.assertTrue(r.image.exists())
            self.assertEqual(r.image.name, "screen-20261123-1100.png")
            self.assertIn("indentation", look.calls[0][1].lower())

    def test_text_and_physics_modes_return_text_only(self):
        with tempfile.TemporaryDirectory() as t:
            r = S.read_screen("physics", Path(t), capture=fake_capture, look=FakeLook("A steel gear, 40 mm."), now="x")
            self.assertEqual(r.text, "A steel gear, 40 mm.")
            self.assertEqual(r.files, {})

    def test_window_title_is_passed_to_capture(self):
        seen = {}
        def cap(out_path, window=None):
            seen["w"] = window
            return fake_capture(out_path)
        with tempfile.TemporaryDirectory() as t:
            S.read_screen("text", Path(t), window="Notepad", capture=cap, look=FakeLook("hi"), now="x")
        self.assertEqual(seen["w"], "Notepad")

    def test_existing_image_skips_capture(self):
        with tempfile.TemporaryDirectory() as t:
            img = fake_capture(Path(t) / "photo.png")
            def cap(*a, **k):
                raise AssertionError("must not capture")
            r = S.read_screen("physics", Path(t), image=img, capture=cap, look=FakeLook("ok"), now="x")
            self.assertEqual(r.image, img)

    def test_code_mode_without_files_keeps_text(self):
        with tempfile.TemporaryDirectory() as t:
            r = S.read_screen("code", Path(t), capture=fake_capture, look=FakeLook("No code on the screen."), now="x")
            self.assertEqual(r.files, {})
            self.assertIn("No code", r.text)

    def test_save_files_never_outside_folder(self):
        with tempfile.TemporaryDirectory() as t:
            out = S.save_files(Path(t), {"a/b.py": "x = 1", "../evil.py": "bad"})
            self.assertEqual(out, ["a/b.py"])
            self.assertTrue((Path(t) / "a" / "b.py").exists())
            self.assertFalse((Path(t).parent / "evil.py").exists())


class CaptureCommandTest(unittest.TestCase):
    def test_powershell_capture_command(self):
        cmd = S.capture_command(r"C:\x\s.png")
        self.assertEqual(cmd[0].lower(), "powershell")
        joined = " ".join(cmd)
        self.assertIn("System.Drawing", joined)
        self.assertIn(r"C:\x\s.png", joined)
        self.assertIn("CopyFromScreen", joined)

    def test_window_capture_uses_the_title(self):
        joined = " ".join(S.capture_command(r"C:\x\s.png", window="Блокнот"))
        self.assertIn("Блокнот", joined)
        self.assertIn("GetWindowRect", joined)


if __name__ == "__main__":
    unittest.main()
