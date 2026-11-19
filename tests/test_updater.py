"""Specification: DANTE updates itself from its own GitHub releases — safely.
Специфікація: Данте сам оновлюється зі своїх релізів на GitHub — безпечно.
(Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/updater.py (stdlib only):
  REPO = "yuschenko-mehan/dante-public"
  API_URL = "https://api.github.com/repos/yuschenko-mehan/dante-public/releases/latest"
  TRUSTED = "https://github.com/yuschenko-mehan/dante-public/releases/download/"
  KEEP = {"keys.txt", "dante.toml", "models.json", "lessons.json", "idle.json", "contest.json", "settings.json", "github.json"}
      files of the author that an update never overwrites (matched by file name, anywhere in the tree)

  parse_version(s: str) -> tuple[int, ...]
      "2026.11.19.5" or "v2026.11.19.5" -> (2026, 11, 19, 5); anything that is not dot-separated integers -> ()
  is_newer(remote: str, local: str) -> bool          # parse_version(remote) > parse_version(local); () is never newer
  pick_release(rel: dict) -> dict | None
      rel = GitHub "latest release" JSON. version = tag_name without a leading "v".
      Needs assets named "dante-<version>.zip" and "dante-<version>.zip.sha256"; both browser_download_url
      must start with TRUSTED. Returns {"version", "zip_url", "sha_url", "notes"} (notes = rel["body"] or ""),
      otherwise None (missing asset, foreign URL, bad tag, draft or prerelease -> None).
  check(local_version: str, fetch_json) -> dict | None
      fetch_json(API_URL) -> dict; the picked release if it is newer than local_version; any exception -> None.
  verify(data: bytes, sha_text: str) -> bool        # first word of sha_text (case-insensitive) == sha256(data) hex
  install(zip_bytes: bytes, app_dir: Path, backup_dir: Path) -> list[str]
      Checks every member first: an absolute path, a drive letter, or ".." anywhere -> raise ValueError, write nothing.
      Then for every file member (directories skipped): if its file name is in KEEP and it already exists -> skip;
      if a file with that path exists, copy it first to backup_dir/<same relative path>; write the new file.
      Returns the written relative paths with "/" separators, sorted.
  rollback(app_dir: Path, backup_dir: Path) -> int   # copies every backed-up file back, returns how many
  due(last_check: str | None, now: datetime) -> bool
      True if last_check is None, unparsable, or at least 20 hours before now (ISO format, datetime.isoformat()).
"""
import hashlib
import io
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from dante import updater as U

T = U.TRUSTED + "v2026.12.1.1/"


def rel(tag="v2026.12.1.1", zip_url=None, sha_url=None, **kw):
    ver = tag.lstrip("v")
    r = {"tag_name": tag, "body": "notes", "draft": False, "prerelease": False,
         "assets": [{"name": f"dante-{ver}.zip", "browser_download_url": zip_url or T + f"dante-{ver}.zip"},
                    {"name": f"dante-{ver}.zip.sha256", "browser_download_url": sha_url or T + f"dante-{ver}.zip.sha256"}]}
    r.update(kw)
    return r


def make_zip(files: dict) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return b.getvalue()


class TestVersions(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(U.parse_version("2026.11.19.5"), (2026, 11, 19, 5))
        self.assertEqual(U.parse_version("v2026.11.19.5"), (2026, 11, 19, 5))
        self.assertEqual(U.parse_version("beta"), ())
        self.assertEqual(U.parse_version(""), ())
        self.assertTrue(U.is_newer("2026.11.20.1", "2026.11.19.5"))
        self.assertTrue(U.is_newer("2026.11.19.10", "2026.11.19.5"))
        self.assertFalse(U.is_newer("2026.11.19.5", "2026.11.19.5"))
        self.assertFalse(U.is_newer("junk", "2026.11.19.5"))


class TestRelease(unittest.TestCase):
    def test_pick_good(self):
        p = U.pick_release(rel())
        self.assertEqual(p, {"version": "2026.12.1.1", "zip_url": T + "dante-2026.12.1.1.zip",
                             "sha_url": T + "dante-2026.12.1.1.zip.sha256", "notes": "notes"})

    def test_pick_rejects(self):
        self.assertIsNone(U.pick_release(rel(zip_url="https://evil.example/dante-2026.12.1.1.zip")))
        self.assertIsNone(U.pick_release(rel(sha_url="https://github.com/someone-else/x/releases/download/a/b")))
        self.assertIsNone(U.pick_release(rel(draft=True)))
        self.assertIsNone(U.pick_release(rel(prerelease=True)))
        self.assertIsNone(U.pick_release(rel(tag="nightly")))
        r = rel(); r["assets"] = r["assets"][:1]
        self.assertIsNone(U.pick_release(r))
        self.assertIsNone(U.pick_release({}))

    def test_check(self):
        self.assertEqual(U.check("2026.11.19.5", lambda url: rel())["version"], "2026.12.1.1")
        self.assertIsNone(U.check("2026.12.1.1", lambda url: rel()))
        def boom(url):
            raise OSError("offline")
        self.assertIsNone(U.check("1.0", boom))
        seen = []
        U.check("1.0", lambda url: seen.append(url) or rel())
        self.assertEqual(seen, [U.API_URL])

    def test_verify(self):
        data = b"zip bytes"
        h = hashlib.sha256(data).hexdigest()
        self.assertTrue(U.verify(data, f"{h.upper()}  dante-2026.12.1.1.zip\n"))
        self.assertFalse(U.verify(data + b"x", h))
        self.assertFalse(U.verify(data, ""))


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name) / "app"
        self.bak = Path(self.tmp.name) / "backup"
        (self.app / "dante").mkdir(parents=True)
        (self.app / "dante" / "gui.py").write_text("old gui", encoding="utf-8")
        (self.app / "keys.txt").write_text("SECRET", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_keeps_author_files_and_backs_up(self):
        z = make_zip({"dante/gui.py": "new gui", "dante/new.py": "x", "keys.txt": "EMPTY", "docs/": ""})
        written = U.install(z, self.app, self.bak)
        self.assertEqual(written, ["dante/gui.py", "dante/new.py"])
        self.assertEqual((self.app / "dante" / "gui.py").read_text(encoding="utf-8"), "new gui")
        self.assertEqual((self.app / "keys.txt").read_text(encoding="utf-8"), "SECRET")
        self.assertEqual((self.bak / "dante" / "gui.py").read_text(encoding="utf-8"), "old gui")
        self.assertEqual(U.rollback(self.app, self.bak), 1)
        self.assertEqual((self.app / "dante" / "gui.py").read_text(encoding="utf-8"), "old gui")

    def test_keep_file_is_written_when_missing(self):
        (self.app / "keys.txt").unlink()
        self.assertEqual(U.install(make_zip({"keys.txt": "template"}), self.app, self.bak), ["keys.txt"])

    def test_dangerous_zip_writes_nothing(self):
        for bad in ["../evil.py", "dante/../../evil.py", "/abs.py", "C:/win.py", "C:\\win.py"]:
            z = make_zip({"dante/ok.py": "fine", bad: "boom"})
            with self.assertRaises(ValueError):
                U.install(z, self.app, self.bak)
            self.assertFalse((self.app / "dante" / "ok.py").exists(), bad)


class TestDue(unittest.TestCase):
    def test_due(self):
        now = datetime(2026, 11, 20, 8, 0)
        self.assertTrue(U.due(None, now))
        self.assertTrue(U.due("garbage", now))
        self.assertTrue(U.due((now - timedelta(hours=20)).isoformat(), now))
        self.assertFalse(U.due((now - timedelta(hours=19)).isoformat(), now))


if __name__ == "__main__":
    unittest.main()
