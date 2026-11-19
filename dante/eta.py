from __future__ import annotations
import statistics
from datetime import datetime, timedelta
DEFAULTS = {"code": (90, 360), "dante": (60, 600), "notify": (35, 60), "cmd": (5, 300), "train": (800, 1500)}
def kind_of(job, name=""):
    if name.startswith("zz-train"): return "train"
    if not isinstance(job, dict): return "cmd"
    if job.get("kind") == "dante": return "code" if "run" in (job.get("args") or []) else "dante"
    return "notify" if "notify.ps1" in str(job.get("command") or "") else "cmd"
def record(hist, kind, seconds, keep=50):
    v = hist.setdefault(kind, []); v.append(seconds); del v[:-keep]; return hist
def _d(kind): return DEFAULTS.get(kind, DEFAULTS["cmd"])
def typical(hist, kind):
    v = hist.get(kind) or []
    return statistics.median(v) if v else _d(kind)[0]
def worst(hist, kind):
    v = hist.get(kind) or []
    return max(v) if len(v) >= 3 else _d(kind)[1]
def estimate(lanes, running, hist):
    names = set(lanes) | set(running)
    if not names: return (0, 0)
    t = w = 0
    for ln in names:
        a = b = 0
        if ln in running:
            k, el = running[ln]
            a += max(typical(hist, k) - el, 5); b += max(worst(hist, k) - el, 5)
        for k in lanes.get(ln, []):
            a += typical(hist, k); b += worst(hist, k)
        t, w = max(t, a), max(w, b)
    return (t, w)
def eta_text(now, typical_s, worst_s, jobs):
    if jobs == 0: return "Черга порожня / Queue is empty"
    a = (now + timedelta(seconds=typical_s)).strftime("%H:%M"); b = (now + timedelta(seconds=worst_s)).strftime("%H:%M")
    return f"Завдань: {jobs} · готово ≈ {a} (не пізніше {b}) / Jobs: {jobs} · done ≈ {a} (at the latest {b})"
