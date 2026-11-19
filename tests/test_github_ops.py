"""GitHub publishing safety (no network) / Безпека викладання на GitHub (без мережі)."""
import subprocess, tempfile, unittest
from pathlib import Path
from unittest import mock

from dante import github_ops as O


def git_ok():
    return O.find_tool("git") is not None


class OpsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.r = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gitignore_added_once(self):
        (self.r / ".gitignore").write_text("build/\nkeys.txt\n", encoding="utf-8")
        added = O.ensure_gitignore(self.r)
        self.assertNotIn("keys.txt", added)
        self.assertIn(".env", added)
        self.assertEqual(O.ensure_gitignore(self.r), [])
        lines = (self.r / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "build/")
        self.assertEqual(lines.count("keys.txt"), 1)

    def fake_status(self, user="author"):
        return mock.patch.object(O, "status", return_value={"git": "git", "gh": "gh", "user": user})

    def test_secret_blocks_publish(self):
        (self.r / "a.py").write_text("K = 'gsk_" + "a" * 30 + "'\n", encoding="utf-8")
        out = []
        with self.fake_status(), mock.patch.object(O, "run") as run:
            self.assertEqual(O.publish(self.r, out=out.append, new_ok=True), 3)
        self.assertFalse(run.called)
        self.assertIn("a.py:1", "\n".join(out))
        self.assertNotIn("aaaa", "\n".join(out))

    def test_not_connected(self):
        with self.fake_status(user=None):
            self.assertEqual(O.publish(self.r, out=lambda s: None), 2)

    def test_new_repo_needs_confirmation(self):
        (self.r / "a.py").write_text("print(1)\n", encoding="utf-8")
        with self.fake_status(), mock.patch.object(O, "run", return_value=(1, "")):
            self.assertEqual(O.publish(self.r, out=lambda s: None), 4)
        self.assertFalse((self.r / "README.md").exists())

    @unittest.skipUnless(git_ok(), "git not installed")
    def test_history_leak_found(self):
        def g(*a):
            subprocess.run(["git", *a], cwd=self.r, capture_output=True)
        g("init", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
        (self.r / "keys.txt").write_text("X=1\n", encoding="utf-8"); g("add", "-A"); g("commit", "-m", "x")
        (self.r / "keys.txt").unlink(); g("add", "-A"); g("commit", "-m", "rm")
        self.assertEqual(O.history_leaks(self.r), ["keys.txt"])

    def test_texts_without_model_are_bilingual(self):
        (self.r / "calc.py").write_text("x", encoding="utf-8")
        d = O.make_texts(self.r, "Додати калькулятор", None, need_readme=True)
        self.assertEqual(d["summary_uk"], "Додати калькулятор")
        self.assertIn("Файли", d["readme_uk"])
        self.assertIn("Files", d["readme_en"])

    def test_model_text_with_secret_is_ignored(self):
        class M:
            def complete(self, *a, **k):
                from dante.llm import LLMResponse
                return LLMResponse('{"summary_en": "key gsk_' + "b" * 30 + '", "summary_uk": "Готово"}', "m")
        d = O.make_texts(self.r, "t", M(), need_readme=False)
        self.assertEqual((d["summary_en"], d["summary_uk"]), ("Project update", "Готово"))


if __name__ == "__main__":
    unittest.main()
