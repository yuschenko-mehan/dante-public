"""Spec: after a crash or power loss, jobs that were running are queued again ONCE.
Специфікація: після збою чи зникнення світла завдання, що виконувались, ставляться в чергу ще РАЗ."""
import json
import tempfile
import unittest
from pathlib import Path

from dante import resume as R


class ResumeTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        b = Path(self.t.name)
        self.inbox, self.outbox = b / "inbox", b / "outbox"
        (self.inbox / "done").mkdir(parents=True)
        self.outbox.mkdir()

    def tearDown(self):
        self.t.cleanup()

    def job(self, stem, data=None, running=True, result=False):
        (self.inbox / "done" / f"{stem}.json").write_text(json.dumps(data or {"kind": "cmd", "command": "echo"}),
                                                          encoding="utf-8")
        if running:
            (self.outbox / f"{stem}.running").write_text("", encoding="utf-8")
        if result:
            (self.outbox / f"{stem}.txt").write_text("EXIT 0", encoding="utf-8")

    def test_interrupted_job_is_queued_again_with_retry_suffix(self):
        self.job("50-build")
        out = R.resume_interrupted(self.inbox, self.outbox)
        self.assertEqual(out, ["50-build"])
        again = self.inbox / "50-build-retry1.json"
        self.assertTrue(again.exists())
        self.assertEqual(json.loads(again.read_text(encoding="utf-8"))["command"], "echo")
        self.assertFalse((self.outbox / "50-build.running").exists())

    def test_job_with_a_result_is_not_repeated(self):
        self.job("51-ok", result=True)
        self.assertEqual(R.resume_interrupted(self.inbox, self.outbox), [])
        self.assertFalse((self.outbox / "51-ok.running").exists())

    def test_a_retry_is_never_retried_again(self):
        self.job("52-x-retry1")
        self.assertEqual(R.resume_interrupted(self.inbox, self.outbox), [])
        txt = (self.outbox / "52-x-retry1.txt").read_text(encoding="utf-8")
        self.assertIn("EXIT", txt)
        self.assertIn("interrupted", txt.lower())

    def test_restart_jobs_are_not_repeated(self):
        self.job("60-restart-pult", {"kind": "cmd", "command": r"python C:\DANTE\dante\restart_pult.py --job 60"})
        self.assertEqual(R.resume_interrupted(self.inbox, self.outbox), [])

    def test_running_marker_without_job_file_is_cleaned(self):
        (self.outbox / "70-lost.running").write_text("", encoding="utf-8")
        self.assertEqual(R.resume_interrupted(self.inbox, self.outbox), [])
        self.assertFalse((self.outbox / "70-lost.running").exists())

    def test_existing_retry_in_inbox_is_not_overwritten(self):
        self.job("53-y")
        (self.inbox / "53-y-retry1.json").write_text('{"kind":"cmd","command":"keep"}', encoding="utf-8")
        R.resume_interrupted(self.inbox, self.outbox)
        self.assertIn("keep", (self.inbox / "53-y-retry1.json").read_text(encoding="utf-8"))

    def test_note_is_written_to_the_log(self):
        self.job("54-z")
        log = []
        R.resume_interrupted(self.inbox, self.outbox, say=log.append)
        self.assertTrue(any("54-z" in m for m in log))


if __name__ == "__main__":
    unittest.main()
