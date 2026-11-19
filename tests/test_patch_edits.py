"""Specification: DANTE edits big files with small patches instead of rewriting them.
Специфікація: Данте править великі файли малими латками, а не переписує їх цілком.
(Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/edits.py — an answer may mix two kinds of blocks, in any order:
    === FILE: path ===             (new or small files: the COMPLETE content)
    <content>
    === END FILE ===

    === PATCH: path ===            (existing files: only what changes)
    <<<<<<< SEARCH
    <existing lines, copied exactly>
    =======
    <new lines>
    >>>>>>> REPLACE
    ... more SEARCH/REPLACE hunks ...
    === END PATCH ===

  FileEdit(path, content) stays as it is.
  parse_hunks(body: str) -> list[tuple[str, str]]
      SEARCH text = the lines between "<<<<<<< SEARCH" and "=======" (each line with its "\\n");
      REPLACE text = the lines between "=======" and ">>>>>>> REPLACE" (may be empty = delete).
      No hunk in the body -> ValueError.
  apply_hunks(text: str, hunks: list[tuple[str, str]], path: str = "") -> str
      Hunks are applied in order to the current text. Empty SEARCH -> ValueError.
      1) SEARCH occurs exactly once as a substring -> replace it.
      2) otherwise compare line by line ignoring trailing spaces/tabs: exactly one matching run of lines -> those
         lines are replaced by the REPLACE lines.
      0 matches -> ValueError whose message contains "not found" and the path;
      more than 1 -> ValueError whose message contains "times" and the path.
  parse_edits(answer: str, read=None) -> list[FileEdit]
      read(path) -> str | None gives the current file text (None = no such file).
      "\\r\\n" -> "\\n" first. Blocks are processed in the order they appear; a later block for the same path works on
      the result of the earlier one. Result: one FileEdit per path, in order of first appearance, with full content.
      A PATCH whose file does not exist (read is None or returns None) -> ValueError mentioning the path.
      No FILE and no PATCH block -> ValueError("The model answer contains no file blocks.").
  FORMAT_INSTRUCTIONS describes both block kinds and contains "=== PATCH:", "<<<<<<< SEARCH" and ">>>>>>> REPLACE".
dante/loop.py: call parse_edits(resp.content, read=...) where read returns the text of ws.resolve(path) if it exists,
  else None (an unsafe path raises, which the loop already reports as a rejected answer).
"""
import unittest

from dante import edits as E

BIG = "".join(f"line {i}\n" for i in range(1, 2001))


def patch(path, *hunks):
    body = "".join(f"<<<<<<< SEARCH\n{s}=======\n{r}>>>>>>> REPLACE\n" for s, r in hunks)
    return f"=== PATCH: {path} ===\n{body}=== END PATCH ===\n"


class TestHunks(unittest.TestCase):
    def test_parse_hunks(self):
        body = "<<<<<<< SEARCH\na\nb\n=======\nc\n>>>>>>> REPLACE\n<<<<<<< SEARCH\nx\n=======\n>>>>>>> REPLACE\n"
        self.assertEqual(E.parse_hunks(body), [("a\nb\n", "c\n"), ("x\n", "")])
        with self.assertRaises(ValueError):
            E.parse_hunks("just text\n")

    def test_exact_and_order(self):
        self.assertEqual(E.apply_hunks("a\nb\nc\n", [("b\n", "B\n"), ("B\nc\n", "BC\n")]), "a\nBC\n")
        self.assertEqual(E.apply_hunks("a\nb\nc\n", [("b\n", "")]), "a\nc\n")

    def test_trailing_spaces_are_forgiven(self):
        self.assertEqual(E.apply_hunks("def f():   \n    return 1\t\nx\n", [("def f():\n    return 1\n", "def f():\n    return 2\n")]),
                         "def f():\n    return 2\nx\n")

    def test_errors(self):
        with self.assertRaises(ValueError) as c:
            E.apply_hunks("a\nb\n", [("zzz\n", "y\n")], "src/x.rs")
        self.assertIn("not found", str(c.exception)); self.assertIn("src/x.rs", str(c.exception))
        with self.assertRaises(ValueError) as c:
            E.apply_hunks("a\nb\na\n", [("a\n", "y\n")], "p.py")
        self.assertIn("times", str(c.exception)); self.assertIn("p.py", str(c.exception))
        with self.assertRaises(ValueError):
            E.apply_hunks("a\n", [("", "y\n")])


class TestParseEdits(unittest.TestCase):
    def files(self):
        store = {"big.py": BIG, "small.txt": "old\n"}
        return lambda p: store.get(p)

    def test_patch_big_file(self):
        ans = patch("big.py", ("line 1000\n", "LINE ONE THOUSAND\n"), ("line 2000\n", "line 2000\nline 2001\n"))
        [e] = E.parse_edits(ans, read=self.files())
        self.assertEqual(e.path, "big.py")
        self.assertIn("LINE ONE THOUSAND\nline 1001\n", e.content)
        self.assertTrue(e.content.endswith("line 2000\nline 2001\n"))
        self.assertEqual(e.content.count("\n"), 2001)

    def test_mixed_blocks_crlf_and_order(self):
        ans = ("note\r\n=== FILE: new.py ===\r\nprint(1)\r\n=== END FILE ===\r\n"
               + patch("small.txt", ("old\n", "mid\n")) + patch("small.txt", ("mid\n", "new\n")))
        out = E.parse_edits(ans, read=self.files())
        self.assertEqual([(e.path, e.content) for e in out], [("new.py", "print(1)\n"), ("small.txt", "new\n")])

    def test_old_format_still_works(self):
        self.assertEqual(E.parse_edits("=== FILE: a.py ===\nx = 1\n=== END FILE ==="), [E.FileEdit("a.py", "x = 1\n")])

    def test_patch_needs_existing_file(self):
        with self.assertRaises(ValueError) as c:
            E.parse_edits(patch("ghost.py", ("a\n", "b\n")), read=self.files())
        self.assertIn("ghost.py", str(c.exception))
        with self.assertRaises(ValueError):
            E.parse_edits(patch("big.py", ("line 1\n", "x\n")))  # no read given

    def test_no_blocks(self):
        with self.assertRaises(ValueError) as c:
            E.parse_edits("I think you should...")
        self.assertEqual(str(c.exception), "The model answer contains no file blocks.")

    def test_instructions(self):
        for s in ("=== PATCH:", "<<<<<<< SEARCH", ">>>>>>> REPLACE", "=== FILE:"):
            self.assertIn(s, E.FORMAT_INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
