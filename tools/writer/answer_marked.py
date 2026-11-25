"""Strict file format for web AI chat answers (the Writer asks for it, the Reader parses it).
Суворий формат файлів у відповідях веб-чатів ШІ (Писар просить його, Читач розбирає)."""
from __future__ import annotations

import re

FORMAT_PROMPT = (
    "ANSWER FORMAT (strict): give every file IN FULL, each one exactly like this:\n"
    "=== FILE: relative/path.ext ===\n"
    "<the whole file content>\n"
    "=== END FILE ===\n"
    "Use relative paths with /. Do not put the files inside code fences (```), do not add anything between the "
    "markers except the file content. Short explanations may go before the first file or after the last one."
)

_START = re.compile(r"^[\s*`_]*===\s*FILE:\s*(.+?)\s*===[\s*`_]*$")
_END = re.compile(r"^[\s*`_]*===\s*END FILE\s*===[\s*`_]*$")
_LABELS = {
    "python", "rust", "toml", "html", "css", "c++", "cpp", "c", "markdown", "md", "bash", "sh", "shell",
    "javascript", "js", "typescript", "ts", "json", "yaml", "yml", "xml", "sql", "java", "go", "text",
    "plaintext", "ini", "arduino", "ino", "powershell", "bat", "cmd", "звичайний текст", "код", "code",
    "копіювати", "скопіювати", "копіювати код", "завантажити", "запустити", "редагувати",
    "copy", "copy code", "download", "run", "edit",
}
_TAIL = {"копіювати", "скопіювати", "копіювати код", "завантажити", "запустити", "редагувати",
         "copy", "copy code", "download", "run", "edit"}


def with_format(task: str) -> str:
    """Task + the strict format instruction / Завдання + інструкція суворого формату."""
    return task + "\n\n" + FORMAT_PROMPT


def _safe(path: str) -> str | None:
    p = path.strip().replace("\\", "/")
    if not p or p.startswith("/") or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/"):
        return None
    return p


def _clean(lines: list[str]) -> str:
    """Drop UI labels, fences and blank lines at the edges / Прибрати ярлики, огорожі й порожні рядки по краях."""
    lines = list(lines)
    while lines and (not lines[0].strip() or lines[0].strip().lower() in _LABELS or lines[0].strip().startswith("```")):
        lines.pop(0)
    while lines and (not lines[-1].strip() or lines[-1].strip().lower() in _TAIL or lines[-1].strip() == "```"):
        lines.pop()
    return "\n".join(lines)


def parse_marked(text: str, problems: list | None = None) -> dict:
    """Files between === FILE: path === and === END FILE === / Файли між мітками."""
    probs = problems if problems is not None else []
    out: dict = {}
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    path, body = None, []

    def close(complete: bool):
        if path is None:
            return
        safe = _safe(path)
        if safe is None:
            probs.append(f"unsafe path: {path}")
        elif not complete:
            probs.append(f"cut off: {path}")
        else:
            out[safe] = _clean(body)

    for line in lines:
        m = _START.match(line)
        if m:
            close(True)                     # no END but a new FILE: the old one ends here / нова мітка
            path, body = m.group(1), []
            continue
        if path is not None and _END.match(line):
            close(True)
            path, body = None, []
            continue
        if path is not None:
            body.append(line)
    close(False)                            # text ended inside a file: cut off / обірвано
    return out


def parse_any(text: str, problems: list | None = None) -> dict:
    """Strict format if present, else the old heuristic parser / Суворий формат, інакше старий розбір."""
    if any(_START.match(l) for l in (text or "").replace("\r", "").split("\n")):
        return parse_marked(text, problems)
    import answer_files
    return answer_files.parse(text)
