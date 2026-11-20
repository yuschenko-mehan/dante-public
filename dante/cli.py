"""Command line: `dante run ...` and `dante check`.

    python -m dante check
    python -m dante run --project C:\\path --task "..." --test "python -m unittest"
    python -m dante run --dry-run        (no model, no cost: built-in demo task)
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from dante import __version__, version_line
from dante.audit import AuditLog
from dante.config import LESSONS_FILE, load_settings
from dante.llm import FakeLLM, LLMError, OpenAICompatibleLLM, build_llm, list_models
from dante.loop import run_task
from dante.workspace import Workspace

_DEMO_TASK = "Create add.py with a function add(a, b) that returns a + b."
_DEMO_TEST = f'"{sys.executable}" -c "import add; assert add.add(2, 3) == 5; print(\'OK\')"'
# First answer is deliberately wrong, so the dry run shows the fix loop working.
_DEMO_ANSWERS = [
    "=== FILE: add.py ===\ndef add(a, b):\n    return a - b\n=== END FILE ===\n",
    "=== FILE: add.py ===\ndef add(a, b):\n    return a + b\n=== END FILE ===\n",
]


def _ask_yes(question: str) -> bool:
    """Ask the author in the console. Only the exact word ТАК (or YES) counts as yes."""
    if os.environ.get("DANTE_NO_PROMPT"):  # started from the window: answers come from buttons, never "yes"
        return False
    try:
        answer = input(question + "  Введіть ТАК для згоди: ")
    except EOFError:
        return False
    return answer.strip().upper() in ("ТАК", "YES")


def _make_llm(s, task_text: str):
    """All models for one task; paid ones only after the wallet's double confirmation."""
    from dante.config import KEYS_FILE
    from dante.wallet import Wallet, build_llm_with_wallet, estimate_tokens

    wallet = Wallet(s, KEYS_FILE.parent / "wallet.jsonl", confirm=_ask_yes)
    paid = [p for p in s.active_providers() if p.paid]
    if paid:
        try:
            est = wallet.estimate_task(paid, s.max_fix_attempts, estimate_tokens(task_text) + 4000, s.max_tokens)
        except LLMError as e:
            print(f"Платні моделі вимкнено: {e}")
            est = None
        if est is None or not wallet.approve_task(paid, est):
            print("Платні моделі НЕ використовуються (лише безкоштовні).")
    try:
        return build_llm_with_wallet(s, wallet)
    except LLMError as e:
        print(e)
        return None


def _cmd_plan(args: argparse.Namespace) -> int:
    from dante.planner import make_plan

    s = load_settings(Path(args.config))
    root = Path(args.project)
    if not root.is_dir():
        print(f"Project folder not found: {root}")
        return 2
    llm = _make_llm(s, args.goal)
    if llm is None:
        return 2
    try:
        plan = make_plan(args.goal, root, llm, default_check=args.check or "")
    except (ValueError, LLMError) as e:
        print(f"План не складено: {e}")
        return 1
    print(plan.describe())
    plan.approved = args.yes or _ask_yes("\nПогодити цей план?")
    path = plan.save(root)
    print(("ПЛАН ПОГОДЖЕНО. Виконати: python -m dante do --project " + str(root)) if plan.approved
          else "План чекає вашого погодження (збережено).")
    print(f"План: {path}")
    return 0 if plan.approved else 3  # 3 = plan saved, waiting for the author's approval


def _cmd_do(args: argparse.Namespace) -> int:
    from dante.planner import Plan, execute_plan

    s = load_settings(Path(args.config))
    root = Path(args.project)
    try:
        plan = Plan.load(root)
    except (OSError, ValueError) as e:
        print(f"Немає плану в {root}: {e}. Спершу: python -m dante plan ...")
        return 2
    if not plan.approved:
        print("План не погоджено. Спершу погодьте його командою plan.")
        return 2
    llm = _make_llm(s, plan.goal)
    if llm is None:
        return 2
    audit = AuditLog(Path(args.audit_dir or s.audit_dir))

    def report(step, result):
        mark = "ГОТОВО" if result.success else "НЕ ВДАЛОСЯ"
        print(f"Крок {step.id} «{step.title}»: {mark} (спроб: {result.attempts})"
              + (f", збережено {step.commit}" if step.commit else ""))
        if not result.success and result.last_run:
            print(result.last_run.output[-1200:])

    agent = None
    if args.agent:
        from dante.agent import make_agent
        agent = make_agent(args.agent)
        if not agent.available():
            print(f"Агент {args.agent} не встановлено (запустіть {args.agent}-install.bat).")
            return 2
    ok = execute_plan(plan, root, llm, s, audit, protect=tuple(args.protect), on_step=report, agent=agent)
    print("УСІ КРОКИ ВИКОНАНО." if ok else "Зупинено на кроці з помилкою. Можна змінити план або повторити: do.")
    print(f"Audit log: {audit.path}")
    return 0 if ok else 1


def _cmd_approve(args: argparse.Namespace) -> int:
    from dante.planner import Plan

    root = Path(args.project)
    try:
        plan = Plan.load(root)
    except (OSError, ValueError) as e:
        print(f"Немає плану в {root}: {e}. Спершу складіть план.")
        return 2
    plan.approved = True
    plan.save(root)
    print(plan.describe())
    print("ПЛАН ПОГОДЖЕНО. Можна виконувати.")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    from dante.gui import main as gui_main

    return gui_main()


def _cmd_undo(args: argparse.Namespace) -> int:
    from dante import gitutil

    print(gitutil.undo_last(Path(args.project)))
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    from dante import gitutil

    for line in gitutil.history(Path(args.project)) or ["(no DANTE steps yet)"]:
        print(line)
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    s = load_settings(Path(args.config))
    print(f"DANTE {__version__}")
    print(f"Python      : {sys.version.split()[0]}")
    print(f"Strategy    : {s.strategy} (order: {', '.join(s.order)})")
    by_name = {p.name: p for p in s.providers}
    for name in s.order:
        p = by_name[name]
        key = "key set" if p.api_key else f"NO KEY (set {p.api_key_env})"
        print(f"  {name:<8} {p.model:<22} {key}")
    active = s.active_providers()
    print(f"Ready models: {len(active)}" + ("" if active else "  -> set at least one API key"))
    print(f"Paid models : {'ALLOWED (with double confirmation)' if s.allow_paid else 'OFF (free only)'}")
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    """Check every key by asking its provider for the model list."""
    s = load_settings(Path(args.config))
    ok = 0
    for p in s.providers:
        if not p.api_key:
            print(f"{p.name:<10} no key ({p.api_key_env})")
            continue
        try:
            models = list_models(p)
        except LLMError as e:
            print(f"{p.name:<10} KEY ERROR: {e}")
            continue
        ok += 1
        mark = "OK" if p.model in models else f"WARNING: '{p.model}' not in list"
        print(f"{p.name:<10} key works, {len(models)} models, configured model: {mark}")
        wanted = args.filter.lower() if args.filter else None
        shown = [m for m in models if not wanted or wanted in m.lower()]
        for m in shown[: args.limit]:
            print(f"             {m}")
    print(f"Working keys: {ok}")
    return 0 if ok else 1


def _cmd_ping(args: argparse.Namespace) -> int:
    """Send a tiny request to each model and measure the answer time."""
    import dataclasses
    import time

    s = load_settings(Path(args.config))
    ok = 0
    for p in s.active_providers():
        if p.paid:
            print(f"{p.name:<10} skipped: paid model (money rule)")
            continue
        models = [p.model] + [m for m in args.model if m != p.model and p.name == args.provider]
        for model in models:
            # Extra models are tried without reasoning_effort (not all models accept it).
            prov = dataclasses.replace(p, model=model, reasoning_effort=p.reasoning_effort if model == p.model else None)
            start = time.monotonic()
            try:
                r = OpenAICompatibleLLM(prov, s).complete(
                    "Answer briefly.", "Reply with the single word OK.",
                    max_tokens=512, timeout_s=args.timeout, retries=1,
                )
                answer = r.content.strip().replace("\n", " ")[:40]
                print(f"{p.name:<10} {model:<28} {time.monotonic() - start:6.1f}s  answer: {answer!r}")
                ok += 1
            except LLMError as e:
                print(f"{p.name:<10} {model:<28} {time.monotonic() - start:6.1f}s  ERROR: {str(e)[:200]}")
    print(f"Answered: {ok}")
    return 0 if ok else 1


def _cmd_bench(args: argparse.Namespace) -> int:
    from dante.bench import run_bench

    s = load_settings(Path(args.config))
    base = Path(__file__).resolve().parents[2] / "bench"   # C:\\DANTE\\bench
    tasks = Path(args.tasks) if args.tasks else base / "tasks"
    out = Path(args.out) if args.out else base / "results"
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    try:
        path = run_bench(tasks, out, s, models, include_team=not args.no_team, repeats=args.repeats, learn=args.learn)
    except ValueError as e:
        print(e)
        return 2
    print(f"Summary: {path}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    s = load_settings(Path(args.config))

    if args.dry_run:
        root = Path(tempfile.mkdtemp(prefix="dante-dry-"))
        task, test, llm = _DEMO_TASK, _DEMO_TEST, FakeLLM(_DEMO_ANSWERS)
        print(f"[dry-run] demo project in {root} (no model is called)")
    else:
        if not (args.project and args.task and args.test):
            print("Need --project, --task and --test (or use --dry-run).")
            return 2
        root, task, test = Path(args.project), args.task, args.test
        if not root.is_dir():
            print(f"Project folder not found: {root}")
            return 2
        llm = _make_llm(s, task)
        if llm is None:
            return 2

    if getattr(args, "agent", None):
        from dante import gitutil
        from dante.agent import make_agent, run_agent_task
        agent = make_agent(args.agent)
        if not agent.available():
            print(f"Агент {args.agent} не встановлено (запустіть {args.agent}-install.bat).")
            return 2
        audit = AuditLog(Path(args.audit_dir or s.audit_dir))
        result = run_agent_task(task, test, root, agent, s, audit, protect=tuple(args.protect))
        if result.success:
            gitutil.commit(root, f"task ({agent.name}): {task[:60]}")
        print(("SUCCESS" if result.success else "FAILED") + f" after {result.attempts} attempt(s) with {agent.name}.")
        if result.error:
            print(f"Reason: {result.error}")
        print(f"Audit log: {audit.path}")
        return 0 if result.success else 1

    ws = Workspace(root, tuple(s.protected_paths) + tuple(args.protect))
    audit = AuditLog(Path(args.audit_dir or s.audit_dir))
    # Protected files inside the project are shown to the model as read-only (e.g. tests).
    read_only = []
    for prot in args.protect:
        target = root / prot
        if target.is_file():
            read_only.append(prot.replace("\\", "/"))
        elif target.is_dir():
            read_only += sorted(
                f.relative_to(root).as_posix() for f in target.rglob("*")
                if f.is_file() and f.suffix in {".py", ".txt", ".json", ".toml", ".md"}
            )[:20]
    # a file that is both shown (--file) and protected is shown once, as read-only (it must not crash)
    from dante.workspace import UnsafePathError
    context = []
    for f in args.file:
        rel = f.replace("\\", "/")
        try:
            ws.resolve(rel)
            context.append(rel)
        except UnsafePathError:
            if (root / rel).is_file() and rel not in read_only:
                read_only.append(rel)  # protected: show it, but read-only
    from dante import codemap
    map_text = codemap.context(root, task)
    from dante import gui_logic as _G
    use_critic = _G.critic_enabled() and not getattr(args, "no_critic", False)
    from dante import contest as _K, contest_run as _CR
    import datetime as _dt
    _today = _dt.date.today().isoformat()
    if (getattr(args, "contest", False) or _G.contest_enabled()) and _CR.used_today(_CR.USAGE_FILE, _today) < _K.DEFAULTS["per_day"]:
        from dataclasses import replace as _rep
        from dante.llm import build_llm as _bl
        names = [p.name for p in s.active_providers() if not p.backup][: _K.DEFAULTS["max_models"]]

        def _run_one(model, task_, test_, copy_root):
            one = _rep(s, order=(model,))
            ws1 = Workspace(copy_root, tuple(s.protected_paths) + tuple(args.protect))
            return run_task(task_, test_, ws1, _bl(one), one, audit, context_files=context, read_only_files=read_only,
                            lessons_path=LESSONS_FILE, map_text=map_text, critic=True)

        out = _CR.run_contest(task, test, root, names, _run_one)
        _CR.note_use(_CR.USAGE_FILE, _today)
        print(f"Contest / Конкурс: winner {out['winner']}")
        for m, ok, sc in out["results"]:
            print(f"  {m}: {'OK' if ok else 'FAIL'} {sc:g}")
        return 0 if out["winner"] else 1
    teacher = None
    if not getattr(args, "no_teacher", False):
        # Academy: up to 3 other models give hints after a failed attempt / Академія: до 3 інших моделей дають підказки
        from dataclasses import replace as _rp
        from dante.llm import build_llm as _bt
        names = [p.name for p in s.active_providers() if not p.backup]
        teacher = []
        for name in names[1:4]:
            try:
                teacher.append(_bt(_rp(s, order=(name,))))
            except Exception:
                pass
        teacher = teacher or None
    result = run_task(task, test, ws, llm, s, audit, context_files=context, read_only_files=read_only,
                      lessons_path=LESSONS_FILE, map_text=map_text, critic=use_critic, teacher=teacher)

    status = "SUCCESS" if result.success else "FAILED"
    print(f"{status} after {result.attempts} attempt(s). Files: {', '.join(result.files) or '-'}")
    if result.error:
        print(f"Reason: {result.error}")
    if result.critic_score is not None:
        print(f"Critic / Критик: {result.critic_score:g}/10")
        for issue in result.critic_issues:
            print(f"  - {issue}")
    if result.last_run and not result.success:
        print("Last test output:\n" + result.last_run.output[-1500:])
    print(f"Audit log: {audit.path}")
    return 0 if result.success else 1


def _cmd_perf(args) -> int:
    """How much better DANTE got / Наскільки Данте став кращим."""
    from datetime import datetime as _d
    from dante import perf
    d = Path(args.audit_dir) if args.audit_dir else Path(__file__).resolve().parents[1] / "audit"
    print(perf.report(perf.compare(perf.load_runs(d), _d.fromisoformat(args.since))))
    return 0


def _cmd_collect(args) -> int:
    """Collect code from an AI conversation into a project / Зібрати код з розмови зі ШІ у проєкт."""
    from dante import collector
    src = Path(args.src)
    if not src.is_file():
        print(f"No such file / Немає файлу: {src}")
        return 2
    root = Path(args.project).resolve()
    root.mkdir(parents=True, exist_ok=True)

    def fix(cmd):
        ns = argparse.Namespace(**vars(args))
        ns.task = f"Make the project assembled from an AI conversation pass: {cmd}. Change only what is needed."
        ns.test = cmd
        for k, v in (("file", []), ("protect", []), ("dry_run", False), ("agent", None), ("audit_dir", None), ("no_critic", False), ("contest", False)):
            if not hasattr(ns, k):
                setattr(ns, k, v)
        return _cmd_run(ns) == 0

    out = collector.assemble(src.read_text(encoding="utf-8"), root, run_fix=None if args.no_fix else fix, check=args.test)
    for f in out["files"]:
        print(f"  + {f}")
    print(f"Files / Файлів: {len(out['files'])}; check / перевірка: {out['check'] or '-'}; ok: {out['ok']}")
    return 1 if out["ok"] is False else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dante", description="DANTE — AI code builder")
    p.add_argument("--version", action="version", version=version_line())
    p.add_argument("--config", default="dante.toml", help="settings file")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="show settings and environment").set_defaults(func=_cmd_check)

    m = sub.add_parser("models", help="test API keys and list available models")
    m.add_argument("--filter", help="show only models containing this text")
    m.add_argument("--limit", type=int, default=200)
    m.set_defaults(func=_cmd_models)

    g = sub.add_parser("ping", help="send a tiny request to each model, measure time")
    g.add_argument("--provider", default="", help="provider for extra --model values")
    g.add_argument("--model", action="append", default=[], help="extra model to try (repeatable)")
    g.add_argument("--timeout", type=int, default=60)
    g.set_defaults(func=_cmd_ping)

    pl = sub.add_parser("plan", help="Architect: make a plan for a goal and ask for approval")
    pl.add_argument("--project", required=True)
    pl.add_argument("--goal", required=True, help="what you want, in plain words")
    pl.add_argument("--check", help="default check command, e.g. \"cargo test --lib\"")
    pl.add_argument("--yes", action="store_true", help="approve without asking")
    pl.set_defaults(func=_cmd_plan)

    do = sub.add_parser("do", help="Architect: execute the approved plan step by step")
    do.add_argument("--project", required=True)
    do.add_argument("--protect", action="append", default=[], help="file/folder the model may not change")
    do.add_argument("--audit-dir")
    do.add_argument("--agent", choices=["codex", "gemini"], help="let an external agent (Codex / Gemini CLI) write the code")
    do.set_defaults(func=_cmd_do)

    ap = sub.add_parser("approve", help="Architect: approve the saved plan")
    ap.add_argument("--project", required=True)
    ap.set_defaults(func=_cmd_approve)

    sub.add_parser("gui", help="open the DANTE window (buttons, hotkeys, STOP)").set_defaults(func=_cmd_gui)
    sub.add_parser("setup", help="look at this PC and show what to install / connect (free)").set_defaults(
        func=lambda a: __import__("dante.setup_plan", fromlist=["main"]).main())
    sub.add_parser("fonts", help="find / get the drafting font for the window (free)").set_defaults(
        func=lambda a: __import__("dante.fonts", fromlist=["main"]).main())
    sub.add_parser("selftest", help="check DANTE on this computer (tests + window), free").set_defaults(
        func=lambda a: __import__("dante.selftest", fromlist=["main"]).main())

    un = sub.add_parser("undo", help="undo the last DANTE step (git)")
    un.add_argument("--project", required=True)
    un.set_defaults(func=_cmd_undo)

    hi = sub.add_parser("history", help="list DANTE steps (git)")
    hi.add_argument("--project", required=True)
    hi.set_defaults(func=_cmd_history)

    b = sub.add_parser("bench", help="run every task with each model alone and as a team")
    b.add_argument("--models", default="gemini,groq,qwen-groq,nemotron", help="comma-separated model names")
    b.add_argument("--no-team", action="store_true", help="skip the team configuration")
    b.add_argument("--repeats", type=int, default=1)
    b.add_argument("--learn", action="store_true", help="use and grow the lesson memory / вчитися на помилках")
    b.add_argument("--tasks", help="tasks folder (default C:\\DANTE\\bench\\tasks)")
    b.add_argument("--out", help="results folder (default C:\\DANTE\\bench\\results)")
    b.set_defaults(func=_cmd_bench)

    pu = sub.add_parser("publish", help="publish the project to GitHub (bilingual) / викласти проєкт на GitHub")
    pu.add_argument("--project", required=True)
    pu.add_argument("--public", action="store_true", help="new repository is public (default: private)")
    pu.add_argument("--task", default="", help="what was done (for the description) / що зроблено")
    pu.add_argument("--new-ok", action="store_true", help="the author confirmed creating a new repository")
    pu.set_defaults(func=_cmd_publish)

    idl = sub.add_parser("idle", help="full PC load when nobody works (default on) / повне навантаження в простої")
    idl.add_argument("state", choices=["on", "off", "status"])
    idl.set_defaults(func=_cmd_idle)

    le = sub.add_parser("lesson", help="teach DANTE a rule after fixing its mistake / навчити Данте правилу")
    le.add_argument("--mistake", required=True, help="what went wrong / що було не так")
    le.add_argument("--rule", required=True, help="the rule that prevents it / правило, що це запобігає")
    le.add_argument("--tag", action="append", default=[], help="topic word, repeatable (e.g. json, gui, always)")
    le.set_defaults(func=_cmd_lesson)
    upd = sub.add_parser("update", help="update DANTE from GitHub releases / оновити Данте з GitHub")
    upd.add_argument("action", nargs="?", default="check", choices=["check", "install", "rollback", "auto-on", "auto-off"])
    upd.add_argument("--app-dir", default=None)
    upd.set_defaults(func=_cmd_update)
    sub.add_parser("lessons", help="show what DANTE has learned / що Данте вже вивчив").set_defaults(func=_cmd_lessons)

    r = sub.add_parser("run", help="do one task in a project")
    r.add_argument("--project", help="project folder")
    r.add_argument("--task", help="what to do, in plain words")
    r.add_argument("--test", help="command that must pass, e.g. \"python -m unittest\"")
    r.add_argument("--file", action="append", default=[], help="existing file to show the model (repeatable)")
    r.add_argument("--protect", action="append", default=[], help="file/folder the model may not change, e.g. tests (repeatable)")
    r.add_argument("--dry-run", action="store_true", help="demo run without a model")
    r.add_argument("--agent", choices=["codex", "gemini"], help="let an external agent (Codex / Gemini CLI) write the code")
    r.add_argument("--audit-dir", help="where to write the audit log")
    r.add_argument("--no-critic", action="store_true", help="switch the critic off for this run / вимкнути критика")
    r.add_argument("--no-teacher", action="store_true", help="switch the Academy off / вимкнути Академію")
    r.add_argument("--contest", action="store_true", help="several models at once, the critic picks the best / кілька моделей одразу")
    r.set_defaults(func=_cmd_run)
    c = sub.add_parser("collect", help="code from an AI conversation -> project / код з розмови зі ШІ -> проєкт")
    c.add_argument("--from", dest="src", required=True, help="conversation file (text / Markdown)")
    c.add_argument("--project", required=True, help="project folder")
    c.add_argument("--test", help="check command (default: build / compile)")
    c.add_argument("--no-fix", action="store_true", help="only write the files / лише записати файли")
    c.set_defaults(func=_cmd_collect)
    pf = sub.add_parser("perf", help="compare results before/after a moment / порівняти до і після")
    pf.add_argument("--since", required=True)
    pf.add_argument("--audit-dir")
    pf.set_defaults(func=_cmd_perf)
    return p


def _cmd_publish(args) -> int:
    """Publish to GitHub with free-model texts / Викласти на GitHub з текстами від безкоштовних моделей."""
    from dante.github_ops import publish
    s = load_settings(Path(args.config))
    try:
        llm = _make_llm(s, "github texts")
    except Exception:  # no model: plain texts / без моделі: прості тексти
        llm = None
    return publish(Path(args.project), "public" if args.public else "private", args.task, llm, new_ok=args.new_ok)


def _cmd_idle(args) -> int:
    """Turn idle-time full load on/off / Увімкнути/вимкнути повне навантаження в простої."""
    from dante import idle_policy as I
    path = Path(__file__).resolve().parents[1] / "idle.json"
    s = I.load_settings(path)
    if args.state != "status":
        s["enabled"] = args.state == "on"
        I.save_settings(path, s)
    print(("ON" if s["enabled"] else "OFF") + f" — простій від {s['idle_minutes']} хв, межа відеокарти {s['max_temp']} °C, "
          f"навчання раз на {s['train_every_minutes']} хв")
    return 0


def _cmd_lesson(args) -> int:
    """Save a reviewer's lesson / Зберегти урок від рецензента."""
    from dante import lessons as Ls
    try:
        tags = args.tag or Ls.guess_tags(args.mistake + " " + args.rule) or ["general"]
        x = Ls.add(LESSONS_FILE, args.mistake, args.rule, tags)
    except ValueError as e:
        print(f"Урок не збережено / lesson not saved: {e}")
        return 2
    print(f"{x['id']} (×{x['seen']}) [{', '.join(x['tags'])}]: {x['rule']}")
    return 0


def _cmd_update(args) -> int:
    """Update from GitHub releases (check, install, rollback, auto on/off).
    Оновлення з релізів GitHub (перевірити, встановити, відкат, авто так/ні)."""
    from pathlib import Path as _P
    import dante as D
    from dante import updater as U
    app = _P(args.app_dir) if args.app_dir else _P(D.__file__).resolve().parent.parent
    pol_path = app / "update.json"
    if args.action in ("auto-on", "auto-off"):
        pol = U.load_policy(pol_path)
        pol["auto_install"] = args.action == "auto-on"
        U.save_policy(pol_path, pol)
        print("Автовстановлення оновлень / auto install: " + ("увімкнено / on" if pol["auto_install"] else "вимкнено / off"))
        return 0
    if args.action == "rollback":
        root = app / "update-backup"
        dirs = sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else []
        if not dirs:
            print("Немає резервної копії / no backup")
            return 1
        print(f"Повернуто файлів / files restored: {U.rollback(app, dirs[-1])}")
        return 0
    res = U.run_update(app, D.__build__, install_now=args.action == "install")
    notes = {"up-to-date": "у вас найновіша версія", "offline": "немає зв'язку з GitHub",
             "bad-checksum": "файл пошкоджений або підмінений — нічого не встановлено"}
    head = res.split()[0]
    extra = notes.get(head) or ("є нова версія — встановити: python -m dante update install" if head == "available"
                                else "встановлено; відкат: python -m dante update rollback")
    print(f"{res}  ({extra})")
    return 0


def _cmd_lessons(args) -> int:
    """List learned lessons / Показати вивчені уроки."""
    from dante import lessons as Ls
    items = Ls.load(LESSONS_FILE)
    print(f"Уроків / lessons: {len(items)}")
    for x in items:
        print(f"{x['id']} {x['date']} {x['source']:<13} ×{x['seen']} [{', '.join(x['tags'])}]\n    {x['rule']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
