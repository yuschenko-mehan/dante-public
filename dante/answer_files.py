"""Parse code files out of plain text web AI chat answers.
Розібрати файли коду з проститекстових відповідей веб-чатів ШІ."""

import re

# Known code extensions for file names / Відомі розширення коду для назв файлів
KNOWN_EXTENSIONS = {
    "py", "rs", "js", "ts", "cpp", "c", "h", "hpp", "java", "go", "rb", "php",
    "html", "css", "json", "yaml", "yml", "sh", "bash", "sql", "md", "txt", "xml",
    "toml", "ini", "cfg", "dockerfile", "rs"
}

# Optional toolbar words to skip after language line / Необов'язкові слова панелі інструментів для пропуску після рядка мови
TOOLBAR_WORDS = {
    "копіювати", "скопіювати", "запустити", "завантажити", "редагувати",
    "copy", "copy code", "run", "download", "edit"
}


def is_filename(line: str) -> bool:
    """Check if a line represents a valid file name.
    Перевірити, чи рядок представляє дійсну назву файлу."""
    if not line or not re.match(r'^[\w\.\-/]+$', line):
        return False
    if "." not in line:
        return False
    ext = line.rsplit(".", 1)[-1].lower()
    return ext in KNOWN_EXTENSIONS


def is_prose_line(line: str) -> bool:
    """Check if a line is an unindented prose line.
    Перевірити, чи є рядок невідступним рядком прози."""
    if not line:
        return False
    # Starts with a capital letter, has spaces, no code symbols
    # Починається з великої літери, має пробіли, без символів коду
    if not line[0].isupper() and not line[0].isdigit():
        return False
    if " " not in line:
        return False
    code_symbols = set("=()[]{}<>;")
    if any(sym in line for sym in code_symbols):
        return False
    return True


def is_clock_line(line: str) -> bool:
    """Check if a line is a clock line like 14:11.
    Перевірити, чи є рядок рядком годинника на кшталт 14:11."""
    return bool(re.match(r'^\d{2}:\d{2}$', line))


def parse(text: str) -> dict:
    """Parse text and extract code files.
    Розібрати текст та витягти файли коду."""
    result = {}
    lines = text.splitlines()
    i = 0
    n = len(lines)

    current_file = None
    current_lang = None
    code_lines = []

    def save_current():
        """Save the current accumulated file content.
        Зберегти поточний накопичений вміст файлу."""
        nonlocal current_file, current_lang, code_lines
        if current_file and current_lang and code_lines:
            # Strip leading/trailing blank lines / Видалити початкові/кінцеві порожні рядки
            while code_lines and not code_lines[0].strip():
                code_lines.pop(0)
            while code_lines and not code_lines[-1].strip():
                code_lines.pop()
            if code_lines or current_file:
                result[current_file] = "\n".join(code_lines)
        current_file = None
        current_lang = None
        code_lines = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Check if this line is a file name header / Перевірити, чи цей рядок є заголовком імені файлу
        if is_filename(stripped):
            # A file name inside a sentence or without following structure is handled below.
            # Look ahead for language line and optional blank lines / Шукати рядок мови та необов'язкові порожні рядки
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            
            if j < n:
                lang_candidate = lines[j].strip().lower()
                # Check if it's a valid one-word language line / Перевірити, чи це дійсний однослівний рядок мови
                if lang_candidate and len(lang_candidate.split()) == 1 and not is_filename(lines[j].strip()) and not is_prose_line(lines[j]):
                    # Found a valid header! Save previous file first.
                    # Знайдено дійсний заголовок! Зберегти попередній файл спочатку.
                    save_current()
                    current_file = stripped
                    current_lang = lang_candidate
                    i = j + 1
                    
                    # Skip optional toolbar words / Пропустити необов'язкові слова панелі інструментів
                    while i < n:
                        tb_candidate = lines[i].strip().lower()
                        if tb_candidate in TOOLBAR_WORDS:
                            i += 1
                        else:
                            break
                    continue

        # If we are inside a file block, check for termination conditions
        # Якщо ми знаходимося всередині блоку файлу, перевірити умови завершення
        if current_file and current_lang:
            # Check termination: next file header, unindented prose line, or clock line
            # Перевірка завершення: наступний заголовок файлу, невідступний рядок прози або рядок годинника
            is_new_header = False
            if is_filename(stripped):
                # Verify if it has a language line following it
                # Перевірити, чи за ним слідує рядок мови
                cj = i + 1
                while cj < n and not lines[cj].strip():
                    cj += 1
                if cj < n:
                    lc = lines[cj].strip().lower()
                    if lc and len(lc.split()) == 1 and not is_filename(lines[cj].strip()) and not is_prose_line(lines[cj]):
                        is_new_header = True

            if is_new_header or is_clock_line(stripped) or (not line.startswith(" ") and not line.startswith("\t") and is_prose_line(stripped)):
                save_current()
                # Re-evaluate current line as it might be a new header
                # Повторно оцінити поточний рядок, оскільки він може бути новим заголовком
                continue
            else:
                code_lines.append(line)

        i += 1

    save_current()
    return result
