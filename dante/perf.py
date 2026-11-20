"""Self-measurement from audit logs / Самовимірювання за журналами аудиту."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
def summarize_run(events):
    res = [e for e in events if e.get("event") in ("task_success", "task_failed")]
    if not res or not events: return None
    t = [datetime.fromisoformat(e["ts"]) for e in events if "ts" in e]
    last = res[-1]
    return {"start": t[0], "seconds": (t[-1] - t[0]).total_seconds(), "success": last["event"] == "task_success",
            "attempts": int(last.get("attempts", 0) or 0), "academy": any(e.get("event") == "academy_hints" for e in events)}
def load_runs(audit_dir):
    out = []
    for f in sorted(Path(audit_dir).glob("*.jsonl")):
        ev = []
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(line)
                if isinstance(d, dict): ev.append(d)
            except ValueError:
                pass
        try:
            r = summarize_run(ev)
        except (KeyError, ValueError):
            r = None
        if r: out.append(r)
    return sorted(out, key=lambda r: r["start"])
def stats(runs):
    n = len(runs); ok = [r for r in runs if r["success"]]
    if not n: return {"runs": 0, "solved": 0, "solve_rate": 0, "first_try": 0, "avg_attempts": 0, "avg_seconds": 0}
    return {"runs": n, "solved": len(ok), "solve_rate": len(ok) / n, "first_try": sum(1 for r in ok if r["attempts"] == 1) / n,
            "avg_attempts": sum(r["attempts"] for r in ok) / len(ok) if ok else 0, "avg_seconds": sum(r["seconds"] for r in ok) / len(ok) if ok else 0}
def compare(runs, split):
    return {"before": stats([r for r in runs if r["start"] < split]), "after": stats([r for r in runs if r["start"] >= split])}
def report(cmp):
    b, a = cmp["before"], cmp["after"]
    lines = []
    for name, s in (("До / Before", b), ("Після / After", a)):
        lines.append(f"{name}: завдань {s['runs']}, розв'язано {s['solved']} ({s['solve_rate']:.0%}), з 1-ї спроби {s['first_try']:.0%}, "
                     f"спроб {s['avg_attempts']:.1f}, час {s['avg_seconds']:.0f} с")
    if b["avg_seconds"] > 0 and a["avg_seconds"] > 0:
        r = b["avg_seconds"] / a["avg_seconds"]
        lines.append(f"Час на завдання: {'швидше' if r >= 1 else 'повільніше'} у {max(r, 1/r):.1f}× / time per task {r:.1f}× ")
    return "\n".join(lines)
