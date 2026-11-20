"""Specification: the COLLECTOR — DANTE's main idea. It takes a conversation with any AI (text, Markdown, or what the
Reader took from a chat window), pulls out the code, lays it into a project and lets DANTE fix it until it works.
Специфікація: ЗБИРАЧ — головна ідея Данте. Бере розмову з будь-яким ШІ (текст, Markdown або те, що Читач забрав
з вікна чату), виймає код, розкладає у проєкт, а Данте доводить його до робочого стану.
(Claude, 20.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/codeblocks.py — move C:\\DANTE\\proby\\reader\\codeblocks.py into the dante package unchanged
  (Block, LANG_EXT, name_from_context, extract_blocks, collect).
dante/collector.py (stdlib only):
  def from_text(text: str) -> dict[str, str]      # codeblocks.collect(codeblocks.extract_blocks(text))
  def safe_rel(path: str) -> str | None
      backslashes -> "/", strip a leading "./"; None if empty, absolute ("/..."), with a drive letter ("C:..."),
      or with a ".." part.
  def write_files(files: dict[str, str], root: Path) -> list[str]
      writes every file with a safe path under root (creates folders; content ends with exactly one "\\n");
      unsafe paths are skipped; returns the written safe paths, sorted.
  def default_check(root: Path) -> str | None
      root/"Cargo.toml" exists -> "cargo build --quiet"; any *.py file under root -> f'"{sys.executable}" -m compileall -q .';
      otherwise None.
  def assemble(text: str, root: Path, run_fix=None, check: str | None = None) -> dict
      files = write_files(from_text(text), root); cmd = check or default_check(root);
      {"files": files, "check": cmd, "ok": run_fix(cmd) if (cmd and run_fix and files) else None}
dante/cli.py: new command
  python -m dante collect --from FILE --project DIR [--test CMD] [--no-fix]
      reads FILE (UTF-8); creates DIR; assemble(...). Without --no-fix, run_fix(cmd) runs the same machinery as
      `dante run` in DIR with the task "Make the project assembled from an AI conversation pass: <cmd>. Change only
      what is needed." and returns True on success. Prints every written file and the result; returns 0 when
      ok is True or None, 1 when ok is False; FILE missing -> 2.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dante import cli, collector as C

CHAT = '''User: write me a calculator

Assistant: Here is the project.

**calc/ops.py**
```python
def add(a, b):
    return a + b
```

And the entry point:

```python
# file: main.py
from calc.ops import add
print(add(2, 3))
```

Oops, a better version of ops:

`calc/ops.py`
```python
def add(a, b):
    """Sum."""
    return a + b
```

Evil one:

**../../evil.py**
```python
import os
```
'''


class TestCollector(unittest.TestCase):
    def test_from_text_latest_version_wins(self):
        files = C.from_text(CHAT)
        self.assertIn('"""Sum."""', files["calc/ops.py"])
        self.assertEqual(files["main.py"].splitlines()[0], "from calc.ops import add")

    def test_safe_rel(self):
        self.assertEqual(C.safe_rel("calc\\ops.py"), "calc/ops.py")
        self.assertEqual(C.safe_rel("./a.py"), "a.py")
        for bad in ("", "/etc/x", "C:/win.py", "c:\\x.py", "../e.py", "a/../../e.py"):
            self.assertIsNone(C.safe_rel(bad), bad)

    def test_write_and_check(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "proj"
            written = C.write_files(C.from_text(CHAT), root)
            self.assertEqual(written, ["calc/ops.py", "main.py"])
            self.assertFalse((Path(t) / "evil.py").exists())
            self.assertTrue((root / "main.py").read_text(encoding="utf-8").endswith(")\n"))
            self.assertEqual(C.default_check(root), f'"{sys.executable}" -m compileall -q .')
            (root / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
            self.assertEqual(C.default_check(root), "cargo build --quiet")
            self.assertIsNone(C.default_check(Path(t) / "empty"))

    def test_assemble(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "proj"
            calls = []
            out = C.assemble(CHAT, root, run_fix=lambda cmd: calls.append(cmd) or True)
            self.assertEqual(out["files"], ["calc/ops.py", "main.py"])
            self.assertTrue(out["ok"])
            self.assertEqual(calls, [out["check"]])
            out = C.assemble("no code here", Path(t) / "p2", run_fix=lambda cmd: False)
            self.assertEqual(out, {"files": [], "check": None, "ok": None})

    def test_cli_collect_no_fix(self):
        with tempfile.TemporaryDirectory() as t:
            chat = Path(t) / "chat.md"
            chat.write_text(CHAT, encoding="utf-8")
            proj = Path(t) / "out"
            self.assertEqual(cli.main(["collect", "--from", str(chat), "--project", str(proj), "--no-fix"]), 0)
            self.assertTrue((proj / "calc" / "ops.py").exists())
            self.assertEqual(cli.main(["collect", "--from", str(Path(t) / "missing.md"), "--project", str(proj), "--no-fix"]), 2)


if __name__ == "__main__":
    unittest.main()
