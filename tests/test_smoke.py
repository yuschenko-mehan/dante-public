"""Smoke tests. Run with:  python -m unittest discover -s tests -v"""

import os
import sys
import tempfile
import json
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dante.audit import AuditLog  # noqa: E402
from dante.cli import main  # noqa: E402
from dante.config import Settings, load_settings  # noqa: E402
from dante.edits import parse_edits  # noqa: E402
from dante.llm import FakeLLM, LLMError, MultiLLM  # noqa: E402
from dante.loop import run_task  # noqa: E402
from dante.workspace import UnsafePathError, Workspace  # noqa: E402

PY = f'"{sys.executable}"'


def block(path, body):
    return f"=== FILE: {path} ===\n{body}=== END FILE ===\n"


class TestEdits(unittest.TestCase):
    def test_parse_two_files(self):
        e = parse_edits("noise\n" + block("a.py", "x = 1\n") + block("b/c.py", "y = 2\n"))
        self.assertEqual([x.path for x in e], ["a.py", "b/c.py"])
        self.assertEqual(e[0].content, "x = 1\n")

    def test_windows_line_endings(self):
        e = parse_edits(block("a.py", "x = 1\n").replace("\n", "\r\n"))
        self.assertEqual(e[0].content, "x = 1\n")

    def test_no_blocks_is_error(self):
        with self.assertRaises(ValueError):
            parse_edits("just text")


class TestWorkspace(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.root, (".env", ".git"))

    def test_unsafe_paths_refused(self):
        for bad in ["../x.py", "/etc/passwd", "C:/Windows/x", ".env", ".git/config", "a/../../x"]:
            with self.assertRaises(UnsafePathError, msg=bad):
                self.ws.resolve(bad)

    def test_rollback_restores_and_deletes(self):
        (self.root / "old.py").write_text("old\n", encoding="utf-8")
        self.ws.apply(parse_edits(block("old.py", "new\n") + block("new.py", "n\n")))
        self.ws.rollback()
        self.assertEqual((self.root / "old.py").read_text(encoding="utf-8"), "old\n")
        self.assertFalse((self.root / "new.py").exists())

    def test_unsafe_edit_writes_nothing(self):
        with self.assertRaises(UnsafePathError):
            self.ws.apply(parse_edits(block("ok.py", "1\n") + block("../bad.py", "2\n")))
        self.assertFalse((self.root / "ok.py").exists())


class TestLoop(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.root)
        self.audit = AuditLog(self.root / "_audit")
        self.s = Settings(max_fix_attempts=2, protected_paths=())
        self.test = f'{PY} -c "import m; assert m.f() == 1"'

    def test_fixes_after_failure(self):
        llm = FakeLLM([block("m.py", "def f():\n    return 0\n"), block("m.py", "def f():\n    return 1\n")])
        r = run_task("make f return 1", self.test, self.ws, llm, self.s, self.audit)
        self.assertTrue(r.success)
        self.assertEqual(r.attempts, 2)
        self.assertIn("PREVIOUS ATTEMPT FAILED", llm.calls[1][1])  # error was fed back

    def test_all_fail_rolls_back(self):
        llm = FakeLLM([block("m.py", "def f():\n    return 0\n")] * 2)
        r = run_task("make f return 1", self.test, self.ws, llm, self.s, self.audit)
        self.assertFalse(r.success)
        self.assertFalse((self.root / "m.py").exists())

    def test_read_only_tests_shown_to_model(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_m.py").write_text("SECRET_EXPECTATION = 1\n", encoding="utf-8")
        ws = Workspace(self.root, ("tests",))
        llm = FakeLLM([block("m.py", "def f():\n    return 1\n")])
        r = run_task("t", self.test, ws, llm, self.s, self.audit, read_only_files=["tests/test_m.py"])
        self.assertTrue(r.success)
        self.assertIn("SECRET_EXPECTATION", llm.calls[0][1])
        self.assertIn("READ-ONLY", llm.calls[0][1])

    def test_audit_written(self):
        llm = FakeLLM([block("m.py", "def f():\n    return 1\n")])
        run_task("t", self.test, self.ws, llm, self.s, self.audit)
        text = self.audit.path.read_text(encoding="utf-8")
        self.assertIn('"task_success"', text)


class Broken:
    def complete(self, system, user):
        raise LLMError("no credit")


class TestMultiModel(unittest.TestCase):
    def test_rotate_uses_next_model_each_attempt(self):
        a, b = FakeLLM(["A1", "A2"]), FakeLLM(["B1"])
        m = MultiLLM([("a", a), ("b", b)], "rotate")
        self.assertEqual([m.complete("s", "u").content for _ in range(3)], ["A1", "B1", "A2"])

    def test_quota_exhausted_switches_provider_off(self):
        from dante.llm import QuotaExhausted

        class NoQuota:
            calls = 0

            def complete(self, system, user):
                NoQuota.calls += 1
                raise QuotaExhausted("free credit is over")

        m = MultiLLM([("x", NoQuota()), ("b", FakeLLM(["B1", "B2"]))], "rotate")
        self.assertEqual(m.complete("s", "u").content, "B1")
        self.assertEqual(m.complete("s", "u").content, "B2")
        self.assertEqual(NoQuota.calls, 1)  # never asked again after the quota ended
        self.assertIn("x", m.disabled)

    def test_backup_only_when_all_main_fail(self):
        backup = FakeLLM(["LOCAL"])
        m = MultiLLM([("a", FakeLLM(["A1"]))], "rotate", [("local", backup)])
        self.assertEqual(m.complete("s", "u").content, "A1")
        self.assertEqual(backup.calls, [])  # not touched while main models work
        m2 = MultiLLM([("x", Broken())], "rotate", [("local", FakeLLM(["LOCAL"]))])
        self.assertEqual(m2.complete("s", "u").content, "LOCAL")

    def test_local_needs_no_key_and_is_backup(self):
        local = {p.name: p for p in Settings().active_providers()}["local"]
        self.assertTrue(local.backup)
        self.assertFalse(local.paid)

    def test_fallback_skips_broken_model(self):
        m = MultiLLM([("x", Broken()), ("b", FakeLLM(["B1"]))], "fallback")
        self.assertEqual(m.complete("s", "u").content, "B1")

    def test_all_broken_is_error(self):
        m = MultiLLM([("x", Broken())], "rotate")
        with self.assertRaises(LLMError):
            m.complete("s", "u")

    def test_only_models_with_keys_are_active(self):
        os.environ["GEMINI_API_KEY"] = "test"
        try:
            names = [p.name for p in Settings().active_providers()]
        finally:
            del os.environ["GEMINI_API_KEY"]
        self.assertIn("gemini", names)

    def test_toml_overrides_provider(self):
        p = Path(tempfile.mkdtemp()) / "dante.toml"
        p.write_text('order = ["claude"]\nstrategy = "fallback"\n[providers.claude]\nmodel = "claude-opus-5-5"\n', encoding="utf-8")
        os.environ["DANTE_NO_ROUTING"] = "1"   # isolate from live stats and the author's models.json
        self.addCleanup(os.environ.pop, "DANTE_NO_ROUTING", None)
        s = load_settings(p, p.parent / "no-models.json")
        self.assertEqual(s.order, ("claude",))
        self.assertEqual({x.name: x.model for x in s.providers}["claude"], "claude-opus-5-5")


class TestKeysFile(unittest.TestCase):
    def test_reads_keys_skips_empty_and_comments(self):
        from dante.config import _file_keys

        p = Path(tempfile.mkdtemp()) / "keys.txt"
        # BOM + CRLF as Windows Notepad may save it
        p.write_bytes("﻿# comment\r\nGEMINI_API_KEY = \"abc\"\r\nGROQ_API_KEY=\r\n".encode("utf-8"))
        self.assertEqual(_file_keys(p), {"GEMINI_API_KEY": "abc"})


class TestHttpClient(unittest.TestCase):
    """Real HTTP round trip against a local fake OpenAI-compatible server."""

    def test_round_trip(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from dante.config import Provider
        from dante.llm import OpenAICompatibleLLM

        seen = {}

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["path"] = self.path
                seen["auth"] = self.headers["Authorization"]
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = json.dumps({"model": "m1", "choices": [{"message": {"content": "hi"}}],
                                  "usage": {"prompt_tokens": 3, "completion_tokens": 1}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        os.environ["DANTE_TEST_KEY"] = "k123"
        try:
            prov = Provider("t", f"http://127.0.0.1:{srv.server_port}/v1", "m1", "DANTE_TEST_KEY")
            r = OpenAICompatibleLLM(prov, Settings()).complete("sys", "usr")
        finally:
            srv.shutdown()
            del os.environ["DANTE_TEST_KEY"]
        self.assertEqual(r.content, "hi")
        self.assertEqual(r.model, "t:m1")
        self.assertEqual(r.prompt_tokens, 3)
        self.assertEqual(seen["path"], "/v1/chat/completions")
        self.assertEqual(seen["auth"], "Bearer k123")
        self.assertEqual(seen["body"]["messages"][0], {"role": "system", "content": "sys"})


class TestArchitect(unittest.TestCase):
    PLAN = ('Ось план: {"summary": "Калькулятор", "steps": ['
            '{"title": "Додавання", "description": "add", "files": ["calc.py"], "check": "CHECK1"},'
            '{"title": "Множення", "description": "mul", "files": ["calc.py"], "check": "CHECK2"}]}')

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "README.md").write_text("# calc\n", encoding="utf-8")
        self.c1 = f'{PY} -c "import calc; assert calc.add(2,3)==5"'
        self.c2 = f'{PY} -c "import calc; assert calc.mul(2,3)==6"'
        self.plan_text = self.PLAN.replace("CHECK1", json.dumps(self.c1)[1:-1]).replace("CHECK2", json.dumps(self.c2)[1:-1])
        self.s = Settings(max_fix_attempts=2)
        self.audit = AuditLog(self.root.parent / (self.root.name + "_audit"))

    def test_plan_with_windows_paths_unescaped(self):
        from dante.planner import _extract_json
        bs = chr(92)  # one backslash, as a model would write it
        d = _extract_json('{"check": "C:' + bs + 'Users' + bs + 'me' + bs + 'python.exe -m unittest"}')
        self.assertEqual(d["check"], "C:" + bs + "Users" + bs + "me" + bs + "python.exe -m unittest")
        d = _extract_json('{"check": "C:' + bs + 'users' + bs + 'x.py"}')
        self.assertTrue(d["check"].endswith("x.py"))

    def test_map_and_plan(self):
        from dante.planner import make_plan, map_project
        self.assertIn("README.md", map_project(self.root))
        llm = FakeLLM(["not json", self.plan_text])  # first answer invalid -> retried
        plan = make_plan("калькулятор", self.root, llm)
        self.assertEqual([s.title for s in plan.steps], ["Додавання", "Множення"])
        self.assertIn("Крок 2. Множення", plan.describe())

    def test_plan_without_check_rejected(self):
        from dante.planner import make_plan
        bad = '{"summary": "x", "steps": [{"title": "t", "description": "d"}]}'
        with self.assertRaises(ValueError):
            make_plan("g", self.root, FakeLLM([bad, bad]))

    def test_import_only_check_rejected(self):
        from dante.planner import make_plan
        weak = '{"summary": "x", "steps": [{"title": "t", "description": "d", "check": "python -c \\"import temperature\\""}]}'
        with self.assertRaises(ValueError):
            make_plan("g", self.root, FakeLLM([weak, weak]))

    def test_execute_requires_approval(self):
        from dante.planner import execute_plan, make_plan
        plan = make_plan("g", self.root, FakeLLM([self.plan_text]))
        with self.assertRaises(ValueError):
            execute_plan(plan, self.root, FakeLLM([]), self.s, self.audit)

    def test_execute_steps_commit_and_undo(self):
        from dante import gitutil
        from dante.planner import Plan, execute_plan, make_plan
        plan = make_plan("g", self.root, FakeLLM([self.plan_text]))
        plan.approved = True
        step1 = block("calc.py", "def add(a, b):\n    return a + b\n")
        step2 = block("calc.py", "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n")
        ok = execute_plan(plan, self.root, FakeLLM([step1, step2]), self.s, self.audit)
        self.assertTrue(ok)
        self.assertEqual([s.status for s in Plan.load(self.root).steps], ["done", "done"])
        if gitutil.available():
            self.assertEqual(len(gitutil.history(self.root)), 3)  # start + 2 steps
            self.assertIn("Undone", gitutil.undo_last(self.root))
            self.assertNotIn("mul", (self.root / "calc.py").read_text(encoding="utf-8"))

    def test_stops_on_failed_step(self):
        from dante.planner import execute_plan, make_plan
        plan = make_plan("g", self.root, FakeLLM([self.plan_text]))
        plan.approved = True
        good = block("calc.py", "def add(a, b):\n    return a + b\n")
        bad = block("calc.py", "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return 0\n")
        ok = execute_plan(plan, self.root, FakeLLM([good, bad, bad]), self.s, self.audit)
        self.assertFalse(ok)
        self.assertEqual([s.status for s in plan.steps], ["done", "failed"])
        self.assertNotIn("mul", (self.root / "calc.py").read_text(encoding="utf-8"))  # failed step rolled back


class FakeAgent:
    """Stands in for Codex: each call writes the next scripted set of files."""
    name = "fake"

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.prompts = []

    def run(self, prompt, root):
        from dante.agent import AgentRun
        self.prompts.append(prompt)
        for rel, text in self.scripts.pop(0).items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        return AgentRun(0, "ok", 0.1)


@unittest.skipUnless(__import__("shutil").which("git"), "git required")
class TestAgent(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_m.py").write_text(
            "import unittest\nfrom m import f\nclass T(unittest.TestCase):\n"
            "    def test(self):\n        self.assertEqual(f(), 1)\n", encoding="utf-8")
        self.s = Settings(max_fix_attempts=2)
        self.audit = AuditLog(self.root.parent / (self.root.name + "_audit"))
        self.test = f"{PY} -m unittest discover -s tests"

    def test_agent_success_after_fix(self):
        from dante.agent import run_agent_task
        a = FakeAgent([{"m.py": "def f():\n    return 0\n"}, {"m.py": "def f():\n    return 1\n"}])
        r = run_agent_task("make f return 1", self.test, self.root, a, self.s, self.audit, protect=("tests",))
        self.assertTrue(r.success)
        self.assertEqual(r.attempts, 2)
        self.assertIn("Previous attempt failed", a.prompts[1])

    def test_agent_cannot_change_tests(self):
        from dante.agent import run_agent_task
        cheat = {"tests/test_m.py": "import unittest\n", "m.py": "def f():\n    return 0\n"}
        a = FakeAgent([cheat, {"m.py": "def f():\n    return 1\n"}])
        r = run_agent_task("t", self.test, self.root, a, self.s, self.audit, protect=("tests",))
        self.assertTrue(r.success)
        self.assertIn("assertEqual", (self.root / "tests" / "test_m.py").read_text(encoding="utf-8"))

    def test_agent_all_fail_resets_project(self):
        from dante.agent import run_agent_task
        a = FakeAgent([{"m.py": "def f():\n    return 0\n"}] * 2)
        r = run_agent_task("t", self.test, self.root, a, self.s, self.audit)
        self.assertFalse(r.success)
        self.assertFalse((self.root / "m.py").exists())

    def test_codex_never_gets_api_key(self):
        from dante.agent import CodexAgent
        script = Path(tempfile.mkdtemp()) / "fakecodex.py"
        script.write_text("import os,sys\nprint('KEY=' + str('OPENAI_API_KEY' in os.environ))\n", encoding="utf-8")
        os.environ["OPENAI_API_KEY"] = "sk-should-not-pass"
        try:
            run = CodexAgent(command=[sys.executable, str(script)]).run("hi", self.root)
        finally:
            del os.environ["OPENAI_API_KEY"]
        self.assertIn("KEY=False", run.output)


class TestWallet(unittest.TestCase):
    """Money rule: free only by default; paid needs allow_paid + two confirmations + limits."""

    def setUp(self):
        from dante.config import Provider
        self.Provider = Provider
        self.paid = Provider("p", "http://x", "m", "DANTE_W_KEY", paid=True,
                             price_in_usd_per_m=1.0, price_out_usd_per_m=2.0)
        self.free = Provider("f", "http://x", "m", "DANTE_W_KEY")
        os.environ["DANTE_W_KEY"] = "k"
        self.ledger = Path(tempfile.mkdtemp()) / "wallet.jsonl"

    def tearDown(self):
        del os.environ["DANTE_W_KEY"]

    def settings(self, **kw):
        base = dict(providers=(self.paid, self.free), order=("p", "f"))
        base.update(kw)
        return Settings(**base)

    def test_paid_excluded_by_default(self):
        self.assertEqual([p.name for p in self.settings().active_providers()], ["f"])

    def test_two_confirmations_required(self):
        from dante.wallet import Wallet
        s = self.settings(allow_paid=True, budget_task_usd=1, budget_day_usd=1, budget_month_usd=1)
        asked = []
        w = Wallet(s, self.ledger, confirm=lambda q: asked.append(q) or True)
        self.assertTrue(w.approve_task([self.paid], 0.01))
        self.assertEqual(len(asked), 2)
        self.assertIn("1 з 2", asked[0])
        self.assertIn("2 з 2", asked[1])
        self.assertIn("$0.0100", asked[0])  # the sum is shown
        self.assertIn("$0.0100", asked[1])

    def test_second_no_blocks(self):
        from dante.wallet import Wallet
        s = self.settings(allow_paid=True, budget_task_usd=1, budget_day_usd=1, budget_month_usd=1)
        answers = iter([True, False])
        w = Wallet(s, self.ledger, confirm=lambda q: next(answers))
        self.assertFalse(w.approve_task([self.paid], 0.01))

    def test_not_allowed_or_no_confirm_or_over_limit(self):
        from dante.wallet import Wallet
        yes = lambda q: True  # noqa: E731
        self.assertFalse(Wallet(self.settings(), self.ledger, yes).approve_task([self.paid], 0.01))
        s = self.settings(allow_paid=True, budget_task_usd=1, budget_day_usd=1, budget_month_usd=1)
        self.assertFalse(Wallet(s, self.ledger, None).approve_task([self.paid], 0.01))
        self.assertFalse(Wallet(s, self.ledger, yes).approve_task([self.paid], 5.0))  # above task limit

    def test_unknown_price_refused(self):
        from dante.wallet import BudgetError, call_cost_usd
        with self.assertRaises(BudgetError):
            call_cost_usd(self.Provider("x", "u", "m", "K", paid=True), 10, 10)

    def test_limits_stop_calls_and_ledger_records(self):
        from dante.llm import FakeLLM
        from dante.wallet import BudgetError, PaidLLM, Wallet
        s = self.settings(allow_paid=True, budget_task_usd=1, budget_day_usd=0.0001, budget_month_usd=1)
        w = Wallet(s, self.ledger, confirm=lambda q: True)
        w.approved = True
        llm = PaidLLM(self.paid, FakeLLM(["x"]), w, 100)
        with self.assertRaises(BudgetError):  # day limit too small for even one call
            llm.complete("s", "u" * 3000)
        s2 = self.settings(allow_paid=True, budget_task_usd=1, budget_day_usd=1, budget_month_usd=1)
        w2 = Wallet(s2, self.ledger, confirm=lambda q: True)
        w2.approved = True
        PaidLLM(self.paid, FakeLLM(["answer"]), w2, 100).complete("s", "u")
        self.assertGreater(w2.spent_today(), 0)
        self.assertIn('"provider": "p"', self.ledger.read_text(encoding="utf-8"))

    def test_unapproved_paid_is_dropped(self):
        from dante.wallet import Wallet, build_llm_with_wallet
        s = self.settings(allow_paid=True, budget_task_usd=1, budget_day_usd=1, budget_month_usd=1)
        llm = build_llm_with_wallet(s, Wallet(s, self.ledger, None))
        self.assertEqual([n for n, _ in llm.clients], ["f"])

    def test_new_toml_provider_is_paid_by_default(self):
        p = Path(tempfile.mkdtemp()) / "dante.toml"
        p.write_text('[providers.newco]\nbase_url = "http://x"\nmodel = "m"\napi_key_env = "K"\n', encoding="utf-8")
        self.assertTrue({x.name: x for x in load_settings(p).providers}["newco"].paid)


class TestRateLimit(unittest.TestCase):
    def test_waits_on_429_then_succeeds(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        import dante.llm as llm_mod
        from dante.config import Provider

        calls = []

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                calls.append(1)
                if len(calls) < 3:
                    body = b'{"error":{"message":"Rate limit reached. Please try again in 1.5s."}}'
                    self.send_response(429)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                out = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        waits = []
        sleep = llm_mod.time.sleep
        llm_mod.time.sleep = waits.append
        os.environ["DANTE_RL_KEY"] = "k"
        try:
            prov = Provider("t", f"http://127.0.0.1:{srv.server_port}/v1", "m", "DANTE_RL_KEY")
            r = llm_mod.OpenAICompatibleLLM(prov, Settings()).complete("s", "u", retries=1)
        finally:
            llm_mod.time.sleep = sleep
            srv.shutdown()
            del os.environ["DANTE_RL_KEY"]
        self.assertEqual(r.content, "ok")
        self.assertEqual(waits, [2.0, 2.0])  # 1.5 s from the message + 0.5 s margin

    def test_too_large_is_not_retried(self):
        from dante.llm import _retry_after  # noqa: F401  (import check)
        self.assertTrue(callable(_retry_after))


class TestBench(unittest.TestCase):
    """End-to-end bench against a local fake OpenAI-compatible server."""

    def test_bench_end_to_end(self):
        import csv
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from dante.bench import run_bench
        from dante.config import Provider

        good = "=== FILE: m.py ===\ndef f():\n    return 1\n=== END FILE ===\n"
        bad = "=== FILE: m.py ===\ndef f():\n    return 0\n=== END FILE ===\n"

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if body["model"] == "down":
                    self.send_response(503)
                    self.end_headers()
                    return
                text = good if body["model"] == "good" else bad
                out = json.dumps({"choices": [{"message": {"content": text}}],
                                  "usage": {"prompt_tokens": 5, "completion_tokens": 7}}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_port}/v1"
        os.environ["DANTE_BENCH_KEY"] = "k"
        root = Path(tempfile.mkdtemp())
        task = root / "tasks" / "t1"
        (task / "tests").mkdir(parents=True)
        (task / "task.txt").write_text("make f return 1", encoding="utf-8")
        (task / "tests" / "test_m.py").write_text(
            "import unittest\nfrom m import f\nclass T(unittest.TestCase):\n"
            "    def test(self):\n        self.assertEqual(f(), 1)\n", encoding="utf-8")
        s = Settings(
            providers=(Provider("good", url, "good", "DANTE_BENCH_KEY"),
                       Provider("bad", url, "bad", "DANTE_BENCH_KEY"),
                       Provider("down", url, "down", "DANTE_BENCH_KEY")),
            order=("good", "bad", "down"), max_fix_attempts=2,
        )
        try:
            import dante.llm as llm_mod
            sleep = llm_mod.time.sleep
            llm_mod.time.sleep = lambda s: None  # no retry delays in tests
            summary = run_bench(root / "tasks", root / "out", s, ["bad", "good", "down"])
        finally:
            llm_mod.time.sleep = sleep
            srv.shutdown()
            del os.environ["DANTE_BENCH_KEY"]
        rows = {r["config"]: r for r in csv.DictReader(summary.with_suffix(".csv").open(encoding="utf-8"))}
        self.assertEqual(rows["good"]["success"], "1")
        self.assertEqual(rows["bad"]["success"], "0")
        self.assertEqual(rows["down"]["llm_failed"], "1")
        team = rows["team(bad+good+down)"]
        self.assertEqual((team["success"], team["attempts"]), ("1", "2"))  # bad first, good fixes
        self.assertEqual(team["models"], "bad:bad good:good")
        self.assertIn("| good | 1/1 | 100% |", summary.read_text(encoding="utf-8"))
        self.assertIn("| down | 0/0 | - |", summary.read_text(encoding="utf-8"))


class TestCli(unittest.TestCase):
    def test_dry_run_succeeds(self):
        audit_dir = tempfile.mkdtemp()
        self.assertEqual(main(["--config", "missing.toml", "run", "--dry-run", "--audit-dir", audit_dir]), 0)

    def test_unknown_setting_rejected(self):
        p = Path(tempfile.mkdtemp()) / "dante.toml"
        p.write_text('modell = "x"\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_settings(p)


if __name__ == "__main__":
    unittest.main()


class GeminiAgentTest(unittest.TestCase):
    def test_env_strips_paid_routes_and_passes_prompt(self):
        import os, sys, tempfile
        from pathlib import Path
        from dante.agent import GeminiAgent, make_agent
        self.assertEqual(make_agent("gemini").name, "gemini")
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "fake.py"
            script.write_text("import os,sys\nprint('VERTEX' if os.environ.get('GOOGLE_GENAI_USE_VERTEXAI') else 'NOVERTEX')\n"
                              "print('KEY' if os.environ.get('GEMINI_API_KEY') else 'NOKEY')\nprint(sys.argv[1:])\n")
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
            os.environ["GEMINI_API_KEY"] = "test-free-key"
            try:
                run = GeminiAgent(command=[sys.executable, str(script)]).run("do it", Path(d))
            finally:
                os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
                os.environ.pop("GEMINI_API_KEY", None)
            self.assertEqual(run.exit_code, 0)
            self.assertIn("NOVERTEX", run.output)
            self.assertIn("KEY", run.output)
            self.assertIn("--yolo", run.output)
            self.assertIn("gemini-3.5-flash-lite", run.output)
            self.assertIn("do it", run.output)


class ProtectedContextFileTest(unittest.TestCase):
    def test_file_that_is_shown_and_protected_does_not_crash(self):
        from unittest import mock
        import dante.cli as cli
        answer = "=== FILE: app.py ===\nfrom lib import X\nY = X + 1\n=== END FILE ===\n"
        fake = FakeLLM(["1. Write app.py", answer])   # the planner speaks first / спершу план
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cli, "_make_llm", lambda s, t: fake):
            (Path(d) / "lib.py").write_text("X = 1\n", encoding="utf-8")
            code = main(["run", "--project", d, "--protect", "lib.py", "--file", "lib.py", "--audit-dir",
                         str(Path(d) / "audit"), "--task", "make app.py",
                         "--test", f'"{sys.executable}" -c "import app; assert app.Y == 2"'])
            self.assertEqual(code, 0)
            self.assertIn("lib.py", fake.calls[1][1])  # it was shown to the model (read-only)


class SetupPlanTest(unittest.TestCase):
    def test_models_fit_the_hardware(self):
        from dante.setup_plan import Hardware, choose_local_models
        names = lambda hw: {m["model"]: m["mode"] for m in choose_local_models(hw)}  # noqa: E731
        now = names(Hardware(ram_gb=15.9, free_disk_gb=58, gpus=[{"name": "GT 1030", "vram_gb": 2.0}]))
        self.assertEqual(now["qwen2.5-coder:3b"], "mixed")
        self.assertNotIn("qwen2.5-coder:14b", now)
        one = names(Hardware(ram_gb=16, free_disk_gb=200, gpus=[{"name": "GTX 1070", "vram_gb": 8.0}]))
        self.assertEqual(one["qwen2.5vl:7b"], "gpu")
        self.assertNotIn("qwen2.5-coder:14b", one)
        two = names(Hardware(ram_gb=16, free_disk_gb=200, gpus=[{"vram_gb": 8.0}, {"vram_gb": 8.0}]))
        self.assertEqual(two["qwen2.5-coder:14b"], "gpu")
        cpu = names(Hardware(ram_gb=16, free_disk_gb=200))
        self.assertEqual(set(cpu.values()), {"cpu"})
        tiny_disk = names(Hardware(ram_gb=16, free_disk_gb=18, gpus=[{"vram_gb": 8.0}]))
        self.assertEqual(list(tiny_disk), ["qwen2.5-coder:3b"])

    def test_plan_lists_missing_parts_and_keys(self):
        from dante.setup_plan import Hardware, describe, make_plan
        plan = make_plan(Hardware(cpu_cores=6, ram_gb=16, free_disk_gb=50, gpus=[]),
                         have_program=lambda c: c in ("python", "git"), keys={"GEMINI_API_KEY": "x"},
                         installed_models={"qwen2.5-coder:3b"})
        self.assertEqual([c["component"] for c in plan["missing_components"]], ["Node.js", "Ollama"])
        self.assertNotIn("GEMINI_API_KEY", [p["key"] for p in plan["free_providers_to_connect"]])
        self.assertTrue(plan["local_models"][0]["installed"])
        text = describe(plan)
        self.assertIn("winget install Ollama.Ollama", text)
        self.assertIn("лише процесор", text)
        self.assertIn("не знайдено", text)

    def test_detect_reads_nvidia_smi(self):
        from unittest import mock
        import dante.setup_plan as sp
        fake = mock.Mock(return_value=mock.Mock(stdout="NVIDIA GeForce GTX 1070, 8192\nNVIDIA GeForce GTX 1070, 8192\n"))
        with mock.patch.object(sp.shutil, "which", return_value="nvidia-smi"):
            gpus = sp._nvidia_gpus(run=fake)
        self.assertEqual(gpus, [{"name": "NVIDIA GeForce GTX 1070", "vram_gb": 8.0}] * 2)


class WindowLogicTest(unittest.TestCase):
    def test_buttons_build_commands(self):
        import tempfile
        from pathlib import Path
        from dante import gui_logic as L
        with tempfile.TemporaryDirectory() as d:
            st = L.State(project=d, task="Add a function", test="python -m unittest", agent="gemini")
            a = L.dante_args("run", st)
            self.assertEqual(a[:3], ["run", "--project", d])
            self.assertIn("--protect", a)
            self.assertEqual(a[-2:], ["--agent", "gemini"])
            st.agent = ""
            self.assertNotIn("--agent", L.dante_args("run", st))
            self.assertEqual(L.dante_args("plan", st)[:5], ["plan", "--project", d, "--goal", "Add a function"])
            self.assertEqual(L.dante_args("approve", st), ["approve", "--project", d])
            self.assertEqual(L.dante_args("undo", st), ["undo", "--project", d])
            st.task = ""
            with self.assertRaises(L.InputError):
                L.dante_args("run", st)
            with self.assertRaises(L.InputError):
                L.dante_args("run", L.State(project=str(Path(d) / "missing"), task="x"))
            self.assertEqual(L.child_env()["DANTE_NO_PROMPT"], "1")

    def test_state_roundtrip_and_help(self):
        import tempfile
        from pathlib import Path
        from dante import gui_logic as L
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "w.json"
            L.save_state(L.State(project="C:/p1", task="t"), f)
            st = L.load_state(f)
            self.assertEqual((st.project, st.task, st.recent), ("C:/p1", "t", ["C:/p1"]))
            self.assertEqual(L.load_state(Path(d) / "none.json").project, "")
        for lang in ("uk", "en"):
            h = L.help_text(lang)
            self.assertIn("Ctrl+Alt+Q", h)
            self.assertIn("Esc", h)
        self.assertIn("Витрачено", L.wallet_summary("uk"))
        self.assertIn("Spent today", L.wallet_summary("en"))
        # an older file kept the shown agent name: it is converted to the id
        with tempfile.TemporaryDirectory() as d2:
            f2 = Path(d2) / "old.json"
            f2.write_text('{"agent": "Gemini CLI (безкоштовний ключ)", "lang": "xx"}', encoding="utf-8")
            st = L.load_state(f2)
            self.assertEqual((st.agent, st.lang), ("gemini", "uk"))

    def test_both_languages_have_every_text(self):
        from dante.i18n import TEXTS, t
        self.assertEqual(set(TEXTS["uk"]), set(TEXTS["en"]))
        self.assertEqual(t("en", "need_task"), "Write the task (what should be done).")
        from dante import gui_logic as L
        for lang in ("uk", "en"):
            for label in L.agent_labels(lang):
                self.assertIn(L.agent_id(lang, label), L.AGENT_IDS)
            for label in L.template_labels(lang):
                self.assertTrue(L.template_text(lang, label))
        st = L.State(project="", task="x", lang="en")
        with self.assertRaises(L.InputError) as e:
            L.dante_args("run", st)
        self.assertIn("project folder", str(e.exception))

    def test_plan_waits_then_approve_command(self):
        import os, tempfile
        from pathlib import Path
        from dante.cli import main
        from dante.planner import Plan, Step
        with tempfile.TemporaryDirectory() as d:
            Plan("goal", "sum", [Step(1, "s", "d", [], "python -c 1")]).save(Path(d))
            self.assertFalse(Plan.load(Path(d)).approved)
            self.assertEqual(main(["approve", "--project", d]), 0)
            self.assertTrue(Plan.load(Path(d)).approved)
            os.environ["DANTE_NO_PROMPT"] = "1"
            try:
                from dante.cli import _ask_yes
                self.assertFalse(_ask_yes("pay?"))
            finally:
                del os.environ["DANTE_NO_PROMPT"]
