"""Watchdog and job monitoring logic for DANTE.
Логіка сторожа та моніторингу завдань для DANTE.
"""


def check(now, heartbeat_ts, alive, limit_s=180):
    """Check if the system status is 'ok' or requires a 'restart'.
    Перевірити, чи статус системи 'ok', чи потребує 'restart'.
    """
    # "restart" if not alive, or heartbeat_ts is None, or now - heartbeat_ts > limit_s; else "ok"
    # "restart", якщо не alive, або heartbeat_ts є None, або now - heartbeat_ts > limit_s; інакше "ok"
    if not alive or heartbeat_ts is None or (now - heartbeat_ts) > limit_s:
        return "restart"
    return "ok"


def allow_restart(history, now, max_per_hour=6):
    """Check if restarts are allowed based on history timestamps within the last hour.
    Перевірити, чи дозволені перезапуски на основі історії міток часу за останню годину.
    """
    # Count timestamps within the last 3600 seconds / Підрахувати мітки часу за останні 3600 секунд
    recent_restarts = [ts for ts in history if (now - ts) <= 3600]
    return len(recent_restarts) < max_per_hour


def overdue_jobs(running, now, limits, default_limit=7200):
    """Find overdue jobs exceeding their time limits, sorted by name.
    Знайти прострочені завдання, що перевищують ліміти часу, відсортовані за назвою.
    """
    overdue = []
    for job_name, start_ts in running.items():
        limit = limits.get(job_name, default_limit)
        if (now - start_ts) > limit:
            overdue.append(job_name)
    return sorted(overdue)
