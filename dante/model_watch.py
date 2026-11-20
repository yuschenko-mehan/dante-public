"""Model watch: tracks new AI models and proposes additions via critic.
Моніторинг моделей: відстежує нові моделі ШІ та пропонує додавання через критика."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import urlopen


@dataclass
class WatchResult:
    """Result of running model watch / Результат роботи моніторингу моделей."""
    new_count: int
    proposals: list
    errors: list


# English first, then Ukrainian / Англійською спочатку, потім українською
def diff(old: dict | None, new: dict) -> dict:
    """Finds new models per source, ignoring removed ones.
    Знаходить нові моделі за джерелом, ігноруючи видалені."""
    if old is None:
        return {}
    result = {}
    for source, new_models in new.items():
        old_models = old.get(source, [])
        old_ids = {m.get("id") for m in old_models if isinstance(m, dict) and "id" in m}
        added = [m for m in new_models if isinstance(m, dict) and m.get("id") not in old_ids]
        if added:
            result[source] = added
    return result


def load_snapshot(path: Path) -> dict | None:
    """Loads snapshot JSON or returns None if missing/broken.
    Завантажує знімок у форматі JSON або повертає None, якщо файл відсутній чи пошкоджений."""
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "models" in data:
            return data["models"]
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None


def save_snapshot(path: Path, models: dict, now: str) -> None:
    """Saves models snapshot with timestamp.
    Зберігає знімок моделей із міткою часу."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"when": now, "models": models}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_prompt(new: dict, known_services: list) -> str:
    """Builds English prompt listing new models, asking for JSON, never 'api_key'.
    Створює англійську підказку зі списком нових моделей, запитом JSON і без згадок 'api_key'."""
    services_str = ", ".join(known_services) if known_services else "none"
    lines = [
        "Review the following new AI models and decide which ones should be added, watched, or skipped.",
        f"Known services: {services_str}.",
        "Return ONLY a JSON array of objects with keys: id, verdict (add|watch|skip), why (max 200 chars).",
        "New models:"
    ]
    for source, models in new.items():
        lines.append(f"Source: {source}")
        for m in models:
            lines.append(f"- id: {m.get('id')}, free: {m.get('free')}, ctx: {m.get('ctx')}")
    return "\n".join(lines)


def parse_reply(reply: str, new: dict) -> list:
    """Parses first JSON array in reply, filters invalid ids and verdicts, limits why to 200 chars.
    Аналізує перший масив JSON у відповіді, фільтрує недійсні id та вердикти, обмежує why до 200 символів."""
    all_valid_ids = {m.get("id") for models in new.values() for m in models if isinstance(m, dict)}
    
    # Find first JSON array / Знайти перший масив JSON
    start = reply.find("[")
    end = reply.rfind("]")
    if start == -1 or end == -1 or start > end:
        return []
    
    try:
        arr = json.loads(reply[start:end+1])
        if not isinstance(arr, list):
            return []
    except Exception:
        return []

    results = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if mid not in all_valid_ids:
            continue
        verdict = str(item.get("verdict", "skip")).lower().strip()
        if verdict not in ("add", "watch", "skip"):
            verdict = "skip"
        why = str(item.get("why", ""))[:200]
        results.append({"id": mid, "verdict": verdict, "why": why})
    return results


def run_watch(sources: dict, critic, snap_path: Path, report_path: Path, known_services: list, now: str) -> WatchResult:
    """Runs watch process across sources, calls critic if new models exist, saves snapshot and report.
    Запускає процес моніторингу за джерелами, викликає критика за наявності нових моделей, зберігає знімок та звіт."""
    errors = []
    new_data = {}
    old_snapshot = load_snapshot(snap_path)

    for name, fetch_func in sources.items():
        try:
            models = fetch_func()
            new_data[name] = models
        except Exception:
            errors.append(name)
            if old_snapshot and name in old_snapshot:
                new_data[name] = old_snapshot[name]
            else:
                new_data[name] = []

    changes = diff(old_snapshot, new_data)
    total_new = sum(len(lst) for lst in changes.values())

    proposals = []
    if total_new > 0 and changes:
        prompt = build_prompt(changes, known_services)
        try:
            reply = critic(prompt)
            proposals = parse_reply(reply, changes)
        except Exception as e:
            errors.append(f"critic: {type(e).__name__}")
            for models in changes.values():
                for m in models:
                    proposals.append({"id": m.get("id"), "verdict": "watch", "why": "Critic failed"})

    # Ensure all new models have a proposal entry even if critic missed them / Переконатися, що всі нові моделі мають пропозицію
    proposed_ids = {p["id"] for p in proposals}
    for models in changes.values():
        for m in models:
            mid = m.get("id")
            if mid not in proposed_ids:
                proposals.append({"id": mid, "verdict": "watch", "why": "No proposal from critic"})

    save_snapshot(snap_path, new_data, now)

    # Write Markdown report in Ukrainian / Записати звіт у форматі Markdown українською
    date_str = now.split("T")[0] if "T" in now else now[:10]
    report_lines = [f"# Нові моделі ШІ ({date_str})"]
    if total_new == 0 or not changes:
        report_lines.append("Нових моделей немає.")
    else:
        for p in proposals:
            report_lines.append(f"{p['id']}: {p['verdict']} — {p['why']}")
    
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return WatchResult(new_count=total_new, proposals=proposals, errors=errors)


def parse_openrouter(data: dict) -> list:
    """Parses Openrouter models data.
    Аналізує дані моделей Openrouter."""
    models = []
    for item in data.get("data", []):
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not mid:
            continue
        pricing = item.get("pricing", {})
        p_prompt = float(pricing.get("prompt", "0"))
        p_comp = float(pricing.get("completion", "0"))
        free = (p_prompt == 0.0 and p_comp == 0.0)
        ctx = int(item.get("context_length", 0))
        models.append({"id": mid, "name": item.get("name", mid), "free": free, "ctx": ctx})
    return models


def parse_openai_list(data: dict) -> list:
    """Parses OpenAI style model list.
    Аналізує список моделей у стилі OpenAI."""
    models = []
    for item in data.get("data", []):
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not mid:
            continue
        models.append({"id": mid, "name": mid, "free": True, "ctx": 0})
    return models


def default_sources(fetch_json) -> dict:
    """Returns default source fetchers using fetch_json.
    Повертає функції отримання даних джерел за замовчуванням через fetch_json."""
    return {
        "openrouter": lambda: parse_openrouter(fetch_json("https://openrouter.ai/api/v1/models")),
        "freellmapi": lambda: parse_openai_list(fetch_json("http://127.0.0.1:3001/v1/models")),
    }
