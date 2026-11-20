"""Contest utilities.
Конкурсні утиліти.
"""

# Default settings for the contest / Типові налаштування конкурсу
DEFAULTS = {"enabled": True, "max_models": 2, "per_day": 10, "after_failures": 1}

def should_contest(failures, used_today, settings):
    """Return True if a contest is allowed.
    Returns True only when enabled, failures >= after_failures and used_today < per_day.
    Повертає True лише коли ввімкнено, кількість помилок >= after_failures і використано сьогодні менше per_day.
    """
    if not settings.get("enabled", False):
        return False
    if failures < settings.get("after_failures", 0):
        return False
    if used_today >= settings.get("per_day", 0):
        return False
    return True

def pick_contestants(ranked_models, already_tried, settings):
    """Pick up to max_models (capped at 3) models not already tried.
    Returns a list of model names, best first.
    Повертає список імен моделей, найкращі спочатку, не більше max_models (не більше 3) і не включаючи already_tried.
    """
    max_models = int(settings.get("max_models", 0))
    # never more than 3 even if settings say more
    limit = min(max_models, 3)
    if limit <= 0:
        return []
    result = []
    for m in ranked_models:
        if m in already_tried:
            continue
        result.append(m)
        if len(result) >= limit:
            break
    return result
