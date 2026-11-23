"""Daily AI capacity probing and reporting (stdlib only).

Щоденна перевірка ПОТУЖНОСТІ безкоштовних ШІ та формування звіту (лише стандартна бібліотека)."""
import csv
import re
from pathlib import Path

# Known daily limits for free AI providers / Відомі денні ліміти безкоштовних ШІ-провайдерів
KNOWN_LIMITS = {
    "gemini": {
        "requests_per_day": 1500,
        "source": "Google AI Studio free tier limits (ai.google.dev)",
    },
    "glm": {
        "requests_per_day": 1000,
        "source": "Zhipu GLM free API documentation (open.bigmodel.cn)",
    },
    "freellmapi": {
        "requests_per_day": None,
        "source": "FreeLLMAPI project README (github.com)",
    },
}

# Column order for the CSV history / Порядок колонок для історії у CSV
CSV_COLUMNS = [
    "when",
    "name",
    "ok",
    "latency_s",
    "requests_limit",
    "requests_remaining",
    "tokens_limit",
    "tokens_remaining",
    "reset",
    "error",
    "source",
]


def _to_int(value):
    """Convert a header value to int, or None if missing / invalid.

    Перетворити значення заголовка на int або None, якщо воно відсутнє / некоректне."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def parse_headers(headers):
    """Parse rate-limit headers case-insensitively into a normalized dict.

    Розібрати заголовки лімітів без урахування регістру у нормалізований словник."""
    # Build a lowercase-keyed view of the headers / Побудувати подання заголовків з ключами у нижньому регістрі
    lower = {}
    for key, val in (headers or {}).items():
        lower[str(key).lower()] = val

    def pick(*names):
        """Return the first present value among candidate header names.

        Повернути перше наявне значення серед переліку назв заголовків."""
        for name in names:
            if name in lower:
                return lower[name]
        return None

    # Requests: specific headers first, then generic fallback / Запити: спершу спеціальні, потім загальний запасний варіант
    requests_limit = _to_int(pick("x-ratelimit-limit-requests", "x-ratelimit-limit"))
    requests_remaining = _to_int(pick("x-ratelimit-remaining-requests", "x-ratelimit-remaining"))
    # Tokens: only the specific headers exist / Токени: існують лише спеціальні заголовки
    tokens_limit = _to_int(pick("x-ratelimit-limit-tokens"))
    tokens_remaining = _to_int(pick("x-ratelimit-remaining-tokens"))

    # Reset stays a raw string (e.g. "2m59s") / Reset лишається рядком (напр. "2m59s")
    reset = pick("x-ratelimit-reset-requests", "x-ratelimit-reset")
    if reset is not None:
        reset = str(reset)

    return {
        "requests_limit": requests_limit,
        "requests_remaining": requests_remaining,
        "tokens_limit": tokens_limit,
        "tokens_remaining": tokens_remaining,
        "reset": reset,
    }


def probe(providers, call):
    """Probe free providers and return one row per provider.

    Перевірити безкоштовних провайдерів і повернути по одному рядку на кожного."""
    rows = []
    for provider in providers:
        # Skip paid providers / Пропустити платних провайдерів
        if provider.get("paid"):
            continue

        name = provider.get("name")
        row = {
            "name": name,
            "ok": False,
            "latency_s": None,
            "requests_limit": None,
            "requests_remaining": None,
            "tokens_limit": None,
            "tokens_remaining": None,
            "reset": None,
            "error": "",
            "source": "headers",
        }

        try:
            headers, latency = call(provider)
        except Exception as exc:  # noqa: BLE001 - record any failure as an error row / записати будь-яку помилку як рядок помилки
            row["ok"] = False
            row["error"] = str(exc)
            rows.append(row)
            continue

        parsed = parse_headers(headers)
        row["ok"] = True
        row["latency_s"] = latency
        row["requests_limit"] = parsed["requests_limit"]
        row["requests_remaining"] = parsed["requests_remaining"]
        row["tokens_limit"] = parsed["tokens_limit"]
        row["tokens_remaining"] = parsed["tokens_remaining"]
        row["reset"] = parsed["reset"]

        # Fill the gap from known limits when no request limit arrived / Заповнити прогалину з відомих лімітів, коли ліміт запитів не надійшов
        if parsed["requests_limit"] is None and name in KNOWN_LIMITS:
            row["source"] = KNOWN_LIMITS[name]["source"]
        else:
            row["source"] = "headers"

        rows.append(row)
    return rows


def claude_percent(path):
    """Read the leading integer percentage from a text file, or None.

    Прочитати цілий відсоток на початку текстового файлу або None."""
    file_path = Path(path)
    # Missing file yields None / Відсутній файл дає None
    if not file_path.exists():
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Match the leading integer (allowing leading spaces) / Знайти ціле число на початку (допускаючи пробіли)
    match = re.match(r"\s*(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def write_report(rows, csv_path, md_path, now, claude_percent=None):
    """Append rows to a CSV history and write a Ukrainian Markdown report.

    Додати рядки до історії у CSV та записати звіт Markdown українською."""
    csv_path = Path(csv_path)
    md_path = Path(md_path)

    # Append to CSV history, writing the header only once / Додати до історії CSV, записати заголовок лише один раз
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            # Keep only known columns and stamp the 'when' column / Залишити лише відомі колонки та додати колонку 'when'
            out = {col: row.get(col, "") for col in CSV_COLUMNS}
            out["when"] = now
            writer.writerow(out)

    # Build the Ukrainian Markdown report / Побудувати звіт Markdown українською
    day = str(now)[:10]
    lines = []
    lines.append(f"# Потужність ШІ ({day})")
    lines.append("")
    lines.append("| ШІ | Статус | Запити (лишилось/ліміт) | Токени (лишилось/ліміт) | Затримка, с | Джерело |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in rows:
        # Human-readable status / Зрозумілий для людини статус
        if row.get("ok"):
            status = "OK"
        else:
            status = f"Помилка: {row.get('error', '')}"
        requests = f"{row.get('requests_remaining')}/{row.get('requests_limit')}"
        tokens = f"{row.get('tokens_remaining')}/{row.get('tokens_limit')}"
        latency = row.get("latency_s")
        latency = "" if latency is None else latency
        lines.append(
            f"| {row.get('name')} | {status} | {requests} | {tokens} | {latency} | {row.get('source', '')} |"
        )

    # Optional Claude weekly-usage line / Необов'язковий рядок про тижневе використання Claude
    if claude_percent is not None:
        lines.append("")
        lines.append(f"Claude: {claude_percent} % тижневого ліміту використано (вносить автор)")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
