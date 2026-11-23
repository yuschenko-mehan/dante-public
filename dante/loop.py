"""The core loop: task -> model writes files -> run tests -> fix -> repeat.
Основний цикл: завдання -> модель пише файли -> запустити тести -> виправити -> повторити.

On success the changes are kept. If every attempt fails, all changes
are rolled back, so the project is never left half-broken.
У разі успіху зміни зберігаються. Якщо кожна спроба зазнає невдачі, всі зміни
відкочуються, тому проєкт ніколи не залишається наполовину зламаним.
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


CRITIC_SYSTEM = "You are a strict code reviewer. Answer ONLY with JSON."


def _review(llm, task, ws, touched, audit, res) -> None:
    """Critic: score the passing solution / Критик: оцінити рішення, що пройшло тести."""
    from dante import critic as C
    try:
        parts = []
        for p in touched:
            f = ws.resolve(p)
            if f.exists():
                parts.append(f"=== {p} ===\n" + f.read_text(encoding="utf-8", errors="replace"))
        code = "\n".join(parts)
        if len(code) > 24000:   # show the end of every file too: keep head and tail / показати і кінець файлу
            code = code[:16000] + "\n... [middle skipped for length / середину пропущено] ...\n" + code[-8000:]
        note = ("\nNOTE: the tests already PASS. Judge quality only; a skipped middle is a display limit, not missing code.\n")
        resp = llm.complete(CRITIC_SYSTEM, C.critic_prompt(task + note, code))
        review = C.parse_critic(resp.content)
        res.critic_score, res.critic_issues = review["score"], review["issues"]
        audit.log("critic", score=res.critic_score, issues=res.critic_issues)
    except Exception:
        res.critic_score, res.critic_issues = None, []


TEACHER_SYSTEM = ("You are a teacher in the academy of a coding assistant. Find the ROOT CAUSE of the failure and give "
                  "ONE precise, concrete hint for the next attempt. At most 5 lines. No code blocks.")


def teacher_prompt(task: str, code: str, error: str) -> str:
    """Prompt for a teacher model / Запит до моделі-вчителя."""
    return (f"TASK:\n{task[:1500]}\n\nCURRENT CODE:\n{code[:6000]}\n\nTEST OUTPUT (end):\n{error[-3000:]}\n\n"
            "Explain the root cause in 1-2 lines, then give one precise hint to fix it.")


def lesson_prompt(task: str) -> str:
    return ("Give a short LESSON for this coding mission before it starts: the approach, common pitfalls, "
            "and what the tests will check. At most 10 lines.\n\nMISSION:\n" + task)


def _lesson(teachers, task: str) -> str:
    try:
        return (teachers[0].complete(TEACHER_SYSTEM, lesson_prompt(task)).content or "").strip()[:1500]
    except Exception:
        return ""


def _academy(teachers, task: str, code: str, error: str) -> list[str]:
    """Ask up to 3 teachers in parallel; failed or empty answers are skipped.
    Спитати до 3 учителів паралельно; невдалі чи порожні відповіді пропускаються."""
    import threading
    prompt = teacher_prompt(task, code, error)
    out: list[str | None] = [None] * len(teachers)

    def ask(i, t):
        try:
            out[i] = (t.complete(TEACHER_SYSTEM, prompt).content or "").strip()[:1500] or None
        except Exception:
            out[i] = None

    threads = [threading.Thread(target=ask, args=(i, t), daemon=True) for i, t in enumerate(teachers)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=180)
    return [h for h in out if h]


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
    critic_score: float | None = None
    critic_issues: list[str] = field(default_factory=list)


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
    map_text: str = "",
    teacher=None,
    critic: bool = False,
) -> LoopResult:
    """lessons_path: lessons.json — read before work, written after a fixed mistake (None = off).
    lessons_path: файл уроків — читається перед роботою, поповнюється після виправленої помилки."""
    context_files = list(context_files or [])
    touched: list[str] = []
    models: list[str] = []
    tokens = [0, 0]
    feedback = ""
    hints: list[str] = []
    teachers = ([] if teacher is None else list(teacher) if isinstance(teacher, (list, tuple)) else [teacher])[:3]
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
    lesson = _lesson(teachers, task) if teachers and settings.academy_briefing else ""
    plan_text = ""
    if settings.planner_always:
        from dante import mission_plan as MP
        mp = MP.get_or_make(ws.root, task, lambda q: llm.complete(TEACHER_SYSTEM, q).content)
        if mp:
            plan_text = MP.render(mp)
            audit.log("mission_plan", steps=mp.steps)
    if lesson:
        audit.log("academy_lesson", lesson=lesson)

    started = time.monotonic()
    for attempt in range(1, settings.max_fix_attempts + 1):
        if time.monotonic() - started > settings.task_time_limit_s:
            ws.rollback()
            audit.log("time_limit", attempt=attempt, limit_s=settings.task_time_limit_s)
            return LoopResult(False, attempt - 1, touched, last_run,
                              f"Time limit {settings.task_time_limit_s}s reached", models, tokens[0], tokens[1])
        prompt = f"TASK:\n{task}\n\nTEST COMMAND (must pass): {test_command}\n"
        if lesson:
            prompt += f"\nACADEMY LESSON:\n{lesson}\n"
        if plan_text:
            prompt += f"\n{plan_text}\n"
        if map_text:
            prompt += f"\n{map_text}\n"
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
        if hints:
            prompt += "\nACADEMY HINTS (from other models):\n" + "\n".join(f"{i}) {h}" for i, h in enumerate(hints, 1)) + "\n"

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
            edits = parse_edits(resp.content, read=lambda p: ws.resolve(p).read_text(encoding="utf-8") if ws.resolve(p).exists() else None)
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
            res = LoopResult(True, attempt, touched, last_run, None, models, tokens[0], tokens[1])
            if critic:
                _review(llm, task, ws, touched, audit, res)
            return res
        feedback = last_run.output
        first_failure = first_failure or feedback
        hints = []
        if teachers and attempt >= settings.solo_attempts and attempt < settings.max_fix_attempts:
            code = "\n".join(f"=== {p} ===\n" + ws.resolve(p).read_text(encoding="utf-8", errors="replace")
                             for p in touched if ws.resolve(p).exists())
            hints = _academy(teachers, task, code, feedback)
            audit.log("academy_hints", attempt=attempt, hints=hints)

    ws.rollback()
    audit.log("task_failed", attempts=settings.max_fix_attempts)
    return LoopResult(False, settings.max_fix_attempts, touched, last_run, "All attempts failed",
                      models, tokens[0], tokens[1])



def run_mission(task, test_command, ws, llm, settings, audit, step_check=None, **kw):
    """Planner always on: short plans go inline, long plans run STEP BY STEP; progress is saved, so after a restart
    the mission continues from the first unfinished step.
    Планувальник: короткий план — у запиті, довгий — покроково; прогрес зберігається і після перезапуску продовжується."""
    import dataclasses
    import sys as _sys
    from dante import mission_plan as MP

    # Pop critic flag from kwargs / Витягнути прапорець critic з аргументів
    want_critic = bool(kw.pop('critic', False))

    if not settings.planner_always:
        res = run_task(task, test_command, ws, llm, settings, audit, critic=want_critic, **kw)
        return res

    plan = MP.get_or_make(ws.root, task, lambda q: llm.complete(TEACHER_SYSTEM, q).content)
    if plan is None or len(plan.steps) <= settings.plan_inline_steps:
        res = run_task(task, test_command, ws, llm, settings, audit, critic=want_critic, **kw)
        return res

    sub = dataclasses.replace(settings, planner_always=False)
    # every step must at least compile (force: ignore cached .pyc) / кожен крок має хоча б компілюватися
    check = step_check or (f'"{_sys.executable}" -c "import compileall,sys; '
                           f'sys.exit(0 if compileall.compile_dir(\'.\', quiet=1, force=True) else 1)"')
    result = None
    collected_files = []

    while plan.done < len(plan.steps):
        last = plan.done == len(plan.steps) - 1
        audit.log("mission_step", step=plan.done + 1, total=len(plan.steps))
        
        # Call run_task with critic=False / Викликати run_task з critic=False
        result = run_task(MP.step_task(plan) + "\n\n" + MP.render(plan), test_command if last else check,
                          ws, llm, sub, audit, critic=False, **kw)
        
        if not result.success:
            return result

        # Collect all files of all steps / Збрати всі файли всіх кроків
        for f in result.files:
            if f not in collected_files:
                collected_files.append(f)
        result.files = list(collected_files)

        plan.done += 1
        MP.save(ws.root, plan)

        # After a successful step that is NOT the last, run the REAL test command / Після успішного кроку (не останнього) запустити справжні тести
        if not last:
            real_run = run_command(test_command, ws.root, settings.command_timeout_s)
            if real_run.ok and not no_tests_ran(real_run.output):
                audit.log('mission_early_done', step=plan.done, total=len(plan.steps))
                plan.done = len(plan.steps)
                MP.save(ws.root, plan)
                break

    if result and result.success:
        result.files = list(collected_files)
        if want_critic:
            _review(llm, task, ws, result.files, audit, result)

    return result
