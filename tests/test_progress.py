"""Spec: PROGRESS window — the author sees that DANTE is alive and what it does now (jobs, attempts, code being written),
in a small window that can be folded into a thin bar and never gets in the way.
Специфікація: вікно ПРОГРЕСУ — автор бачить, що Данте живий і що робить зараз; маленьке вікно, згортається в тонку смужку."""
import unittest

from dante import progress as P

LOG = """2026-11-23 10:27:51 DANTE pult: watching C:\\DANTE\\inbox, parallel 3
2026-11-23 10:40:00 start [vision]: 149a1-screen-read.json
2026-11-23 10:41:00 start [ollama]: 149b-pull-qwenvl.json
2026-11-23 10:41:05 start [icon]: 148-boot-check.json
2026-11-23 10:41:07 done / готово: 148-boot-check.json
2026-11-23 10:44:00 done / готово: 149b-pull-qwenvl.json""".splitlines()


class ParseTest(unittest.TestCase):
    def test_running_and_done(self):
        s = P.status_from_log(LOG, now="2026-11-23 10:45:00")
        self.assertEqual([j.name for j in s.running], ["149a1-screen-read"])
        self.assertEqual(s.running[0].lane, "vision")
        self.assertEqual(s.running[0].seconds, 300)
        self.assertEqual([j.name for j in s.recent], ["149b-pull-qwenvl", "148-boot-check"])
        self.assertTrue(s.alive)

    def test_quiet_log_means_idle_not_dead(self):
        s = P.status_from_log(LOG[:1], now="2026-11-23 12:00:00")
        self.assertEqual(s.running, [])
        self.assertTrue(s.alive)

    def test_empty_log_is_not_alive(self):
        self.assertFalse(P.status_from_log([], now="2026-11-23 12:00:00").alive)

    def test_pult_exit_line_does_not_kill_alive(self):
        s = P.status_from_log(LOG + ["2026-11-23 10:44:30 another pult is already running — exiting"], now="2026-11-23 10:45:00")
        self.assertTrue(s.alive)

    def test_restart_forgets_jobs_started_before_it(self):
        lines = ["2026-11-23 09:00:00 start [a]: 1-x.json", "2026-11-23 10:27:51 DANTE pult: watching C:\\DANTE\\inbox"]
        self.assertEqual(P.status_from_log(lines, now="2026-11-23 10:30:00").running, [])


class TextTest(unittest.TestCase):
    def test_bar_text_uk_and_en(self):
        s = P.status_from_log(LOG, now="2026-11-23 10:45:00")
        self.assertEqual(P.bar_text(s, "uk"), "● Данте працює · завдань: 1 · 149a1-screen-read 5 хв")
        self.assertEqual(P.bar_text(s, "en"), "● DANTE working · jobs: 1 · 149a1-screen-read 5 min")
        idle = P.status_from_log(LOG[:1], now="2026-11-23 10:45:00")
        self.assertEqual(P.bar_text(idle, "uk"), "● Данте чекає завдань")
        self.assertEqual(P.bar_text(P.status_from_log([], now="x"), "uk"), "○ Данте не запущений")

    def test_detail_lines(self):
        s = P.status_from_log(LOG, now="2026-11-23 10:45:00")
        lines = P.detail_lines(s, "uk")
        self.assertIn("▶ 149a1-screen-read [vision] — 5 хв", lines)
        self.assertIn("✓ 149b-pull-qwenvl", lines)

    def test_minutes_format(self):
        self.assertEqual(P.human_time(45, "uk"), "45 с")
        self.assertEqual(P.human_time(300, "uk"), "5 хв")
        self.assertEqual(P.human_time(3900, "uk"), "1 год 5 хв")
        self.assertEqual(P.human_time(3900, "en"), "1 h 5 min")


class ResultTest(unittest.TestCase):
    def test_failed_jobs_are_marked_from_outbox_text(self):
        s = P.status_from_log(LOG, now="2026-11-23 10:45:00",
                              read_result=lambda name: "EXIT 1\nFAILED after 4" if name == "148-boot-check" else "EXIT 0")
        lines = P.detail_lines(s, "uk")
        self.assertIn("✗ 148-boot-check", lines)


if __name__ == "__main__":
    unittest.main()


class PultIndicatorTest(unittest.TestCase):
    def test_fresh_heartbeat(self):
        self.assertEqual(P.pult_text("2026-11-23 12:40:00", "2026-11-23 12:40:07", "uk"), "Пульт: ● працює (пульс 7 с тому)")
        self.assertEqual(P.pult_text("2026-11-23 12:40:00", "2026-11-23 12:40:07", "en"), "Pult: ● running (pulse 7 s ago)")

    def test_old_or_missing_heartbeat(self):
        self.assertEqual(P.pult_text("2026-11-23 12:00:00", "2026-11-23 12:12:00", "uk"), "Пульт: ○ мовчить 12 хв")
        self.assertEqual(P.pult_text(None, "2026-11-23 12:12:00", "uk"), "Пульт: ○ не запущений")
        self.assertEqual(P.pult_text("garbage", "2026-11-23 12:12:00", "uk"), "Пульт: ○ не запущений")


class LiveAuditTest(unittest.TestCase):
    EV = [{"event": "task_start", "task": "Write calc.add"},
          {"event": "academy_lesson", "lesson": "return the sum"},
          {"event": "mission_plan", "steps": ["a", "b", "c"]},
          {"event": "mission_step", "step": 2, "total": 3},
          {"event": "llm_response", "attempt": 1, "model": "groq:gpt-oss"},
          {"event": "files_written", "attempt": 1, "files": ["calc.py"]},
          {"event": "test_run", "attempt": 1, "exit_code": 1, "output_tail": "FAILED (failures=2)"},
          {"event": "llm_response", "attempt": 2, "model": "gemini:flash"}]

    def test_live_lines(self):
        lines = P.live_lines(self.EV, "uk")
        self.assertEqual(lines[0], "Завдання: Write calc.add")
        self.assertIn("План: 3 кроків · крок 2 з 3", lines)
        self.assertIn("Урок Академії: є", lines)
        self.assertIn("Спроба 2 · gemini:flash", lines)
        self.assertIn("Файли: calc.py", lines)
        self.assertIn("Тести: ✗ не пройшли (FAILED (failures=2))", lines)

    def test_success_and_empty(self):
        lines = P.live_lines(self.EV + [{"event": "test_run", "attempt": 2, "exit_code": 0, "output_tail": "OK"},
                                        {"event": "task_success", "attempts": 2}], "uk")
        self.assertIn("Тести: ✓ пройшли", lines)
        self.assertIn("Готово ✓", lines)
        self.assertEqual(P.live_lines([], "uk"), [])
