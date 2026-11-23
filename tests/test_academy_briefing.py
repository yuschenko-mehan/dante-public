"""Spec: the ACADEMY gives a LESSON before every mission (author, 23.11.2026). Before attempt 1 the first teacher
gets the task once and answers with a short lesson: approach, pitfalls, what the tests will check. The lesson goes into
every attempt's prompt as "ACADEMY LESSON:". Hints after two own mistakes stay as before.
Специфікація: АКАДЕМІЯ дає УРОК перед кожною місією: перед 1-ю спробою перший учитель один раз отримує завдання
й відповідає коротким уроком (підхід, пастки, що перевірять тести); урок іде в запит кожної спроби як
"ACADEMY LESSON:". Підказки після двох власних помилок — як і раніше."""
import tempfile
import unittest

from dante import loop as L
from dante.config import Settings
from tests.test_academy import BAD, GOOD, Fake, go


class TestBriefing(unittest.TestCase):
    def test_default_on(self):
        self.assertTrue(Settings().academy_briefing)

    def test_lesson_prompt(self):
        p = L.lesson_prompt("TASK-Y")
        self.assertIn("TASK-Y", p)
        self.assertIn("pitfall", p.lower())
        self.assertIn("lesson", p.lower())

    def test_lesson_asked_once_before_attempt_1_and_used_in_every_prompt(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([BAD, GOOD])
            teacher = Fake(["LESSON: return the sum, not the difference."])
            r = go(t, main, teacher, attempts=3, solo=5, briefing=True)
            self.assertTrue(r.success)
            self.assertEqual(len(teacher.calls), 1)
            self.assertIn("Write calc.add", teacher.calls[0][1])
            for _, prompt in main.calls:
                self.assertIn("ACADEMY LESSON:", prompt)
                self.assertIn("return the sum", prompt)

    def test_teacher_failure_does_not_stop_the_mission(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([GOOD])
            r = go(t, main, Fake([RuntimeError("down")]), attempts=2, solo=5, briefing=True)
            self.assertTrue(r.success)
            self.assertNotIn("ACADEMY LESSON:", main.calls[0][1])

    def test_lesson_is_capped(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([GOOD])
            go(t, main, Fake(["x" * 9000]), attempts=1, solo=5, briefing=True)
            self.assertLess(main.calls[0][1].count("x"), 1600)

    def test_no_teacher_no_lesson(self):
        with tempfile.TemporaryDirectory() as t:
            main = Fake([GOOD])
            go(t, main, None, attempts=1, briefing=True)
            self.assertNotIn("ACADEMY LESSON:", main.calls[0][1])


if __name__ == "__main__":
    unittest.main()
