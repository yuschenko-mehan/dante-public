from dataclasses import dataclass
import re

@dataclass
class Block:
    lang: str
    code: str
    filename: str | None = None

LANG_EXT = {
    "python": "py",
    "py": "py",
    "rust": "rs",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "html": "html",
    "css": "css",
    "json": "json",
    "bash": "sh",
    "sh": "sh",
    "shell": "sh",
    "powershell": "ps1",
    "ps1": "ps1",
    "bat": "bat",
    "cmd": "bat",
    "sql": "sql",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "toml": "toml",
    "yaml": "yml",
    "yml": "yml",
    # New languages / Нові мови
    "arduino": "ino",
    "ino": "ino",
    "java": "java",
    "csharp": "cs",
    "cs": "cs",
    "go": "go",
    "kotlin": "kt",
    "kt": "kt",
    "php": "php",
    "xml": "xml",
    "markdown": "md",
    "md": "md",
}

def _is_path(s: str) -> bool:
    if not s or " " in s:
        return False
    parts = s.split(".")
    if len(parts) < 2:
        return False
    ext = parts[-1]
    if not ext or not ext.isalnum():
        return False
    return True

def name_from_context(before: str, code: str) -> tuple[str | None, str]:
    # 1. comment filename in first line of code
    lines = code.splitlines()
    if lines:
        first = lines[0].strip()
        m = re.match(r'^(?:#|//|--)\s*(?:file|filename):\s*(\S+)\s*$', first, re.IGNORECASE)
        if m:
            return m.group(1), "\n".join(lines[1:])

    # 2. last non-empty line before fence
    before_lines = [l.strip() for l in before.splitlines() if l.strip()]
    if before_lines:
        last = before_lines[-1]
        # strip decorations
        last = re.sub(r'^#{1,6}\s*', '', last)               # headings
        last = re.sub(r'^\*\*(.*?)\*\*$', r'\1', last)       # bold
        last = re.sub(r'^`(.*?)`$', r'\1', last)             # backticks
        last = re.sub(r'^(?:file|файл):\s*', '', last, flags=re.IGNORECASE)
        last = re.sub(r':$', '', last)                       # trailing colon
        last = last.strip()
        if _is_path(last):
            return last, code
    return None, code

_OPEN = re.compile(r"^[ \t]*(```|~~~)[ \t]*([^\s`]*)[^\n`]*$")


def extract_blocks(text: str) -> list[Block]:
    """Fences count only at the start of a line (``` inside a sentence or a string is not a fence)."""
    blocks: list[Block] = []
    lines = text.split("\n")
    i, before_start = 0, 0
    while i < len(lines):
        m = _OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        fence, lang = m.group(1), m.group(2).lower()
        j = i + 1
        while j < len(lines) and lines[j].strip() != fence:  # closing fence: alone on its line
            j += 1
        before = "\n".join(lines[before_start:i])
        code = "\n".join(lines[i + 1:j]).rstrip("\n")  # an unclosed fence takes the rest
        filename, code = name_from_context(before, code)
        blocks.append(Block(lang=lang, code=code, filename=filename))
        i = before_start = j + 1
    return blocks


def collect(blocks: list[Block]) -> dict[str, str]:
    files: dict[str, str] = {}
    seen_unnamed: dict[tuple[str, str], str] = {}
    unnamed_counter = 1

    for b in blocks:
        if b.filename is not None:
            files[b.filename] = b.code
        else:
            key = (b.lang.lower(), b.code)
            if key in seen_unnamed:
                files[seen_unnamed[key]] = b.code
            else:
                ext = LANG_EXT.get(b.lang.lower(), "txt")
                name = f"block_{unnamed_counter:02d}.{ext}"
                unnamed_counter += 1
                files[name] = b.code
                seen_unnamed[key] = name
    return files

