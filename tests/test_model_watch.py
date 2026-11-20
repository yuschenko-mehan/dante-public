"""Spec: daily watch for NEW AI models worldwide; the critic decides what is worth adding.
Специфікація: щоденний моніторинг НОВИХ моделей ШІ у світі; критик вирішує, що варто додати."""
import json
import tempfile
import unittest
from pathlib import Path

from dante import model_watch as W


def fake_sources():
    return {
        "openrouter": lambda: [{"id": "meta/llama-9:free", "name": "Llama 9", "free": True, "ctx": 128000},
                               {"id": "acme/pro-1", "name": "Pro 1", "free": False, "ctx": 32000}],
        "freellmapi": lambda: [{"id": "auto", "name": "auto", "free": True, "ctx": 0}],
        "broken": lambda: (_ for _ in ()).throw(RuntimeError("HTTP 500")),
    }


class DiffTest(unittest.TestCase):
    def test_diff_finds_only_new_ids_per_source(self):
        old = {"openrouter": [{"id": "a"}], "freellmapi": []}
        new = {"openrouter": [{"id": "a"}, {"id": "b"}], "freellmapi": [{"id": "auto"}]}
        d = W.diff(old, new)
        self.assertEqual([m["id"] for m in d["openrouter"]], ["b"])
        self.assertEqual([m["id"] for m in d["freellmapi"]], ["auto"])

    def test_first_run_has_no_old_snapshot_and_reports_nothing_new(self):
        d = W.diff(None, {"openrouter": [{"id": "a"}]})
        self.assertEqual(d, {})

    def test_removed_models_are_not_reported(self):
        self.assertEqual(W.diff({"s": [{"id": "a"}, {"id": "b"}]}, {"s": [{"id": "a"}]}), {})


class SnapshotTest(unittest.TestCase):
    def test_save_and_load_roundtrip_and_missing_or_broken_file(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "snap.json"
            self.assertIsNone(W.load_snapshot(p))
            W.save_snapshot(p, {"s": [{"id": "a"}]}, now="2026-11-20T10:00:00")
            self.assertEqual(W.load_snapshot(p), {"s": [{"id": "a"}]})
            p.write_text("{broken", encoding="utf-8")
            self.assertIsNone(W.load_snapshot(p))


class CriticTest(unittest.TestCase):
    def test_prompt_lists_new_models_and_asks_for_json_and_never_for_secrets(self):
        txt = W.build_prompt({"openrouter": [{"id": "meta/llama-9:free", "free": True, "ctx": 128000}]},
                             known_services=["groq", "gemini"])
        self.assertIn("meta/llama-9:free", txt)
        self.assertIn("JSON", txt)
        self.assertIn("groq", txt)
        self.assertNotIn("api_key", txt.lower())

    def test_parse_reply_accepts_json_in_text_and_drops_unknown_ids(self):
        new = {"openrouter": [{"id": "x"}, {"id": "y"}]}
        reply = 'Here you go: [{"id":"x","verdict":"add","why":"free and large"},{"id":"zzz","verdict":"add","why":"?"}]'
        res = W.parse_reply(reply, new)
        self.assertEqual([r["id"] for r in res], ["x"])
        self.assertEqual(res[0]["verdict"], "add")

    def test_parse_reply_garbage_gives_empty_list(self):
        self.assertEqual(W.parse_reply("no json at all", {"s": [{"id": "x"}]}), [])

    def test_verdict_must_be_add_watch_or_skip(self):
        res = W.parse_reply('[{"id":"x","verdict":"BUY NOW","why":"."}]', {"s": [{"id": "x"}]})
        self.assertEqual(res[0]["verdict"], "skip")


class RunTest(unittest.TestCase):
    def run_watch(self, tmp, critic, old=None):
        snap = Path(tmp) / "snap.json"
        if old is not None:
            W.save_snapshot(snap, old, now="2026-11-19T10:00:00")
        return W.run_watch(fake_sources(), critic, snap, Path(tmp) / "report.md", known_services=["groq"],
                           now="2026-11-20T10:00:00")

    def test_first_run_only_saves_a_baseline(self):
        with tempfile.TemporaryDirectory() as t:
            r = self.run_watch(t, critic=lambda p: "[]")
            self.assertEqual(r.new_count, 0)
            self.assertTrue((Path(t) / "snap.json").exists())
            self.assertIn("broken", r.errors)

    def test_second_run_asks_critic_and_writes_a_human_report(self):
        with tempfile.TemporaryDirectory() as t:
            calls = []
            def critic(prompt):
                calls.append(prompt)
                return '[{"id":"meta/llama-9:free","verdict":"add","why":"free, 128K context"}]'
            r = self.run_watch(t, critic, old={"openrouter": [{"id": "acme/pro-1"}], "freellmapi": [{"id": "auto"}]})
            self.assertEqual(r.new_count, 1)
            self.assertEqual(len(calls), 1)
            rep = (Path(t) / "report.md").read_text(encoding="utf-8")
            self.assertIn("meta/llama-9:free", rep)
            self.assertIn("add", rep)
            self.assertEqual(r.proposals[0]["verdict"], "add")

    def test_critic_failure_still_reports_new_models_without_verdicts(self):
        with tempfile.TemporaryDirectory() as t:
            def critic(prompt): raise RuntimeError("router down")
            r = self.run_watch(t, critic, old={"openrouter": [], "freellmapi": []})
            self.assertEqual(r.new_count, 3)
            self.assertTrue(all(p["verdict"] == "watch" for p in r.proposals))
            self.assertIn("critic", " ".join(r.errors).lower())

    def test_nothing_new_means_no_critic_call_and_no_keys_touched(self):
        with tempfile.TemporaryDirectory() as t:
            def critic(prompt): self.fail("must not be called")
            r = self.run_watch(t, critic, old={"openrouter": [{"id": "meta/llama-9:free"}, {"id": "acme/pro-1"}],
                                               "freellmapi": [{"id": "auto"}]})
            self.assertEqual(r.new_count, 0)

    def test_report_is_in_ukrainian_headings(self):
        with tempfile.TemporaryDirectory() as t:
            self.run_watch(t, lambda p: "[]", old={"openrouter": [], "freellmapi": []})
            rep = (Path(t) / "report.md").read_text(encoding="utf-8")
            self.assertIn("Нові моделі", rep)


class SourcesTest(unittest.TestCase):
    def test_parse_openrouter_marks_free_and_keeps_ctx(self):
        data = {"data": [{"id": "a/b:free", "name": "B", "context_length": 8000, "pricing": {"prompt": "0", "completion": "0"}},
                         {"id": "c/d", "name": "D", "context_length": 4000, "pricing": {"prompt": "0.000001", "completion": "0.000002"}}]}
        out = W.parse_openrouter(data)
        self.assertEqual([(m["id"], m["free"], m["ctx"]) for m in out], [("a/b:free", True, 8000), ("c/d", False, 4000)])

    def test_parse_openai_style_list(self):
        out = W.parse_openai_list({"data": [{"id": "auto"}, {"id": "x"}, {"nope": 1}]})
        self.assertEqual([m["id"] for m in out], ["auto", "x"])

    def test_default_sources_names(self):
        self.assertEqual(set(W.default_sources(lambda url: {"data": []})), {"openrouter", "freellmapi"})


if __name__ == "__main__":
    unittest.main()
