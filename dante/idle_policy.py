"""Idle policy management for DANTE.
Керування політикою простою для DANTE.
"""

import json
from pathlib import Path

# Default settings dictionary / Словник налаштувань за замовчуванням
DEFAULTS = {
    "enabled": True,
    "idle_minutes": 10,
    "max_temp": 83,
    "busy_parallel": 2,
    "train_every_minutes": 120,
}


def load_settings(path):
    """Load settings from JSON file, falling back to defaults for invalid/missing values.
    Завантажити налаштування з JSON-файлу, підставляючи значення за замовчуванням для недійсних/відсутніх.
    """
    # Start with a copy of defaults / Почати з копії значень за замовчуванням
    settings = dict(DEFAULTS)
    try:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # Validate each key against allowed types and ranges / Перевірити кожен ключ за дозволеними типами та діапазонами
                for k in DEFAULTS:
                    if k in data:
                        val = data[k]
                        if k == "enabled" and isinstance(val, bool):
                            settings[k] = val
                        elif k == "idle_minutes" and isinstance(val, int) and not isinstance(val, bool) and 1 <= val <= 240:
                            settings[k] = val
                        elif k == "max_temp" and isinstance(val, int) and not isinstance(val, bool) and 50 <= val <= 95:
                            settings[k] = val
                        elif k == "busy_parallel" and isinstance(val, int) and not isinstance(val, bool) and 1 <= val <= 32:
                            settings[k] = val
                        elif k == "train_every_minutes" and isinstance(val, int) and not isinstance(val, bool) and 10 <= val <= 1440:
                            settings[k] = val
    except Exception:
        # Fallback to defaults on any read/parse error / Повернутися до за замовчуванням при будь-якій помилці читання/парсингу
        pass
    return settings


def save_settings(path, settings):
    """Save settings dictionary to a JSON file (UTF-8), creating parent directories.
    Зберегти словник налаштувань у JSON-файл (UTF-8), створюючи батьківські каталоги.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def plan_load(idle_seconds, settings, cpu_threads, gpu_temp):
    """Determine load parameters based on idle time, temperature, and settings.
    Визначити параметри навантаження на основі часу простою, температури та налаштувань.
    """
    max_temp = settings.get("max_temp", DEFAULTS["max_temp"])
    enabled = settings.get("enabled", DEFAULTS["enabled"])
    idle_minutes = settings.get("idle_minutes", DEFAULTS["idle_minutes"])
    busy_parallel = settings.get("busy_parallel", DEFAULTS["busy_parallel"])

    # Rule 1: gpu_temp is not None and gpu_temp >= max_temp -> hot
    # Правило 1: gpu_temp не None і gpu_temp >= max_temp -> гаряче
    if gpu_temp is not None and gpu_temp >= max_temp:
        return {"parallel": 1, "train": False, "reason": "hot"}

    # Rule 2: not enabled -> off
    # Правило 2: не увімкнено -> вимкнено
    if not enabled:
        return {"parallel": busy_parallel, "train": False, "reason": "off"}

    # Rule 3: idle_seconds < idle_minutes * 60 -> user
    # Правило 3: idle_seconds < idle_minutes * 60 -> користувач
    if idle_seconds < idle_minutes * 60:
        return {"parallel": busy_parallel, "train": False, "reason": "user"}

    # Rule 4: otherwise -> idle
    # Правило 4: інакше -> простій
    parallel = max(2, cpu_threads // 2)
    return {"parallel": parallel, "train": True, "reason": "idle"}


def should_train(last_train_ts, now, settings, inbox_jobs):
    """Check whether training should be initiated.
    Перевірити, чи варто розпочинати навчання.
    """
    # True only when inbox_jobs == 0 and time interval met / True тільки коли inbox_jobs == 0 та досягнуто інтервал часу
    if inbox_jobs != 0:
        return False
    train_every_minutes = settings.get("train_every_minutes", DEFAULTS["train_every_minutes"])
    if last_train_ts is None:
        return True
    return (now - last_train_ts) >= train_every_minutes * 60
