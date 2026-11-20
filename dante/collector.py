"""Collector: extracts code blocks from text and writes them into a workspace project safely.
Збирач: виймає блоки коду з тексту та безпечно записує їх у проєкт робочої області."""

from __future__ import annotations

import sys
from pathlib import Path

from dante import codeblocks


def from_text(text: str) -> dict[str, str]:
    """Extract and collect code blocks from text / Витягти та зібрати блоки коду з тексту."""
    return codeblocks.collect(codeblocks.extract_blocks(text))


def safe_rel(path: str) -> str | None:
    """Normalize and validate a relative path, ensuring no directory traversal or absolute paths.
    Нормалізувати та перевірити відносний шлях, гарантуючи відсутність виходу за межі каталогу чи абсолютних шляхів."""
    if not path:
        return None
    # Convert backslashes to slashes / Перетворити зворотні слеші на прямі
    p = path.replace("\\", "/")
    # Strip leading "./" / Видалити початковий "./"
    while p.startswith("./"):
        p = p[2:]
    # Check for absolute paths or drive letters / Перевірити на абсолютні шляхи або букви дисків
    if p.startswith("/") or ":" in p:
        return None
    parts = p.split("/")
    norm_parts = []
    for part in parts:
        if not part or part == ".":
            continue
        if part == "..":
            return None
        norm_parts.append(part)
    if not norm_parts:
        return None
    return "/".join(norm_parts)


def write_files(files: dict[str, str], root: Path) -> list[str]:
    """Write files with safe paths under root, ensuring each content ends with exactly one newline.
    Записати файли з безпечними шляхами під коренєм, гарантуючи, що кожен вміст закінчується рівно одним символом нового рядка."""
    written = []
    for rel_path, content in files.items():
        s_rel = safe_rel(rel_path)
        if s_rel is None:
            continue
        target = root / s_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Ensure content ends with exactly one newline / Гарантувати, що вміст закінчується рівно одним новим рядком
        clean_content = content.rstrip("\r\n") + "\n"
        target.write_text(clean_content, encoding="utf-8")
        written.append(s_rel)
    return sorted(written)


def default_check(root: Path) -> str | None:
    """Determine the default check command based on project files.
    Визначити команду перевірки за замовчуванням на основі файлів проєкту."""
    if (root / "Cargo.toml").exists():
        return "cargo build --quiet"
    # Check for any .py file under root / Перевірити на наявність будь-якого .py файлу в корені
    py_files = list(root.rglob("*.py"))
    if py_files:
        return f'"{sys.executable}" -m compileall -q .'
    return None


def assemble(text: str, root: Path, run_fix=None, check: str | None = None) -> dict:
    """Assemble a project from text and optionally run a fix command.
    Зібрати проєкт із тексту та опціонально запустити команду виправлення."""
    files = write_files(from_text(text), root)
    cmd = check or default_check(root)
    ok = run_fix(cmd) if (cmd and run_fix and files) else None
    return {"files": files, "check": cmd, "ok": ok}
