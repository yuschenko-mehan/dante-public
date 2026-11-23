import hashlib, json, re
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class MissionPlan:
    task: str
    steps: list = field(default_factory=list)
    done: int = 0          # steps 1..done are finished / виконано кроків

MAX_STEPS = 200


def plan_prompt(task):
    # Ask for the fewest steps that really work, keep required phrases / Просити найменшу кількість кроків, що реально працюють, зберегти обов'язкові фрази
    return ("Make a numbered plan for this coding mission: as many steps as it really needs. "
            "Ask for the FEWEST steps that really work (a bug fix or a change in 1-2 files is 1-3 steps), "
            f"at most {MAX_STEPS}. Each step one line, small enough to do and check alone. "
            "No separate steps for reading, reviewing or running tests. "
            "Only the steps, no code.\n\nMISSION:\n" + task[:3000])

def parse_steps(text):
    steps = [m.group(1).strip() for m in re.finditer(r"(?m)^\s*\d+[.)]\s*(.+)$", text or "")]
    if not steps and (text or "").strip():
        steps = [text.strip().splitlines()[0][:300]]
    return steps[:MAX_STEPS]

def render(plan, window=4):
    """Compact view: finished steps as one line, the current step, a few next ones. / Стислий вигляд плану."""
    n, d = len(plan.steps), plan.done
    lines = [f"MISSION PLAN ({n} steps, done {d}):", plan.task[:400]]
    if d:
        lines.append(f"Steps 1-{d} are DONE.")
    for i in range(d, min(n, d + 1 + window)):
        mark = "NOW" if i == d else "next"
        lines.append(f"{i + 1}. [{mark}] {plan.steps[i][:180]}")
    return "\n".join(lines)[:1800]

def _key(task):
    return hashlib.sha256(task.encode("utf-8")).hexdigest()[:16]

def get_or_make(root, task, ask):
    f = Path(root) / ".dante" / "mission.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("key") == _key(task) and d.get("steps"):
            return MissionPlan(task, d["steps"], int(d.get("done", 0)))
    except (OSError, ValueError, AttributeError):
        pass
    try:
        steps = parse_steps(ask(plan_prompt(task)))
    except Exception:
        return None
    if not steps:
        return None
    f.parent.mkdir(parents=True, exist_ok=True)
    plan = MissionPlan(task, steps)
    save(root, plan)
    return plan


def save(root, plan):
    f = Path(root) / ".dante" / "mission.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"key": _key(plan.task), "steps": plan.steps, "done": plan.done}, ensure_ascii=False, indent=1),
                 encoding="utf-8")


def step_task(plan):
    """Task text for the current step only. / Текст завдання лише для поточного кроку."""
    i = plan.done
    return (f"{plan.task[:1500]}\n\nWORK ONLY ON STEP {i + 1} of {len(plan.steps)}: {plan.steps[i]}\n"
            "Earlier steps are already in the files. Do not start later steps.")
