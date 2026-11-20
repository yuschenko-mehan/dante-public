"""Spec: install roles and language choice / Специфікація: ролі встановлення і вибір мови."""
import json
import unittest
import tempfile
from pathlib import Path

from dante import roles as R


class TestRolesFile(unittest.TestCase):
    def test_roles_in_order(self):
        # Five roles, in this order / П'ять ролей у такому порядку
        self.assertEqual(R.role_ids(), ["archant", "reserve", "knyaz", "ant", "solo"])

    def test_both_languages_everywhere(self):
        for rid in R.role_ids():
            for lang in ("uk", "en"):
                self.assertTrue(R.name(rid, lang).strip())
                self.assertTrue(R.summary(rid, lang).strip())
        self.assertEqual(R.name("knyaz", "uk"), "Князь")
        self.assertEqual(R.name("knyaz", "en"), "Knyaz")
        self.assertEqual(R.name("archant", "uk"), "Архант")
        self.assertEqual(R.name("archant", "en"), "Archant")
        # unknown language falls back to English / невідома мова -> англійська
        self.assertEqual(R.name("ant", "de"), R.name("ant", "en"))

    def test_components_and_needs(self):
        self.assertIn("dante", R.components("archant"))
        self.assertIn("murakha", R.components("archant"))
        k = R.components("knyaz")
        self.assertIn("murakha", k)
        # a friend's PC gets no keys tools and no DANTE core / ПК друга без ядра Данте
        for c in ("dante", "freellmapi", "claude_code", "gh"):
            self.assertNotIn(c, k)
        self.assertEqual(R.needs("knyaz"), ["consent", "archant_public"])
        self.assertEqual(R.needs("solo"), [])
        self.assertNotIn("murakha", R.components("solo"))
        with self.assertRaises(KeyError):
            R.components("king")

    def test_validate_catches_errors(self):
        data = json.loads(R.ROLES_FILE.read_text(encoding="utf-8"))
        self.assertEqual(R.validate(data), [])
        bad = json.loads(json.dumps(data))
        bad["roles"][0]["name"]["en"] = ""
        self.assertTrue(R.validate(bad))
        bad = json.loads(json.dumps(data))
        bad["roles"][1]["id"] = "archant"
        self.assertTrue(R.validate(bad))
        bad = json.loads(json.dumps(data))
        bad["roles"][2]["components"] = []
        self.assertTrue(R.validate(bad))
        self.assertTrue(R.validate({"roles": []}))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "roles.json"
            bad["roles"][2]["components"] = []
            p.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                R.load_roles(p)


class TestChoice(unittest.TestCase):
    def test_language(self):
        for a in ("1", "uk", "UA", " Українська ", "укр"):
            self.assertEqual(R.parse_language(a), "uk", a)
        for a in ("2", "en", "English", "англійська"):
            self.assertEqual(R.parse_language(a), "en", a)
        for a in ("", "3", "de", "russian"):
            self.assertIsNone(R.parse_language(a), a)

    def test_menu(self):
        uk = R.menu_text("uk").splitlines()
        en = R.menu_text("en").splitlines()
        self.assertEqual(uk[0], "Який Данте встановити?")
        self.assertEqual(en[0], "Which DANTE to install?")
        self.assertEqual(len(uk), 6)
        self.assertTrue(uk[1].startswith("1. Архант — "))
        self.assertTrue(en[3].startswith("3. Knyaz — "))
        self.assertTrue(uk[5].startswith("5. Окремий Данте — "))

    def test_role_choice(self):
        self.assertEqual(R.parse_choice("1"), "archant")
        self.assertEqual(R.parse_choice(" 3 "), "knyaz")
        self.assertEqual(R.parse_choice("князь"), "knyaz")
        self.assertEqual(R.parse_choice("KNYAZ"), "knyaz")
        self.assertEqual(R.parse_choice("Reserve Archant"), "reserve")
        self.assertEqual(R.parse_choice("мураха"), "ant")
        for bad in ("", "0", "6", "king", "-1"):
            self.assertIsNone(R.parse_choice(bad), bad)


class TestRules(unittest.TestCase):
    def test_only_one_archant(self):
        # New swarm: anyone may become the Archant; existing swarm: only with the flash
        # Новий рій: Архантом може стати будь-хто; наявний рій — лише з флешкою
        self.assertTrue(R.can_become("archant", has_flash=False, swarm_exists=False))
        self.assertFalse(R.can_become("archant", has_flash=False, swarm_exists=True))
        self.assertTrue(R.can_become("archant", has_flash=True, swarm_exists=True))
        for rid in ("reserve", "knyaz", "ant", "solo"):
            self.assertTrue(R.can_become(rid, has_flash=False, swarm_exists=True))
        with self.assertRaises(KeyError):
            R.can_become("king", True, False)

    def test_save_and_load_role(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "role.json"
            self.assertIsNone(R.load_role(p))
            R.save_role(p, "knyaz", "en", now=123)
            self.assertEqual(R.load_role(p), {"role": "knyaz", "lang": "en", "since": 123})
            p.write_text('{"role": "king", "lang": "uk", "since": 1}', encoding="utf-8")
            self.assertIsNone(R.load_role(p))
            p.write_text("not json", encoding="utf-8")
            self.assertIsNone(R.load_role(p))
            with self.assertRaises(KeyError):
                R.save_role(p, "king", "uk")


if __name__ == "__main__":
    unittest.main()
