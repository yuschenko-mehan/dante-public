"""Spec: vision.look must use DEFAULT_MODEL when model is None or empty (Ollama answers 400 to "model": null).
Специфікація: vision.look має брати DEFAULT_MODEL, коли model = None або порожній (Ollama дає 400 на "model": null)."""
import tempfile
import unittest
from pathlib import Path

from dante import vision


class VisionDefaultModel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.img = Path(self.tmp.name) / "a.png"
        self.img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
        self.seen = {}

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, url, payload, timeout):
        self.seen.update(payload)
        return {"message": {"content": "ok"}}

    def test_none_model_uses_default(self):
        self.assertEqual(vision.look(self.img, "q", model=None, post=self.post), "ok")
        self.assertEqual(self.seen["model"], vision.DEFAULT_MODEL)

    def test_empty_model_uses_default(self):
        vision.look(self.img, "q", model="", post=self.post)
        self.assertEqual(self.seen["model"], vision.DEFAULT_MODEL)

    def test_blank_model_uses_default(self):
        vision.look(self.img, "q", model="   ", post=self.post)
        self.assertEqual(self.seen["model"], vision.DEFAULT_MODEL)

    def test_explicit_model_kept(self):
        vision.look(self.img, "q", model="qwen2.5vl:3b", post=self.post)
        self.assertEqual(self.seen["model"], "qwen2.5vl:3b")

    def test_payload_model_is_always_text(self):
        vision.look(self.img, "q", model=None, post=self.post)
        self.assertIsInstance(self.seen["model"], str)
        self.assertTrue(self.seen["model"])


if __name__ == "__main__":
    unittest.main()
