"""Specification for dante/models_hub.py — the list of user-added AI models.

models.json holds {"models": [entry, ...]}. An entry:
  name      str  ^[a-z0-9][a-z0-9-]{1,30}$   unique, not one of the built-ins
            (BUILTIN_NAMES = frozenset of dante.config.DEFAULT_PROVIDERS names)
  base_url  str  https://...  or  http://localhost|127.0.0.1[:port]/...
  model     str  1..120 chars, no spaces at the ends, no newlines
  key_env   str  ^[A-Z][A-Z0-9_]{2,40}$   required when needs_key is true, else may be ""
  needs_key bool
  paid      bool
  price_in  float >= 0   (USD per 1M input tokens), required > 0 when paid
  price_out float >= 0   required > 0 when paid
  note      str  optional, <= 200 chars
"""
import json, os, tempfile, unittest
from pathlib import Path

from dante import models_hub as H

GOOD = {"name": "my-mistral", "base_url": "https://api.mistral.ai/v1", "model": "mistral-small-latest",
        "key_env": "MISTRAL_API_KEY", "needs_key": True, "paid": False, "price_in": 0.0, "price_out": 0.0, "note": ""}


def e(**kw):
    d = dict(GOOD); d.update(kw); return d


class ValidateTest(unittest.TestCase):
    def test_good_entry_has_no_errors(self):
        self.assertEqual(H.validate(GOOD, taken=set()), [])

    def test_errors_are_list_of_field_names(self):
        errs = H.validate(e(name="Bad Name", base_url="ftp://x"), taken=set())
        self.assertIsInstance(errs, list)
        self.assertIn("name", errs)
        self.assertIn("base_url", errs)

    def test_name_rules(self):
        for bad in ["", "a", "-abc", "ABC", "a b", "a_b", "x" * 32, "мова"]:
            self.assertIn("name", H.validate(e(name=bad), taken=set()), bad)
        for ok in ["ab", "a1", "my-model-2", "x" * 31]:
            self.assertNotIn("name", H.validate(e(name=ok), taken=set()), ok)

    def test_name_taken_or_builtin(self):
        self.assertIn("name", H.validate(GOOD, taken={"my-mistral"}))
        for b in H.BUILTIN_NAMES:
            self.assertIn("name", H.validate(e(name=b), taken=set()), b)
        from dante.config import DEFAULT_PROVIDERS
        self.assertEqual(H.BUILTIN_NAMES, frozenset(p.name for p in DEFAULT_PROVIDERS))

    def test_url_rules(self):
        for ok in ["https://api.x.ai/v1", "http://localhost:11434/v1", "http://127.0.0.1:8080/v1", "https://a.b/c/"]:
            self.assertNotIn("base_url", H.validate(e(base_url=ok), taken=set()), ok)
        for bad in ["", "http://api.x.ai/v1", "ftp://a", "https://", "https://a b.com", "localhost:11434",
                    "http://192.168.1.5/v1", "https://a.com/v1?key=1"]:
            self.assertIn("base_url", H.validate(e(base_url=bad), taken=set()), bad)

    def test_model_rules(self):
        self.assertIn("model", H.validate(e(model=""), taken=set()))
        self.assertIn("model", H.validate(e(model=" x"), taken=set()))
        self.assertIn("model", H.validate(e(model="a\nb"), taken=set()))
        self.assertIn("model", H.validate(e(model="m" * 121), taken=set()))
        self.assertNotIn("model", H.validate(e(model="meta-llama/Llama-3.3-70B-Instruct"), taken=set()))

    def test_key_env_rules(self):
        self.assertIn("key_env", H.validate(e(key_env=""), taken=set()))
        self.assertIn("key_env", H.validate(e(key_env="mistral_key"), taken=set()))
        self.assertIn("key_env", H.validate(e(key_env="AB"), taken=set()))
        self.assertNotIn("key_env", H.validate(e(needs_key=False, key_env=""), taken=set()))
        self.assertNotIn("key_env", H.validate(e(key_env="MY_KEY_2"), taken=set()))

    def test_paid_needs_prices(self):
        self.assertIn("price_in", H.validate(e(paid=True), taken=set()))
        self.assertIn("price_out", H.validate(e(paid=True, price_in=1.0), taken=set()))
        self.assertEqual(H.validate(e(paid=True, price_in=0.2, price_out=0.6), taken=set()), [])
        self.assertIn("price_in", H.validate(e(price_in=-1.0), taken=set()))
        self.assertIn("price_out", H.validate(e(price_out="abc"), taken=set()))

    def test_types(self):
        self.assertIn("needs_key", H.validate(e(needs_key="yes"), taken=set()))
        self.assertIn("paid", H.validate(e(paid=1), taken=set()))
        self.assertIn("note", H.validate(e(note="n" * 201), taken=set()))
        self.assertIn("name", H.validate(e(name=5), taken=set()))

    def test_missing_fields_reported(self):
        d = dict(GOOD); del d["model"]
        self.assertIn("model", H.validate(d, taken=set()))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.dir = Path(self.tmp.name)
        self.path = self.dir / "models.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_file_is_empty(self):
        self.assertEqual(H.load(self.path), [])

    def test_load_bad_file_is_empty_and_keeps_file(self):
        self.path.write_text("{oops", encoding="utf-8")
        self.assertEqual(H.load(self.path), [])
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{oops")

    def test_load_skips_invalid_entries(self):
        self.path.write_text(json.dumps({"models": [GOOD, e(name="Bad Name"), "x", e(name="my-mistral")]}), encoding="utf-8")
        got = H.load(self.path)
        self.assertEqual([m["name"] for m in got], ["my-mistral"])

    def test_save_then_load_roundtrip(self):
        H.save(self.path, [GOOD])
        self.assertEqual(H.load(self.path), [GOOD])
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(list(data), ["models"])

    def test_save_is_atomic_no_temp_left(self):
        H.save(self.path, [GOOD]); H.save(self.path, [GOOD])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["models.json"])

    def test_save_creates_folder(self):
        p = self.dir / "sub" / "models.json"
        H.save(p, [GOOD])
        self.assertTrue(p.exists())

    def test_upsert_adds_and_replaces(self):
        H.upsert(self.path, GOOD)
        H.upsert(self.path, e(model="mistral-large-latest"))
        got = H.load(self.path)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["model"], "mistral-large-latest")
        H.upsert(self.path, e(name="other"))
        self.assertEqual([m["name"] for m in H.load(self.path)], ["my-mistral", "other"])

    def test_upsert_rejects_invalid(self):
        with self.assertRaises(ValueError) as cm:
            H.upsert(self.path, e(base_url="http://evil.com"))
        self.assertIn("base_url", str(cm.exception))
        self.assertFalse(self.path.exists())

    def test_upsert_fills_defaults(self):
        H.upsert(self.path, {"name": "loc", "base_url": "http://localhost:11434/v1", "model": "qwen", "needs_key": False})
        m = H.load(self.path)[0]
        self.assertEqual((m["key_env"], m["paid"], m["price_in"], m["price_out"], m["note"]), ("", False, 0.0, 0.0, ""))

    def test_remove(self):
        H.upsert(self.path, GOOD); H.upsert(self.path, e(name="other"))
        self.assertTrue(H.remove(self.path, "my-mistral"))
        self.assertFalse(H.remove(self.path, "my-mistral"))
        self.assertEqual([m["name"] for m in H.load(self.path)], ["other"])


class KeysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = Path(self.tmp.name) / "keys.txt"

    def tearDown(self):
        self.tmp.cleanup()

    def test_set_key_creates_file(self):
        H.set_key(self.p, "MISTRAL_API_KEY", "abc123")
        self.assertEqual(self.p.read_text(encoding="utf-8"), "MISTRAL_API_KEY=abc123\n")

    def test_set_key_replaces_only_that_line(self):
        self.p.write_text("# my keys\nGROQ_API_KEY=g1\nMISTRAL_API_KEY=old\nOTHER=o\n", encoding="utf-8")
        H.set_key(self.p, "MISTRAL_API_KEY", "new")
        self.assertEqual(self.p.read_text(encoding="utf-8"), "# my keys\nGROQ_API_KEY=g1\nMISTRAL_API_KEY=new\nOTHER=o\n")

    def test_set_key_appends_with_newline(self):
        self.p.write_text("GROQ_API_KEY=g1", encoding="utf-8")
        H.set_key(self.p, "MISTRAL_API_KEY", "m")
        self.assertEqual(self.p.read_text(encoding="utf-8"), "GROQ_API_KEY=g1\nMISTRAL_API_KEY=m\n")

    def test_set_key_strips_and_rejects_bad(self):
        H.set_key(self.p, "MISTRAL_API_KEY", "  abc  \n")
        self.assertEqual(self.p.read_text(encoding="utf-8"), "MISTRAL_API_KEY=abc\n")
        for env, val in [("bad", "x"), ("MISTRAL_API_KEY", ""), ("MISTRAL_API_KEY", "a\nb"), ("MISTRAL_API_KEY", "a b")]:
            with self.assertRaises(ValueError):
                H.set_key(self.p, env, val)

    def test_error_never_contains_value(self):
        try:
            H.set_key(self.p, "MISTRAL_API_KEY", "secret value")
        except ValueError as ex:
            self.assertNotIn("secret", str(ex))

    def test_has_key(self):
        self.p.write_text("A_KEY=1\nB_KEY=\n", encoding="utf-8")
        self.assertTrue(H.has_key(self.p, "A_KEY"))
        self.assertFalse(H.has_key(self.p, "B_KEY"))
        self.assertFalse(H.has_key(self.p, "C_KEY"))
        self.assertFalse(H.has_key(Path(self.tmp.name) / "none.txt", "A_KEY"))


class ReviewFindingsTest(unittest.TestCase):
    """Defects found by Claude in DANTE's first version (19.11.2026)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_fills_missing_optional_fields(self):
        # a hand-edited file without "note"/prices must not crash the window later (m["note"])
        p = self.dir / "models.json"
        d = dict(GOOD); del d["note"]; del d["price_in"]; del d["price_out"]
        p.write_text(json.dumps({"models": [d]}), encoding="utf-8")
        m = H.load(p)[0]
        self.assertEqual((m["note"], m["price_in"], m["price_out"]), ("", 0.0, 0.0))

    def test_key_value_with_tab_or_cr_rejected(self):
        p = self.dir / "keys.txt"
        for bad in ["a\tb", "a\rb"]:
            with self.assertRaises(ValueError):
                H.set_key(p, "MISTRAL_API_KEY", bad)

    def test_infinite_or_nan_price_rejected(self):
        for v in (float("inf"), float("nan")):
            self.assertIn("price_in", H.validate(e(paid=True, price_in=v, price_out=1.0), taken=set()))

    def test_bad_key_name_type_is_value_error(self):
        with self.assertRaises(ValueError):
            H.set_key(self.dir / "k.txt", None, "x")


if __name__ == "__main__":
    unittest.main()
