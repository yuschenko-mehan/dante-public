"""Specification for dante/lessons.py — DANTE's memory of past mistakes, so it does not repeat them.

lessons.json holds {"lessons": [lesson, ...]}. A lesson:
  id      "L001", "L002", ... (next number = max existing + 1, three digits at least)
  date    "YYYY-MM-DD"
  source  "claude-review" (a fix made by a reviewer) or "self" (DANTE failed, then succeeded)
  tags    list of 1..8 tags, each ^[a-z0-9][a-z0-9-]{1,19}$, sorted, no duplicates
  mistake str, 1..300 chars after stripping (inner whitespace runs become one space)
  rule    str, 1..300 chars, same cleaning
  seen    int >= 1  (how many times this mistake happened)

load(path) -> list of lessons; missing file, bad JSON or a non-list -> []; entries that are not valid are skipped.
save(path, lessons): atomic (temp file in the same folder + os.replace), UTF-8, ensure_ascii=False, creates folders.
add(path, mistake, rule, tags, source="claude-review", today=None) -> the stored lesson
    today: "YYYY-MM-DD" (default: today's date). Invalid input -> ValueError (file unchanged).
    Tags are lower-cased before checking. If a lesson with the same rule already exists (compare cleaned rules,
    case-insensitive), no new lesson is made: its seen += 1, its tags become the sorted union (max 8: keep the
    first 8 after sorting) and it is saved and returned.
STOPWORDS: frozenset with at least: the and for with that this from into must should never always python file
    files test tests code use not are was when then than
guess_tags(text, max_tags=6) -> list: words = lower-cased runs of [a-z0-9] split at everything else (so "_"
    and "." split words); keep words of 3..20 chars that start with a letter and are not STOPWORDS;
    most frequent first, ties alphabetically; at most max_tags.
relevant(lessons, text, k=8) -> list: score = number of the lesson's tags found among the words of text
    (same splitting as guess_tags, no length limit); a lesson tagged "always" scores at least 1.
    Keep lessons with score >= 1, sort by score desc, then seen desc, then id asc; return the first k.
render(lessons) -> "" for an empty list, else
    "LESSONS FROM PAST MISTAKES (follow these rules):\\n" + one line per lesson: "- <rule> (was: <mistake>)"
    joined with "\\n", no newline at the end.
"""
import json, tempfile, unittest
from pathlib import Path

from dante import lessons as Ls


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name); self.p = self.d / "lessons.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_and_load(self):
        a = Ls.add(self.p, " Optional  fields\nmissing ", "Fill defaults on load", ["JSON", "load"], today="2026-11-19")
        self.assertEqual(a, {"id": "L001", "date": "2026-11-19", "source": "claude-review", "tags": ["json", "load"],
                             "mistake": "Optional fields missing", "rule": "Fill defaults on load", "seen": 1})
        b = Ls.add(self.p, "m2", "r2", ["x1"], source="self", today="2026-11-20")
        self.assertEqual(b["id"], "L002")
        self.assertEqual(Ls.load(self.p), [a, b])
        self.assertIn("Fill defaults", self.p.read_text(encoding="utf-8"))

    def test_same_rule_counts_instead_of_duplicate(self):
        Ls.add(self.p, "m", "Check NaN and inf", ["float"], today="2026-11-19")
        again = Ls.add(self.p, "other words", "  check nan  AND inf ", ["price", "float"], today="2026-11-21")
        self.assertEqual((again["id"], again["seen"], again["tags"]), ("L001", 2, ["float", "price"]))
        self.assertEqual(len(Ls.load(self.p)), 1)

    def test_tag_union_capped(self):
        Ls.add(self.p, "m", "r", [f"t{i}" for i in range(1, 7)], today="2026-11-19")
        got = Ls.add(self.p, "m", "r", ["a1", "a2", "a3"], today="2026-11-19")
        self.assertEqual(got["tags"], sorted([f"t{i}" for i in range(1, 7)] + ["a1", "a2", "a3"])[:8])

    def test_invalid(self):
        for args in [("", "r", ["t1"]), ("m", " ", ["t1"]), ("m", "r", []), ("m", "r", ["bad tag"]),
                     ("m", "r", ["x"]), ("m", "r", [f"t{i}" for i in range(9)]), ("m" * 301, "r", ["t1"])]:
            with self.assertRaises(ValueError, msg=repr(args)[:40]):
                Ls.add(self.p, *args, today="2026-11-19")
        with self.assertRaises(ValueError):
            Ls.add(self.p, "m", "r", ["t1"], source="other", today="2026-11-19")
        with self.assertRaises(ValueError):
            Ls.add(self.p, "m", "r", ["t1"], today="19.11.2026")
        self.assertFalse(self.p.exists())

    def test_default_date_is_today(self):
        import datetime
        self.assertEqual(Ls.add(self.p, "m", "r", ["t1"])["date"], datetime.date.today().isoformat())

    def test_load_bad(self):
        self.assertEqual(Ls.load(self.p), [])
        self.p.write_text("{bad", encoding="utf-8")
        self.assertEqual(Ls.load(self.p), [])
        good = {"id": "L007", "date": "2026-11-19", "source": "self", "tags": ["ab"], "mistake": "m", "rule": "r", "seen": 3}
        self.p.write_text(json.dumps({"lessons": [good, {"id": "x"}, 5, dict(good, seen=0)]}), encoding="utf-8")
        self.assertEqual(Ls.load(self.p), [good])
        self.assertEqual(Ls.add(self.p, "m2", "r2", ["ab"], today="2026-11-19")["id"], "L008")

    def test_save_atomic(self):
        p = self.d / "sub" / "lessons.json"
        Ls.save(p, []); Ls.save(p, [])
        self.assertEqual([x.name for x in p.parent.iterdir()], ["lessons.json"])


class UseTest(unittest.TestCase):
    L = [
        {"id": "L001", "date": "d", "source": "self", "tags": ["json", "load"], "mistake": "m1", "rule": "r1", "seen": 1},
        {"id": "L002", "date": "d", "source": "self", "tags": ["always"], "mistake": "m2", "rule": "r2", "seen": 1},
        {"id": "L003", "date": "d", "source": "self", "tags": ["json", "price"], "mistake": "m3", "rule": "r3", "seen": 5},
        {"id": "L004", "date": "d", "source": "self", "tags": ["gui"], "mistake": "m4", "rule": "r4", "seen": 9},
        {"id": "L005", "date": "d", "source": "self", "tags": ["load"], "mistake": "m5", "rule": "r5", "seen": 1},
    ]

    def test_relevant_order(self):
        got = [x["id"] for x in Ls.relevant(self.L, "Load models.json and check the price_in")]
        self.assertEqual(got, ["L003", "L001", "L002", "L005"])  # L003: json+price, seen 5; L001: json+load
        self.assertEqual([x["id"] for x in Ls.relevant(self.L, "nothing here", k=8)], ["L002"])
        self.assertEqual(len(Ls.relevant(self.L, "json load price gui", k=2)), 2)

    def test_guess_tags(self):
        text = "Create models_hub.py: load models.json, save models.json atomically. The tests must pass. a1 x"
        self.assertEqual(Ls.guess_tags(text), ["models", "json", "atomically", "create", "hub", "load"])
        self.assertEqual(Ls.guess_tags(text, max_tags=2), ["models", "json"])
        self.assertEqual(Ls.guess_tags("the and 123abc python"), [])

    def test_render(self):
        self.assertEqual(Ls.render([]), "")
        self.assertEqual(Ls.render(self.L[:2]),
                         "LESSONS FROM PAST MISTAKES (follow these rules):\n- r1 (was: m1)\n- r2 (was: m2)")


class ReviewFindingsTest(unittest.TestCase):
    """Claude's review of DANTE's version (19.11.2026) / Рецензія Claude на версію Данте."""

    def test_always_is_at_least_one_not_plus_one(self):
        ls = [{"id": "L001", "date": "d", "source": "self", "tags": ["always", "json"], "mistake": "m", "rule": "a", "seen": 1},
              {"id": "L002", "date": "d", "source": "self", "tags": ["json", "load"], "mistake": "m", "rule": "b", "seen": 1}]
        self.assertEqual([x["id"] for x in Ls.relevant(ls, "load json")], ["L002", "L001"])

    def test_hand_edited_lesson_is_normalised_not_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lessons.json"
            raw = {"id": "L001", "date": "2026-11-19", "source": "self", "tags": ["load", "json"],
                   "mistake": "two  spaces", "rule": "r", "seen": 1}
            p.write_text(json.dumps({"lessons": [raw]}), encoding="utf-8")
            got = Ls.load(p)
            self.assertEqual((got[0]["tags"], got[0]["mistake"]), (["json", "load"], "two spaces"))


if __name__ == "__main__":
    unittest.main()
