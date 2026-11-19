"""Parse file edits out of an LLM answer.
Парсиінг редагувань файлів із відповіді LLM.

The model is asked to answer only with blocks of this exact form:
Модель просять відповідати лише блоками в такому точно форматі:

    === FILE: relative/path.py ===
    <full new content of the file>
    === END FILE ===

    === PATCH: relative/path.py ===
    <<<<<<< SEARCH
    <existing lines, copied exactly>
    =======
    <new lines>
    >>>>>>> REPLACE
    ... more SEARCH/REPLACE hunks ...
    === END PATCH ===

Whole-file replacement or search/replace patches are supported.
Підтримується повна заміна файлу або патчі пошуку/заміни.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Regular expression for matching FILE blocks / Регулярний вираз для збігу блоків FILE
_BLOCK = re.compile(
    r"^=== FILE: (?P<path>[^\n=]+?) ===\n(?P<body>.*?)^=== END FILE ===\s*$",
    re.MULTILINE | re.DOTALL,
)

# Regular expression for matching PATCH blocks / Регулярний вираз для збігу блоків PATCH
_PATCH_BLOCK = re.compile(
    r"^=== PATCH: (?P<path>[^\n=]+?) ===\n(?P<body>.*?)^=== END PATCH ===\s*$",
    re.MULTILINE | re.DOTALL,
)

# Regular expression for parsing SEARCH/REPLACE hunks / Регулярний вираз для розбору шматків SEARCH/REPLACE
_HUNK = re.compile(
    r"^<<<<<<< SEARCH\n(?P<search>.*?\n?)^=======\n(?P<replace>.*?\n?)^>>>>>>> REPLACE\n?",
    re.MULTILINE | re.DOTALL,
)

FORMAT_INSTRUCTIONS = (
    "Answer ONLY with file blocks in this exact format, one block per file, "
    "each containing either the COMPLETE new file content or PATCH hunks:\n"
    "=== FILE: relative/path/to/file ===\n"
    "<file content>\n"
    "=== END FILE ===\n"
    "OR:\n"
    "=== PATCH: relative/path/to/file ===\n"
    "<<<<<<< SEARCH\n"
    "<existing lines>\n"
    "=======\n"
    "<new lines>\n"
    ">>>>>>> REPLACE\n"
    "=== END PATCH ===\n"
    "Use forward slashes in paths. No other text. "
    "For an EXISTING file prefer PATCH (only the changed lines); each SEARCH must copy existing lines exactly and match once. "
    "Use FILE only for new or very small files."
    "\n"
    "Відповідайте ВИКЛЮЧНО файловими блоками в цьому точному форматі, один блок на файл, "
    "кожен містить або ПОВНИЙ новий вміст файлу, або шматки патчу PATCH:\n"
    "=== FILE: відносний/шлях/до/файлу ===\n"
    "<вміст файлу>\n"
    "=== END FILE ===\n"
    "АБО:\n"
    "=== PATCH: відносний/шлях/до/файлу ===\n"
    "<<<<<<< SEARCH\n"
    "<існуючі рядки>\n"
    "=======\n"
    "<нові рядки>\n"
    ">>>>>>> REPLACE\n"
    "=== END PATCH ===\n"
    "Використовуйте слеші у шляхах. Жодного іншого тексту."
)


@dataclass(frozen=True)
class FileEdit:
    path: str
    content: str


def parse_hunks(body: str) -> list[tuple[str, str]]:
    """Parse SEARCH/REPLACE hunks from a patch body / Розібрати шматки SEARCH/REPLACE з тіла патчу."""
    hunks = []
    for m in _HUNK.finditer(body):
        hunks.append((m.group("search"), m.group("replace")))
    if not hunks:
        raise ValueError("No valid SEARCH/REPLACE hunks found in patch body.")
    return hunks


def apply_hunks(text: str, hunks: list[tuple[str, str]], path: str = "") -> str:
    """Apply search/replace hunks to text with fallback / Застосувати шматки пошуку/заміни до тексту з резервним варіантом."""
    for search, replace in hunks:
        if not search:
            raise ValueError("SEARCH block cannot be empty.")
        
        # 1) SEARCH occurs exactly once as a substring -> replace it / SEARCH зустрічається рівно один раз як підрядок -> замінити його
        if text.count(search) == 1:
            text = text.replace(search, replace, 1)
            continue
        
        # If 0 or >1 exact matches, try fallback: compare line by line ignoring trailing spaces/tabs
        # Якщо 0 або >1 точних збігів, спробувати резервний варіант: порівнювати рядок за рядком, ігноруючи пробіли/табуляції в кінці
        text_lines = text.splitlines(keepends=True)
        search_lines = search.splitlines(keepends=True)
        
        matches = []
        n_search = len(search_lines)
        for i in range(len(text_lines) - n_search + 1):
            chunk = text_lines[i:i + n_search]
            if len(chunk) == n_search:
                # Compare lines ignoring trailing whitespace / Порівняти рядки, ігноруючи кінцеві пробіли
                match = True
                for tl, sl in zip(chunk, search_lines):
                    if tl.rstrip(" \t\r\n") != sl.rstrip(" \t\r\n"):
                        match = False
                        break
                if match:
                    matches.append(i)
        
        if len(matches) == 1:
            i = matches[0]
            # Replace the matched lines with replace lines / Замінити знайдені рядки новими
            replace_lines = replace.splitlines(keepends=True)
            text_lines[i:i + n_search] = replace_lines
            text = "".join(text_lines)
        elif len(matches) == 0:
            raise ValueError(f"Hunk search block not found in {path}")
        else:
            raise ValueError(f"Hunk search block matches {len(matches)} times in {path}")
            
    return text


def parse_edits(answer: str, read=None) -> list[FileEdit]:
    """Parse FILE and PATCH blocks from the LLM answer / Розібрати блоки FILE та PATCH з відповіді LLM."""
    text = answer.replace("\r\n", "\n")
    
    # Track edits in order of appearance / Відстежувати редагування в порядку появи
    edits_dict: dict[str, str] = {}
    order: list[str] = []

    # Find all blocks (FILE and PATCH) with their start positions to preserve order
    # Знайти всі блоки (FILE та PATCH) з їх початковими позиціями для збереження порядку
    blocks = []
    
    for m in _BLOCK.finditer(text):
        blocks.append((m.start(), "FILE", m.group("path").strip(), m.group("body")))
        
    for m in _PATCH_BLOCK.finditer(text):
        blocks.append((m.start(), "PATCH", m.group("path").strip(), m.group("body")))
        
    blocks.sort(key=lambda x: x[0])
    
    if not blocks:
        raise ValueError("The model answer contains no file blocks.")
        
    for _, btype, path, body in blocks:
        if path not in order:
            order.append(path)
            
        # Determine current content for this path / Визначити поточний вміст для цього шляху
        if path in edits_dict:
            current_content = edits_dict[path]
        else:
            current_content = read(path) if read is not None else None
            
        if btype == "FILE":
            edits_dict[path] = body
        elif btype == "PATCH":
            if current_content is None:
                raise ValueError(f"Cannot patch non-existent file {path}")
            hunks = parse_hunks(body)
            edits_dict[path] = apply_hunks(current_content, hunks, path)
            
    return [FileEdit(path=p, content=edits_dict[p]) for p in order]

