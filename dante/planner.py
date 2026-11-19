"""Architect: turn a goal in plain words into a plan of small steps, then execute it.

1. map_project()  — short description of the project (files, sizes, first lines).
2. make_plan()    — the model returns a JSON plan: steps with files and a check command.
3. The author approves the plan (shown in plain Ukrainian).
4. execute_plan() — each step goes through the fix loop (run_task); on success the step
   is committed to git (undo = one command); on failure the work stops and nothing of
   the failed step is left behind.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from dante import gitutil
from dante.audit import AuditLog
from dante.config import Settings
from dante.llm import LLM
from dante.loop import LoopResult, run_task
from dante.workspace import Workspace

SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", "__pycache__", ".gradle", ".idea",
             ".vs", ".dante", "venv", ".venv", "bin", "obj", "audit"}
TEXT_EXT = {".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".kt", ".java", ".c", ".h", ".cpp", ".hpp",
            ".cs", ".go", ".html", ".css", ".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".xml",
            ".gradle", ".kts", ".bat", ".ps1", ".sh", ".cfg", ".ini", ".sql"}


@dataclass
class Step:
    id: int
    title: str
    description: str
    files: list[str] = field(default_factory=list)
    check: str = ""
    status: str = "todo"   # todo / done / failed
    commit: str | None = None


@dataclass
class Plan:
    goal: str
    summary: str
    steps: list[Step]
    approved: bool = False

    def save(self, root: Path) -> Path:
        d = root / ".dante"
        d.mkdir(exist_ok=True)
        p = d / "plan.json"
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @staticmethod
    def load(root: Path) -> "Plan":
        data = json.loads((root / ".dante" / "plan.json").read_text(encoding="utf-8"))
        data["steps"] = [Step(**s) for s in data["steps"]]
        return Plan(**data)

    def describe(self) -> str:
        lines = [f"ЦІЛЬ: {self.goal}", f"ПІДСУМОК: {self.summary}", ""]
        for s in self.steps:
            mark = {"done": "✓", "failed": "✗"}.get(s.status, " ")
            lines.append(f"[{mark}] Крок {s.id}. {s.title}")
            lines.append(f"      {s.description}")
            if s.files:
                lines.append(f"      Файли: {', '.join(s.files)}")
            if s.check:
                lines.append(f"      Перевірка: {s.check}")
        return "\n".join(lines)


def map_project(root: Path, max_files: int = 150, head_lines: int = 3, max_chars: int = 12000) -> str:
    """Compact project map for the model: tree with sizes and the first lines of text files."""
    out: list[str] = []
    count = 0
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file():
            continue
        count += 1
        if count > max_files:
            out.append(f"... (more files not shown)")
            break
        line = f"{rel.as_posix()} ({p.stat().st_size} B)"
        if p.suffix.lower() in TEXT_EXT and p.stat().st_size < 200_000:
            try:
                head = p.read_text(encoding="utf-8", errors="replace").splitlines()[:head_lines]
                head = [h.strip()[:100] for h in head if h.strip()]
                if head:
                    line += "  | " + " / ".join(head)
            except OSError:
                pass
        out.append(line)
    text = "\n".join(out) or "(empty project)"
    return text[:max_chars]


PLAN_PROMPT = """You are the ARCHITECT. Split the goal into small, independent, testable steps
(usually 2-7). Each step must be doable by changing a few files and must have a check command
that proves it works (e.g. "python -m unittest discover -s tests", "cargo test --lib", "npm test").
The check must really verify the BEHAVIOUR of this step (run tests that call the new code);
a check that only imports a module or only checks that a file exists is NOT allowed.
Write the tests for new behaviour IN THE SAME STEP as the code (or in an earlier step), never later.
Each step creates or changes AT MOST 2 files (one model answer can carry only about 300 lines of code);
split bigger work into more steps. In Rust, a step that adds src/x.rs also adds `pub mod x;` to src/lib.rs.
Prefer changing existing files over creating new ones. Write titles and descriptions in Ukrainian, simply, for a non-programmer.

Answer ONLY with JSON, no other text:
{"summary": "...", "steps": [{"title": "...", "description": "...", "files": ["path"], "check": "command"}]}
"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON in the answer")
    raw = m.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # models often write Windows paths with single backslashes (C:\Users\...): escape lone ones and retry
        return json.loads(re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", raw))


SOURCE_EXT = (".rs", ".py", ".js", ".ts", ".toml", ".go", ".java", ".kt", ".c", ".h", ".cpp", ".cs")
SKIP_DIRS = {".git", ".dante", "target", "node_modules", "__pycache__", ".venv", "venv", "audit"}


def project_sources(root: Path, exclude: set[str] = frozenset(), budget: int = 24000) -> list[str]:
    """Existing source files of the project, smallest first, within a size budget.
    Наявні файли коду проєкту, від найменших, у межах обсягу."""
    found = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_file() and p.suffix in SOURCE_EXT and not (set(rel.parts) & SKIP_DIRS) and rel.as_posix() not in exclude:
            found.append((p.stat().st_size, rel.as_posix()))
    out, used = [], 0
    for size, rel in sorted(found):
        if used + size > budget:
            break
        out.append(rel)
        used += size
    return out


def make_plan(goal: str, root: Path, llm: LLM, default_check: str = "", attempts: int = 2) -> Plan:
    user = f"GOAL:\n{goal}\n\nPROJECT MAP:\n{map_project(root)}\n"
    if default_check:
        user += f"\nDefault check command for this project: {default_check}\n"
    last_error = ""
    for _ in range(attempts):
        resp = llm.complete(PLAN_PROMPT, user + (f"\nYour previous answer was invalid: {last_error}" if last_error else ""))
        try:
            data = _extract_json(resp.content)
            steps = [
                Step(id=i + 1, title=str(s["title"]), description=str(s.get("description", "")),
                     files=[str(f) for f in s.get("files", [])], check=str(s.get("check") or default_check))
                for i, s in enumerate(data["steps"])
            ]
            if not steps:
                raise ValueError("plan has no steps")
            missing = [st.id for st in steps if not st.check.strip()]
            if missing:
                raise ValueError(f"every step needs a check command; missing in steps {missing}")
            weak = [st.id for st in steps if re.fullmatch(r'\s*python3?\s+-c\s+["\']?\s*import\s+[\w.]+\s*["\']?\s*', st.check)]
            if weak:
                raise ValueError(f"check in steps {weak} only imports a module; it must run tests of the behaviour")
            return Plan(goal=goal, summary=str(data.get("summary", "")), steps=steps)
        except (ValueError, KeyError, TypeError) as e:
            last_error = str(e)
    raise ValueError(f"The model could not make a valid plan: {last_error}")


def execute_plan(
    plan: Plan, root: Path, llm: LLM, settings: Settings, audit: AuditLog,
    protect: tuple[str, ...] = (), on_step: Callable[[Step, LoopResult], None] | None = None,
    agent=None,
) -> bool:
    """Run approved steps in order. Stops at the first failed step. Returns True if all done."""
    if not plan.approved:
        raise ValueError("Plan is not approved by the author")
    gitutil.ensure_repo(root)
    ws = Workspace(root, tuple(settings.protected_paths) + tuple(protect) + (".dante",))
    done_titles = [s.title for s in plan.steps if s.status == "done"]
    for step in plan.steps:
        if step.status == "done":
            continue
        task = (
            f"OVERALL GOAL: {plan.goal}\n"
            f"ALREADY DONE: {'; '.join(done_titles) or 'nothing yet'}\n"
            f"THIS STEP ({step.id}/{len(plan.steps)}): {step.title}\n{step.description}\n"
            "Change only what this step needs."
        )
        existing = [f for f in step.files if (root / f).is_file()]
        # Show the code the step builds on (read-only), so the model uses real names, not invented ones
        # Показати код, на який спирається крок (лише читання), щоб модель брала справжні назви, а не вигадані
        from dante import codemap
        map_text = codemap.context(root, step.title + " " + step.description)
        read_only = project_sources(root, exclude=set(existing), budget=8000) if map_text else project_sources(root, exclude=set(existing))
        if agent is not None:
            from dante.agent import run_agent_task
            result = run_agent_task(task, step.check, root, agent, settings, audit, protect=tuple(protect))
        else:
            from dante.config import LESSONS_FILE
            result = run_task(task, step.check, ws, llm, settings, audit, context_files=existing,
                              read_only_files=read_only, lessons_path=LESSONS_FILE, map_text=map_text)
        if result.success:
            step.status = "done"
            step.commit = gitutil.commit(root, f"step {step.id}: {step.title}")
            done_titles.append(step.title)
        else:
            step.status = "failed"
        plan.save(root)
        if on_step:
            on_step(step, result)
        if not result.success:
            return False
    return True
