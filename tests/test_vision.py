"""Spec: VISION 2 — DANTE looks at a picture (screenshot, drawing, chart) with a LOCAL model through Ollama, no internet.
Специфікація: ЗІР 2 — Данте дивиться на картинку (знімок екрана, креслення, графік) ЛОКАЛЬНОЮ моделлю через Ollama, без інтернету."""
import base64
import json
import tempfile
import unittest
from pathlib import Path

from dante import vision as V

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class FakePost:
    def __init__(self, answer="A red square."):
        self.calls, self.answer = [], answer

    def __call__(self, url, payload, timeout):
        self.calls.append((url, payload, timeout))
        return {"message": {"role": "assistant", "content": self.answer}}


class VisionTest(unittest.TestCase):
    def img(self, t):
        p = Path(t) / "a.png"; p.write_bytes(PNG); return p

    def test_request_is_ollama_chat_with_image(self):
        with tempfile.TemporaryDirectory() as t:
            post = FakePost()
            ans = V.look(self.img(t), "What is on the picture?", post=post)
            self.assertEqual(ans, "A red square.")
            url, payload, timeout = post.calls[0]
            self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
            self.assertEqual(payload["model"], V.DEFAULT_MODEL)
            self.assertFalse(payload["stream"])
            msg = payload["messages"][-1]
            self.assertEqual(msg["role"], "user")
            self.assertIn("What is on the picture?", msg["content"])
            self.assertEqual(base64.b64decode(msg["images"][0]), PNG)
            self.assertGreaterEqual(timeout, 60)

    def test_model_and_host_can_be_changed(self):
        with tempfile.TemporaryDirectory() as t:
            post = FakePost()
            V.look(self.img(t), "q", model="qwen2.5vl:3b", host="http://10.0.0.5:11434", post=post)
            self.assertEqual(post.calls[0][0], "http://10.0.0.5:11434/api/chat")
            self.assertEqual(post.calls[0][1]["model"], "qwen2.5vl:3b")

    def test_missing_or_not_image_file(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(FileNotFoundError):
                V.look(Path(t) / "none.png", "q", post=FakePost())
            bad = Path(t) / "x.png"; bad.write_text("not an image")
            with self.assertRaises(ValueError):
                V.look(bad, "q", post=FakePost())

    def test_too_big_image_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            big = Path(t) / "b.png"; big.write_bytes(PNG[:8] + b"0" * (V.MAX_BYTES + 1))
            with self.assertRaises(ValueError):
                V.look(big, "q", post=FakePost())

    def test_empty_answer_is_an_error(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(RuntimeError):
                V.look(self.img(t), "q", post=FakePost(""))

    def test_jpeg_is_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            j = Path(t) / "a.jpg"; j.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 20)
            self.assertEqual(V.look(j, "q", post=FakePost("ok")), "ok")

    def test_cli_prints_answer(self):
        with tempfile.TemporaryDirectory() as t:
            out = []
            code = V.main([str(self.img(t)), "--ask", "describe"], post=FakePost("A dot."), say=out.append)
            self.assertEqual(code, 0)
            self.assertIn("A dot.", out[0])


if __name__ == "__main__":
    unittest.main()
