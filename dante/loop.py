"""The core loop: task -> model writes files -> run tests -> fix -> repeat.

On success the changes are kept. If every attempt fails, all changes
are rolled back, so the project is never left half-broken.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from dante.audit import AuditLog
from dante.config import Settings
from dante.edits import FORMAT_INSTRUCTIONS, parse_edits
from dante.llm import LLM
from dante.runner import RunResult, run_command
from dante.workspace import Workspace

# Comments in two languages, as at international contests (author's rule, 19.11.2026)
# Коментарі двома мовами, як на міжнародних конкурсах (правило автора, 19.11.2026)
BILINGUAL_RULE = (
    "Write every comment and docstring you add in two languages: English first, then Ukrainian, "
    "e.g. `# Check the input / Перевірити вхідні дані`. Identifiers stay in English. "
)

SYSTEM_PROMPT = (
    "You are DANTE, a careful software engineer. You change a project so that "
    "the given task is done and the test command passes. "
    + BILINGUAL_RULE
    + FORMAT_INSTRUCTIONS
)

LEARN_PROMPT = (
    "You review a programming mistake that was fixed. Answer ONLY with JSON "
    '{"mistake": "...", "rule": "..."}: mistake = what went wrong in one short sentence; '
    "rule = one general rule (max 25 words) that would have prevented it in ANY project. English."
)


_ZERO = (re.compile(r"\bRan 0 tests\b"), re.compile(r"\bno tests ran\b", re.I),
         re.compile(r"collected 0 items"))
_CARGO_RESULT = re.compile(r"test result: \w+\. (\d+) passed; (\d+) failed")


def no_tests_ran(output: str) -> bool:
    """True when a test command succeeded without running a single test.
    True, якщо команда тестів «успішна», але не виконала жодного тесту."""
    if any(r.search(output) for r in _ZERO):
        return True
    results = _CARGO_RESULT.findall(output)
    return bool(results) and all(int(p) == 0 and int(f) == 0 for p, f in results)


def _lessons_for(task: str, files: list[str], path) -> tuple[str, list[str]]:
    """Lessons that fit this task, as prompt text + their ids / Уроки, що стосуються задачі."""
    if path is None:
        return "", []
    try:
        from dante import lessons as Ls
        found = Ls.relevant(Ls.load(path), task + " " + " ".join(files), k=8)
        return Ls.render(found), [x["id"] for x in found]
    except Exception:  # memory must never break a task / пам'ять не повинна ламати задачу
        return "", []


def _learn(llm, task: str, first_failure: str, path, audit) -> None:
    """After a fix, write down the rule so the mistake is not repeated / Записати правило після виправлення."""
    try:
        import json
        import re
        from dante import lessons as Ls
        resp = llm.complete(LEARN_PROMPT, f"TASK:\n{task[:1500]}\n\nFIRST ATTEMPT FAILED WITH:\n{first_failure[-2500:]}")
        m = re.search(r"\{.*\}", resp.content, re.S)
        data = json.loads(m.group(0)) if m else {}
        tags = Ls.guess_tags(task + " " + str(data.get("rule", "")), max_tags=6) or ["general"]
        lesson = Ls.add(path, str(data.get("mistake", "")), str(data.get("rule", "")), tags, source="self")
        audit.log("lesson_learned", id=lesson["id"], seen=lesson["seen"], rule=lesson["rule"])
    except Exception as e:  # never fail a task because of learning / навчання не валить задачу
        audit.log("lesson_skipped", reason=str(e)[:200])


@dataclass
class LoopResult:
    success: bool
    attempts: int
    files: list[str] = field(default_factory=list)
    last_run: RunResult | None = None
    error: str | None = None
    models: list[str] = field(default_factory=list)  # model used on each attempt
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_failed: bool = False  # True if the run ended because no model answered


def run_task(
    task: str,
    test_command: str,
    ws: Workspace,
    llm: LLM,
    settings: Settings,
    audit: AuditLog,
    context_files: list[str] | None = None,
    read_only_files: list[str] | None = None,
    lessons_path=None,
) -> LoopResult:
    """lessons_path: lessons.json — read before work, written after a fixed mistake (None = off).
    lessons_path: файл уроків — читається перед роботою, поповнюється після виправленої помилки."""
    context_files = list(context_files or [])
    touched: list[str] = []
    models: list[str] = []
    tokens = [0, 0]
    feedback = ""
    last_run: RunResult | None = None
    audit.log(
        "task_start", task=task, test_command=test_command,
        models=list(settings.order), strategy=settings.strategy,
    )

    lesson_text, lesson_ids = _lessons_for(task, context_files + list(read_only_files or []), lessons_path)
    system = SYSTEM_PROMPT + ("\n\n" + lesson_text if lesson_text else "")
    if lesson_ids:
        audit.log("lessons_used", ids=lesson_ids)
    first_failure = ""

    started = time.monotonic()
    for attempt in range(1, settings.max_fix_attempts + 1):
        if time.monotonic() - started > settings.task_time_limit_s:
            ws.rollback()
            audit.log("time_limit", attempt=attempt, limit_s=settings.task_time_limit_s)
            return LoopResult(False, attempt - 1, touched, last_run,
                              f"Time limit {settings.task_time_limit_s}s reached", models, tokens[0], tokens[1])
        prompt = f"TASK:\n{task}\n\nTEST COMMAND (must pass): {test_command}\n"
        if read_only_files:
            prompt += (
                "\nREAD-ONLY FILES (you may NOT change these; make the code satisfy them):\n"
                + ws.read_files(read_only_files, check=False) + "\n"
            )
        current = ws.read_files(sorted(set(context_files + touched)))
        if current:
            prompt += f"\nCURRENT FILES:\n{current}\n"
        if feedback:
            prompt += f"\nPREVIOUS ATTEMPT FAILED. Test output:\n{feedback}\nFix it.\n"

        try:
            resp = llm.complete(system, prompt)
        except Exception as e:  # network/key errors end the run cleanly
            ws.rollback()
            audit.log("llm_error", attempt=attempt, error=str(e))
            return LoopResult(False, attempt, touched, last_run, f"LLM error: {e}",
                              models, tokens[0], tokens[1], llm_failed=True)
        skipped = getattr(llm, "last_failures", None)
        if skipped:
            audit.log("models_skipped", attempt=attempt, reasons=[x[:200] for x in skipped])
        models.append(resp.model)
        tokens[0] += resp.prompt_tokens
        tokens[1] += resp.completion_tokens
        audit.log(
            "llm_response",
            attempt=attempt,
            model=resp.model,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            latency_s=resp.latency_s,
        )

        try:
            edits = parse_edits(resp.content)
            written = ws.apply(edits)
        except ValueError as e:  # bad format or unsafe path
            audit.log("edit_rejected", attempt=attempt, reason=str(e))
            feedback = f"Your answer was rejected: {e}"
            continue
        touched = sorted(set(touched + written))
        audit.log("files_written", attempt=attempt, files=written)

        last_run = run_command(test_command, ws.root, settings.command_timeout_s)
        audit.log(
            "test_run",
            attempt=attempt,
            exit_code=last_run.exit_code,
            duration_s=last_run.duration_s,
            output_tail=last_run.output[-2000:],
        )
        if last_run.ok and no_tests_ran(last_run.output):
            # Passing with zero tests means the new code is not connected (e.g. missing `mod`)
            # «Успіх» без жодного тесту означає, що новий код не підключено (напр. немає `mod`)
            audit.log("no_tests_ran", attempt=attempt)
            feedback = (last_run.output[-1500:] + "\n\nNO TESTS RAN: the check passed only because zero tests were "
                        "found. Connect the new code (e.g. add `pub mod x;` to src/lib.rs, or import it in the tests) "
                        "so that its tests really run.")
            first_failure = first_failure or feedback
            continue
        if last_run.ok:
            ws.commit_point()
            audit.log("task_success", attempts=attempt, files=touched)
            if attempt > 1 and lessons_path is not None and first_failure:
                _learn(llm, task, first_failure, lessons_path, audit)
            return LoopResult(True, attempt, touched, last_run, None, models, tokens[0], tokens[1])
        feedback = last_run.output
        first_failure = first_failure or feedback

    ws.rollback()
    audit.log("task_failed", attempts=settings.max_fix_attempts)
    return LoopResult(False, settings.max_fix_attempts, touched, last_run, "All attempts failed",
                      models, tokens[0], tokens[1])
