"""Routing utilities.
Утиліти маршрутизації.
"""

def rank_models(rows):
    """Rank models based on solve rate, first‑try rate, avg time, then name.
    Ignores models named "team" or starting with "team(".
    Ранжує моделі за частотою розв’язання, першою спробою, середнім часом, потім за назвою.
    """
    from collections import defaultdict
    import math

    stats = defaultdict(lambda: {"rows": 0, "solved": 0, "first_try": 0, "time_sum": 0.0, "time_cnt": 0})

    for r in rows:
        model = r.get("model")
        if not model or model == "team" or model.startswith("team("):
            continue
        s = stats[model]
        s["rows"] += 1
        if r.get("solved"):
            s["solved"] += 1
            if r.get("attempts") == 1:
                s["first_try"] += 1
            s["time_sum"] += r.get("time_s", 0.0)
            s["time_cnt"] += 1

    def model_key(item):
        model, s = item
        solve_rate = s["solved"] / s["rows"] if s["rows"] else 0.0
        first_rate = s["first_try"] / s["rows"] if s["rows"] else 0.0
        avg_time = s["time_sum"] / s["time_cnt"] if s["time_cnt"] else math.inf
        return (-solve_rate, -first_rate, avg_time, model)

    sorted_models = sorted(stats.items(), key=model_key)
    return [model for model, _ in sorted_models]

def reorder(order, ranked):
    """Reorder `order` so that models present in `ranked` appear first (in ranked order),
    then the remaining models from `order` keep their original order.
    Nothing is added or removed.
    Перевпорядковує `order`, розташовуючи моделі, що є у `ranked`, спочатку (у порядку `ranked`), потім решту у їхньому початковому порядку.
    """
    ranked_set = set(ranked)
    # first part: models from ranked that are also in order, preserving ranked order
    first = [m for m in ranked if m in order]
    # second part: remaining models from order not already taken
    second = [m for m in order if m not in ranked_set]
    return first + second


# --- Live routing from bench results / Живий розподіл за результатами тренувань ---
import csv as _csv
import dataclasses as _dc
from pathlib import Path as _Path

BENCH_RESULTS = _Path(__file__).resolve().parents[2] / "bench" / "results"


def rows_from_bench(folder):
    """Rows for rank_models from bench CSV files / Рядки для rank_models з CSV тренувань."""
    folder = _Path(folder)
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.glob("bench-*.csv")):
        try:
            with p.open(encoding="utf-8", newline="") as f:
                for r in _csv.DictReader(f):
                    if str(r.get("llm_failed", "")).strip() in ("True", "true", "1") or "+" in (r.get("config") or ""):
                        continue
                    try:
                        att, sec = int(r["attempts"]), float(r["seconds"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    out.append({"model": r["config"], "task": r["task"], "solved": r.get("success") in ("True", "true", "1"),
                                "attempts": att, "time_s": sec})
        except OSError:
            continue
    return out


def apply_routing(settings, folder=None):
    """Best measured models first / Найкращі за замірами моделі — першими."""
    rows = rows_from_bench(folder or BENCH_RESULTS)
    if not rows:
        return settings
    return _dc.replace(settings, order=tuple(reorder(list(settings.order), rank_models(rows))))
