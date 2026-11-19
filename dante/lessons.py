"""Lessons module to track past mistakes and rules / Модуль уроків для відстеження минулих помилок та правил."""

import datetime
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

# Stopwords set / Набір стоп-слів
STOPWORDS = frozenset([
    "the", "and", "for", "with", "that", "this", "from", "into", "must",
    "should", "never", "always", "python", "file", "files", "test", "tests",
    "code", "use", "not", "are", "was", "when", "then", "than"
])

TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,19}$")


def _clean_text(text: str) -> str:
    """Clean inner whitespace in text / Очистити пробіли всередині тексту."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.strip().split())


def _validate_date(date_str: str) -> bool:
    """Validate YYYY-MM-DD date format / Перевірити формат дати YYYY-MM-DD."""
    if not isinstance(date_str, str):
        return False
    try:
        datetime.date.fromisoformat(date_str)
        return True
    except ValueError:
        return False


def _validate_lesson(item: dict) -> bool:
    """Validate a single lesson dict / Перевірити словник окремого уроку."""
    if not isinstance(item, dict):
        return False
    
    # Required keys / Необхідні ключі
    required = ["id", "date", "source", "tags", "mistake", "rule", "seen"]
    if not all(k in item for k in required):
        return False
        
    # id check / Перевірка id
    if not isinstance(item["id"], str) or not re.match(r"^L\d{3,}$", item["id"]):
        return False
        
    # date check / Перевірка дати
    if not _validate_date(item["date"]):
        return False
        
    # source check / Перевірка джерела
    if item["source"] not in ("claude-review", "self"):
        return False
        
    # tags check / Перевірка тегів
    tags = item["tags"]
    if not isinstance(tags, list) or not (1 <= len(tags) <= 8):
        return False
    if len(set(tags)) != len(tags):
        return False
    if tags != sorted(tags):
        return False
    for t in tags:
        if not isinstance(t, str) or not TAG_RE.match(t):
            return False
            
    # mistake check / Перевірка помилки
    mistake = item["mistake"]
    if not isinstance(mistake, str) or not (1 <= len(mistake) <= 300):
        return False
    if mistake != _clean_text(mistake):
        return False
        
    # rule check / Перевірка правила
    rule = item["rule"]
    if not isinstance(rule, str) or not (1 <= len(rule) <= 300):
        return False
    if rule != _clean_text(rule):
        return False
        
    # seen check / Перевірка лічильника seen
    seen = item["seen"]
    if not isinstance(seen, int) or isinstance(seen, bool) or seen < 1:
        return False
        
    return True


def load(path: str | Path) -> list[dict]:
    """Load lessons from file / Завантажити уроки з файлу."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "lessons" not in data:
            return []
        lessons_raw = data["lessons"]
        if not isinstance(lessons_raw, list):
            return []
        
        valid = []
        for item in lessons_raw:
            # Normalise harmless differences of a hand-edited file before checking (Claude's review fix)
            # Вирівняти дрібні відмінності файлу, зміненого вручну, перед перевіркою (виправлення Claude)
            if isinstance(item, dict):
                item = dict(item)
                if isinstance(item.get("tags"), list) and all(isinstance(t, str) for t in item["tags"]):
                    item["tags"] = sorted({t.lower() for t in item["tags"]})
                for key in ("mistake", "rule"):
                    if isinstance(item.get(key), str):
                        item[key] = _clean_text(item[key])
            if _validate_lesson(item):
                valid.append(item)
        return valid
    except (json.JSONDecodeError, OSError):
        return []


def save(path: str | Path, lessons: list[dict]) -> None:
    """Save lessons atomically / Зберегти уроки атомарно."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    content = json.dumps({"lessons": lessons}, ensure_ascii=False, indent=2)
    
    fd, tmp_path = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def guess_tags(text: str, max_tags: int = 6) -> list[str]:
    """Guess tags from text / Вгадати теги з тексту."""
    if not isinstance(text, str):
        return []
    
    # Split at everything except [a-z0-9] / Розділити за всім, крім [a-z0-9]
    raw_words = re.findall(r"[a-z0-9]+", text.lower())
    
    valid_words = []
    for w in raw_words:
        if 3 <= len(w) <= 20 and w[0].isalpha() and w not in STOPWORDS:
            valid_words.append(w)
            
    # Count frequencies, tie-break alphabetically / Підрахунок частот, сортування за алфавітом при рівності
    counter = Counter(valid_words)
    # Most frequent first, ties alphabetically / Найчастіші першими, при рівності за алфавітом
    sorted_words = sorted(counter.keys(), key=lambda w: (-counter[w], w))
    
    return sorted_words[:max_tags]


def add(path: str | Path, mistake: str, rule: str, tags: list[str], source: str = "claude-review", today: str | None = None) -> dict:
    """Add or update a lesson / Додати або оновити урок."""
    # Validate source / Перевірити джерело
    if source not in ("claude-review", "self"):
        raise ValueError("Invalid source")
        
    # Validate and clean text fields / Перевірити та очистити текстові поля
    cleaned_mistake = _clean_text(mistake)
    cleaned_rule = _clean_text(rule)
    
    if not (1 <= len(cleaned_mistake) <= 300):
        raise ValueError("Invalid mistake length")
    if not (1 <= len(cleaned_rule) <= 300):
        raise ValueError("Invalid rule length")
        
    # Process and validate tags / Обробити та перевірити теги
    if not isinstance(tags, list):
        raise ValueError("Tags must be a list")
        
    processed_tags = []
    for t in tags:
        if not isinstance(t, str):
            raise ValueError("Tag must be string")
        t_lower = t.lower()
        if not TAG_RE.match(t_lower):
            raise ValueError(f"Invalid tag: {t}")
        processed_tags.append(t_lower)
        
    if not (1 <= len(processed_tags) <= 8):
        raise ValueError("Tag count must be between 1 and 8")
        
    sorted_unique_tags = sorted(list(set(processed_tags)))
    
    # Determine date / Визначити дату
    if today is None:
        lesson_date = datetime.date.today().isoformat()
    else:
        if not _validate_date(today):
            raise ValueError("Invalid date format")
        lesson_date = today
        
    lessons = load(path)
    
    # Check if rule already exists (case-insensitive on cleaned rule) / Перевірити, чи правило вже існує
    existing_lesson = None
    for item in lessons:
        if item["rule"].lower() == cleaned_rule.lower():
            existing_lesson = item
            break
            
    if existing_lesson is not None:
        existing_lesson["seen"] += 1
        # Union tags, sorted, max 8 / Об'єднання тегів, сортування, макс 8
        combined_tags = sorted(list(set(existing_lesson["tags"] + sorted_unique_tags)))
        existing_lesson["tags"] = combined_tags[:8]
        save(path, lessons)
        return existing_lesson
        
    # Compute new id / Обчислити новий id
    max_num = 0
    for item in lessons:
        m = re.match(r"^L(\d+)$", item["id"])
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
                
    new_id = f"L{max_num + 1:03d}"
    
    new_lesson = {
        "id": new_id,
        "date": lesson_date,
        "source": source,
        "tags": sorted_unique_tags,
        "mistake": cleaned_mistake,
        "rule": cleaned_rule,
        "seen": 1
    }
    
    lessons.append(new_lesson)
    save(path, lessons)
    return new_lesson


def relevant(lessons: list[dict], text: str, k: int = 8) -> list[dict]:
    """Find relevant lessons for text / Знайти релевантні уроки для тексту."""
    if not isinstance(text, str):
        return []
        
    words_set = set(re.findall(r"[a-z0-9]+", text.lower()))
    
    scored = []
    for item in lessons:
        score = 0
        tags = item.get("tags", [])
        for t in tags:
            if t in words_set:
                score += 1
        # "always" means at least 1, not +1 (Claude's review fix)
        # «always» означає щонайменше 1, а не +1 (виправлення Claude)
        if "always" in tags:
            score = max(score, 1)

        if score >= 1:
            scored.append((score, item))
            
    # Sort by score desc, then seen desc, then id asc / Сортування за score desc, потім seen desc, потім id asc
    scored.sort(key=lambda x: (-x[0], -x[1]["seen"], x[1]["id"]))
    
    return [item for _, item in scored[:k]]


def render(lessons: list[dict]) -> str:
    """Render lessons to string / Відобразити уроки в рядок."""
    if not lessons:
        return ""
        
    lines = ["LESSONS FROM PAST MISTAKES (follow these rules):"]
    for item in lessons:
        rule = item.get("rule", "")
        mistake = item.get("mistake", "")
        lines.append(f"- {rule} (was: {mistake})")
        
    return "\n".join(lines)
