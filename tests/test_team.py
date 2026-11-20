"""Spec: team work. A big task is split into parts; each part goes to a group of up to three DIFFERENT models
(free first); parts run in parallel; results are merged and the whole test-suite runs once.
Специфікація: командна робота. Велике завдання ділиться на частини; кожну веде група з до трьох РІЗНИХ моделей
(безкоштовні першими); частини йдуть паралельно; результати зливаються й усі тести запускаються разом."""
import threading
import time
import unittest

from dante import team as T

FREE = [{"name": "groq", "paid": False}, {"name": "gemini", "paid": False}, {"name": "nemotron", "paid": False},
        {"name": "glm", "paid": False}, {"name": "claude", "paid": True}]


class AssignTest(unittest.TestCase):
    def parts(self, n):
        return [T.Part(id=f"p{i}", task=f"t{i}", files=(f"f{i}.py",)) for i in range(n)]

    def test_never_uses_paid_models_unless_allowed(self):
        a = T.assign(self.parts(2), FREE, group_size=3)
        used = {m for g in a.values() for m in g}
        self.assertNotIn("claude", used)

    def test_group_has_distinct_models_and_at_most_group_size(self):
        a = T.assign(self.parts(2), FREE, group_size=3)
        for g in a.values():
            self.assertEqual(len(g), len(set(g)))
            self.assertLessEqual(len(g), 3)
            self.assertGreaterEqual(len(g), 1)

    def test_groups_are_rotated_so_parts_start_with_different_models(self):
        a = T.assign(self.parts(3), FREE, group_size=3)
        leaders = [g[0] for g in a.values()]
        self.assertEqual(len(set(leaders)), 3)

    def test_fewer_models_than_group_size(self):
        a = T.assign(self.parts(2), FREE[:2], group_size=3)
        self.assertTrue(all(len(g) == 2 for g in a.values()))

    def test_paid_allowed_puts_paid_last(self):
        a = T.assign(self.parts(1), FREE, group_size=5, allow_paid=True)
        g = a["p0"]
        self.assertEqual(g[-1], "claude")

    def test_no_models_is_an_error(self):
        with self.assertRaises(ValueError):
            T.assign(self.parts(1), [], group_size=3)


class PlanTest(unittest.TestCase):
    def test_parts_touching_the_same_file_are_merged_into_one(self):
        parts = [T.Part("a", "x", ("m.py", "u.py")), T.Part("b", "y", ("u.py",)), T.Part("c", "z", ("k.py",))]
        out = T.split_conflicts(parts)
        self.assertEqual(len(out), 2)
        merged = next(p for p in out if "m.py" in p.files)
        self.assertEqual(set(merged.files), {"m.py", "u.py"})
        self.assertIn("x", merged.task)
        self.assertIn("y", merged.task)

    def test_independent_parts_stay_separate(self):
        parts = [T.Part("a", "x", ("a.py",)), T.Part("b", "y", ("b.py",))]
        self.assertEqual(len(T.split_conflicts(parts)), 2)


class RunTest(unittest.TestCase):
    def test_parts_run_in_parallel_and_results_are_collected(self):
        started = []
        lock = threading.Lock()

        def worker(part, group):
            with lock:
                started.append(part.id)
            time.sleep(0.3)
            return T.PartResult(part.id, True, list(part.files), group[0])

        parts = [T.Part(f"p{i}", "t", (f"f{i}.py",)) for i in range(3)]
        t0 = time.time()
        res = T.run_parts(parts, {p.id: ["groq", "gemini"] for p in parts}, worker, max_parallel=3)
        self.assertLess(time.time() - t0, 0.8)           # parallel, not 0.9 s
        self.assertEqual(sorted(r.part_id for r in res), ["p0", "p1", "p2"])
        self.assertTrue(all(r.ok for r in res))

    def test_a_crashing_worker_becomes_a_failed_result(self):
        def worker(part, group):
            raise RuntimeError("boom")
        res = T.run_parts([T.Part("p", "t", ("f.py",))], {"p": ["groq"]}, worker)
        self.assertFalse(res[0].ok)
        self.assertIn("boom", res[0].error)

    def test_max_parallel_is_respected(self):
        cur = [0]; peak = [0]; lock = threading.Lock()

        def worker(part, group):
            with lock:
                cur[0] += 1; peak[0] = max(peak[0], cur[0])
            time.sleep(0.15)
            with lock:
                cur[0] -= 1
            return T.PartResult(part.id, True, [], group[0])

        parts = [T.Part(f"p{i}", "t", (f"f{i}.py",)) for i in range(6)]
        T.run_parts(parts, {p.id: ["groq"] for p in parts}, worker, max_parallel=2)
        self.assertLessEqual(peak[0], 2)


class FinishTest(unittest.TestCase):
    def test_all_ok_runs_final_tests_once(self):
        calls = []
        out = T.finish([T.PartResult("a", True, ["a.py"], "groq"), T.PartResult("b", True, ["b.py"], "gemini")],
                       run_all_tests=lambda: calls.append(1) or True, retry_part=lambda pid: self.fail("no retry"))
        self.assertTrue(out.success)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(out.files), ["a.py", "b.py"])

    def test_failed_part_is_retried_once_through_the_academy_then_final_tests(self):
        retried = []

        def retry(pid):
            retried.append(pid)
            return T.PartResult(pid, True, ["b.py"], "academy")

        out = T.finish([T.PartResult("a", True, ["a.py"], "groq"), T.PartResult("b", False, [], "gemini", "bad")],
                       run_all_tests=lambda: True, retry_part=retry)
        self.assertEqual(retried, ["b"])
        self.assertTrue(out.success)

    def test_part_failing_twice_fails_the_team_without_final_tests(self):
        out = T.finish([T.PartResult("b", False, [], "gemini", "bad")], run_all_tests=lambda: self.fail("no"),
                       retry_part=lambda pid: T.PartResult(pid, False, [], "academy", "still bad"))
        self.assertFalse(out.success)
        self.assertIn("b", out.failed_parts)

    def test_final_tests_fail_means_team_fails(self):
        out = T.finish([T.PartResult("a", True, ["a.py"], "groq")], run_all_tests=lambda: False,
                       retry_part=lambda pid: None)
        self.assertFalse(out.success)
        self.assertEqual(out.failed_parts, [])


if __name__ == "__main__":
    unittest.main()
