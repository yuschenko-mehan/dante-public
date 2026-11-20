"""Contest of models in parallel copies / Конкурс моделей у паралельних копіях."""
from __future__ import annotations
import json, shutil, tempfile, threading
from pathlib import Path
from dante import critic as C
USAGE_FILE = Path(__file__).resolve().parents[1] / "contest-usage.json"
SKIP = (".git", "__pycache__", "graphify-out", "target", ".dante")
def _load(path):
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}
def used_today(path, today):
    try:
        return int(_load(path).get(today, 0))
    except (TypeError, ValueError):
        return 0
def note_use(path, today):
    d = _load(path); d[today] = used_today(path, today) + 1
    Path(path).write_text(json.dumps(d), encoding="utf-8"); return d[today]
def run_contest(task, test_command, root, models, run_one):
    root = Path(root); models = list(models)[:3]
    results = {}
    tmps = []
    def work(m, tmp):
        copy = Path(tmp) / "p"
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns(*SKIP))
        try:
            res = run_one(m, task, test_command, copy)
            lines = 0
            for f in res.files or []:
                p = copy / f
                if p.is_file():
                    lines += len(p.read_text(encoding="utf-8", errors="replace").splitlines())
            results[m] = (res, copy, lines)
        except Exception:
            results[m] = (None, copy, 0)
    threads = []
    for m in models:
        tmp = tempfile.mkdtemp(prefix="dante-contest-"); tmps.append(tmp)
        th = threading.Thread(target=work, args=(m, tmp)); th.start(); threads.append(th)
    for th in threads: th.join()
    cands = []
    for m in models:
        res, copy, lines = results.get(m, (None, None, 0))
        passed = bool(res and res.success)
        score = float(res.critic_score) if res is not None and res.critic_score is not None else 0.0
        cands.append({"model": m, "passed": passed, "score": score, "lines": lines, "warnings": 0})
    win = C.best(cands)
    if win:
        res, copy, _ = results[win["model"]]
        for f in res.files:
            dst = root / f; dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copy / f, dst)
    for tmp in tmps: shutil.rmtree(tmp, ignore_errors=True)
    return {"winner": win["model"] if win else None, "results": [(c["model"], c["passed"], c["score"]) for c in cands]}
