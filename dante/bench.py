"""Benchmark: every task x every configuration (each model alone, and the team).

Each task folder contains `task.txt` and `tests/`. For every run the task is
copied to a fresh temporary folder, tests are protected and shown read-only,
and the result is appended to a CSV immediately (so a crash loses nothing).

Infrastructure failures (a model did not answer at all: rate limit, outage)
are recorded separately and NOT counted as the model failing the task.
"""

from __future__ import annotations

import csv
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from dante.audit import AuditLog
from dante.config import Settings
from dante.llm import MultiLLM, OpenAICompatibleLLM
from dante.loop import run_task
from dante.workspace import Workspace

FIELDS = [
    "config", "task", "run", "success", "attempts", "seconds",
    "prompt_tokens", "completion_tokens", "models", "llm_failed", "error",
]


def load_tasks(tasks_dir: Path) -> list[tuple[str, str, Path]]:
    tasks = []
    for d in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
        if (d / "task.txt").exists() and (d / "tests").is_dir():
            tasks.append((d.name, (d / "task.txt").read_text(encoding="utf-8").strip(), d))
    return tasks


def run_bench(
    tasks_dir: Path,
    out_dir: Path,
    settings: Settings,
    model_names: list[str],
    include_team: bool = True,
    repeats: int = 1,
    learn: bool = False,
) -> Path:
    by_name = {p.name: p for p in settings.active_providers()}
    missing = [m for m in model_names if m not in by_name]
    if missing:
        raise ValueError(f"No key or unknown model(s): {', '.join(missing)}")
    paid = [m for m in model_names if by_name[m].paid]
    if paid:
        raise ValueError(f"Bench never uses paid models (money rule): {', '.join(paid)}")

    configs: list[tuple[str, list[str], str]] = [(m, [m], "fallback") for m in model_names]
    if include_team and len(model_names) > 1:
        configs.append(("team(" + "+".join(model_names) + ")", model_names, "rotate"))

    tasks = load_tasks(tasks_dir)
    if not tasks:
        raise ValueError(f"No tasks found in {tasks_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    csv_path = out_dir / f"bench-{stamp}.csv"
    audit = AuditLog(out_dir / "audit")
    test_cmd = f'"{sys.executable}" -m unittest discover -s tests'

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(FIELDS)

    total = len(configs) * len(tasks) * repeats
    n = 0
    for run in range(1, repeats + 1):
        for cfg_name, names, strategy in configs:
            for task_name, task_text, task_dir in tasks:
                n += 1
                work = Path(tempfile.mkdtemp(prefix="dante-bench-"))
                shutil.copytree(task_dir / "tests", work / "tests")
                read_only = sorted(p.relative_to(work).as_posix() for p in (work / "tests").rglob("*.py"))
                ws = Workspace(work, tuple(settings.protected_paths) + ("tests",))
                llm = MultiLLM([(m, OpenAICompatibleLLM(by_name[m], settings)) for m in names], strategy)

                start = time.monotonic()
                # learn=True: use and grow the lesson memory (night training) / уроки: читати й поповнювати (нічне навчання)
                from dante.config import LESSONS_FILE
                r = run_task(task_text, test_cmd, ws, llm, settings, audit, read_only_files=read_only,
                             lessons_path=LESSONS_FILE if learn else None)
                secs = round(time.monotonic() - start, 2)
                shutil.rmtree(work, ignore_errors=True)

                row = [
                    cfg_name, task_name, run, int(r.success), r.attempts, secs,
                    r.prompt_tokens, r.completion_tokens, " ".join(r.models),
                    int(r.llm_failed), (r.error or "")[:600],
                ]
                with csv_path.open("a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow(row)
                mark = "OK  " if r.success else ("N/A " if r.llm_failed else "FAIL")
                print(f"[{n}/{total}] {mark} {cfg_name:<40} {task_name:<16} "
                      f"attempts={r.attempts} {secs}s", flush=True)

    summary = summarize(csv_path)
    summary_path = csv_path.with_suffix(".md")
    summary_path.write_text(summary, encoding="utf-8")
    print("\n" + summary)
    return summary_path


def summarize(csv_path: Path) -> str:
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    configs = list(dict.fromkeys(r["config"] for r in rows))
    tasks = list(dict.fromkeys(r["task"] for r in rows))

    lines = [
        f"# DANTE benchmark — {csv_path.name}",
        "",
        f"Tasks: {len(tasks)}. N/A = no model answered (rate limit/outage), not counted as failure.",
        "",
        "| Config | Solved | Solved % (of measured) | 1st try | Avg attempts (solved) | Avg time s | Tokens out | N/A |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in configs:
        rs = [r for r in rows if r["config"] == c]
        measured = [r for r in rs if r["llm_failed"] == "0" or r["success"] == "1"]
        solved = [r for r in measured if r["success"] == "1"]
        first = [r for r in solved if r["attempts"] == "1"]
        pct = f"{100 * len(solved) / len(measured):.0f}%" if measured else "-"
        att = f"{statistics.mean(int(r['attempts']) for r in solved):.2f}" if solved else "-"
        t = f"{statistics.mean(float(r['seconds']) for r in rs):.1f}" if rs else "-"
        tok = sum(int(r["completion_tokens"]) for r in rs)
        lines.append(f"| {c} | {len(solved)}/{len(measured)} | {pct} | {len(first)} | {att} | {t} | {tok} | {len(rs) - len(measured)} |")

    lines += ["", "## Per task", "", "| Task | " + " | ".join(configs) + " |", "|---|" + "---|" * len(configs)]
    for t in tasks:
        cells = []
        for c in configs:
            rs = [r for r in rows if r["config"] == c and r["task"] == t]
            cells.append(" ".join(
                ("✓" + r["attempts"]) if r["success"] == "1" else ("N/A" if r["llm_failed"] == "1" else "✗")
                for r in rs
            ))
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines += ["", "✓N = solved on attempt N; ✗ = not solved in all attempts; N/A = no model answered."]
    return "\n".join(lines) + "\n"
