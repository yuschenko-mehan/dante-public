"""Specification: the update command and policy (step 2).
Специфікація: команда оновлення і налаштування (крок 2).
(Claude, 19.11.2026. Do not edit — DANTE makes it pass. / Не змінювати — Данте має пройти.)

dante/updater.py, add (stdlib only):
  "update.json" is also in KEEP.
  fetch_json(url, timeout=20) -> dict        # urllib GET, header User-Agent "DANTE-updater", JSON body (network; not tested here)
  fetch_bytes(url, timeout=120) -> bytes     # urllib GET with the same header (network; not tested here)
  DEFAULT_POLICY = {"auto_check": True, "auto_install": False, "last_check": None}
  load_policy(path: Path) -> dict      # DEFAULT_POLICY merged with the JSON file; missing or broken file -> defaults
  save_policy(path: Path, policy: dict) -> None
  run_update(app_dir: Path, local_version: str, *, install_now: bool, fetch_json=None, fetch_bytes=None, now=None) -> str
      fetch_json/fetch_bytes default to the module functions (looked up at call time), now defaults to datetime.now().
      Policy file = app_dir / "update.json"; its last_check is set to now.isoformat() and saved every time.
      rel = check(local_version, fetch_json). None -> "up-to-date".
      Not install_now -> f"available {version}".
      Download zip and sha (sha bytes decoded as UTF-8); not verify(...) -> "bad-checksum" (nothing written).
      Else install(zip, app_dir, app_dir / "update-backup" / local_version) -> f"installed {version}".
      Any exception while downloading -> "offline".
dante/cli.py: new subcommand
  python -m dante update [check|install|rollback|auto-on|auto-off] [--app-dir DIR]
      default action "check"; --app-dir defaults to the folder that contains the dante package.
      check / install: print the run_update result line (plus a short Ukrainian explanation); return 0.
      rollback: the newest folder in <app>/update-backup (by name) is copied back with updater.rollback; prints how many files; 0.
                No backup -> prints a message, returns 1.
      auto-on / auto-off: sets "auto_install" in update.json; return 0.
      local version = dante.__build__.
"""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

import dante
from dante import cli
from dante import updater as U

VER = "2099.1.1.1"
BASE = U.TRUSTED + f"v{VER}/"
ZIP = io.BytesIO()
with zipfile.ZipFile(ZIP, "w") as z:
    z.writestr("dante/hello.py", "print('new')")
ZIP = ZIP.getvalue()
SHA = (hashlib.sha256(ZIP).hexdigest() + f"  dante-{VER}.zip\n").encode()
REL = {"tag_name": "v" + VER, "body": "", "assets": [
    {"name": f"dante-{VER}.zip", "browser_download_url": BASE + f"dante-{VER}.zip"},
    {"name": f"dante-{VER}.zip.sha256", "browser_download_url": BASE + f"dante-{VER}.zip.sha256"}]}


def fj(url):
    return REL


def fb(url):
    return SHA if url.endswith(".sha256") else ZIP


class TestRunUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name)
        (self.app / "dante").mkdir()
        (self.app / "dante" / "hello.py").write_text("print('old')", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_policy_defaults_and_file(self):
        p = self.app / "update.json"
        self.assertEqual(U.load_policy(p), U.DEFAULT_POLICY)
        p.write_text("{broken", encoding="utf-8")
        self.assertEqual(U.load_policy(p), U.DEFAULT_POLICY)
        U.save_policy(p, {"auto_check": True, "auto_install": True, "last_check": None})
        self.assertTrue(U.load_policy(p)["auto_install"])
        self.assertIn("update.json", U.KEEP)

    def test_check_install_and_flow(self):
        now = datetime(2026, 11, 20, 7, 30)
        self.assertEqual(U.run_update(self.app, "1.0", install_now=False, fetch_json=fj, fetch_bytes=fb, now=now), f"available {VER}")
        self.assertEqual(U.load_policy(self.app / "update.json")["last_check"], now.isoformat())
        self.assertEqual((self.app / "dante" / "hello.py").read_text(encoding="utf-8"), "print('old')")
        self.assertEqual(U.run_update(self.app, "1.0", install_now=True, fetch_json=fj, fetch_bytes=fb, now=now), f"installed {VER}")
        self.assertEqual((self.app / "dante" / "hello.py").read_text(encoding="utf-8"), "print('new')")
        self.assertTrue((self.app / "update-backup" / "1.0" / "dante" / "hello.py").exists())
        self.assertEqual(U.run_update(self.app, VER, install_now=True, fetch_json=fj, fetch_bytes=fb, now=now), "up-to-date")

    def test_bad_checksum_and_offline(self):
        bad = lambda url: b"0000" if url.endswith(".sha256") else ZIP
        self.assertEqual(U.run_update(self.app, "1.0", install_now=True, fetch_json=fj, fetch_bytes=bad), "bad-checksum")
        self.assertEqual((self.app / "dante" / "hello.py").read_text(encoding="utf-8"), "print('old')")
        def down(url):
            raise OSError("no internet")
        self.assertEqual(U.run_update(self.app, "1.0", install_now=True, fetch_json=fj, fetch_bytes=down), "offline")


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name)
        (self.app / "dante").mkdir()
        (self.app / "dante" / "hello.py").write_text("print('old')", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out = io.StringIO()
        with mock.patch.object(U, "fetch_json", fj), mock.patch.object(U, "fetch_bytes", fb), mock.patch.object(dante, "__build__", "1.0"), redirect_stdout(out):
            code = cli.main(["update", *args, "--app-dir", str(self.app)])
        return code, out.getvalue()

    def test_cli_flow(self):
        code, out = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn(f"available {VER}", out)
        code, out = self.run_cli("install")
        self.assertEqual(code, 0)
        self.assertIn(f"installed {VER}", out)
        self.assertEqual((self.app / "dante" / "hello.py").read_text(encoding="utf-8"), "print('new')")
        code, out = self.run_cli("rollback")
        self.assertEqual(code, 0)
        self.assertEqual((self.app / "dante" / "hello.py").read_text(encoding="utf-8"), "print('old')")
        self.assertEqual(self.run_cli("auto-on")[0], 0)
        self.assertTrue(json.loads((self.app / "update.json").read_text(encoding="utf-8"))["auto_install"])
        self.assertEqual(self.run_cli("auto-off")[0], 0)
        self.assertFalse(json.loads((self.app / "update.json").read_text(encoding="utf-8"))["auto_install"])

    def test_rollback_without_backup(self):
        self.assertEqual(self.run_cli("rollback")[0], 1)


if __name__ == "__main__":
    unittest.main()
