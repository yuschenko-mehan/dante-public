"""Safe, bilingual publishing of a project to GitHub.
Безпечна двомовна публікація проєкту на GitHub.

Pure logic only (no network, no git calls). Python standard library only.
Лише чиста логіка (без мережі, без викликів git). Тільки стандартна бібліотека Python.
"""

import os
import re
from pathlib import Path

# Excluded directories / Виключені теки
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    "audit",
    "node_modules",
    ".venv",
    "venv",
    "chrome-dante",
    ".pytest_cache",
}

# Excluded file names / Виключені назви файлів
EXCLUDE_FILES = {
    "keys.txt",
    ".env",
    "dante.toml",
    "models.json",
}

# Excluded file extensions / Виключені розширення файлів
EXCLUDE_EXTENSIONS = {".pem", ".key", ".pfx", ".p12"}
# Excluded file name prefixes / Виключені префікси назв файлів
EXCLUDE_PREFIXES = ("id_rsa", "id_ed25519")

# Gitignore template content / Вміст шаблону gitignore
GITIGNORE = "\n".join([
    "keys.txt",
    ".env",
    "dante.toml",
    "models.json",
    "audit/",
    "__pycache__/",
    "*.pyc",
    "chrome-dante/",
]) + "\n"

# Secret detection regex patterns / Регулярні вирази для пошуку секретів
SECRET_PATTERNS = {
    "github": re.compile(r"ghp_[A-Za-z0-9]{36}"),
    "github_pat": re.compile(r"github_pat_[A-Za-z0-9_]{50,}"),
    "openai": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "groq": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "google": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "huggingface": re.compile(r"hf_[A-Za-z0-9]{30,}"),
    "nvidia": re.compile(r"nvapi-[A-Za-z0-9_-]{20,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # NAME_API_KEY=value, TOKEN=value, X_SECRET = value (8+ chars, not $VAR / %VAR%)
    # НАЗВА_API_KEY=значення, TOKEN=значення, X_SECRET = значення (8+ символів, не $VAR / %VAR%)
    "key_assignment": re.compile(r"^\s*(?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN|SECRET)\s*=\s*[^\s$%]\S{7,}"),
}

def _is_excluded(path: Path) -> bool:
    """Check if a file path is excluded / Перевірити, чи шлях до файлу виключено"""
    name = path.name
    if name in EXCLUDE_FILES:
        return True
    if any(name.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
        return True
    if any(name.startswith(pre) for pre in EXCLUDE_PREFIXES):
        return True
    return False


def files_to_publish(root, max_bytes=50 * 1024 * 1024):
    """Files that may go to GitHub (secrets and junk left out).
    Файли, які можна викладати на GitHub (без секретів і сміття)."""
    root_path = Path(root)
    result = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune excluded folders before walking into them (node_modules can be huge)
        # Відкинути виключені теки ще до обходу (node_modules буває величезною)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            p = Path(dirpath) / name
            if p.is_symlink() or not p.is_file() or _is_excluded(p):
                continue
            try:
                if p.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            result.append(p.relative_to(root_path).as_posix())
    return sorted(result)


def find_secrets(text):
    """Find secrets in text lines / Знайти секрети в рядках тексту"""
    lines = text.splitlines()
    found = []
    pattern_order = [
        "github",
        "github_pat",
        "openai",
        "groq",
        "google",
        "huggingface",
        "nvidia",
        "private_key",
        "key_assignment",
    ]
    for idx, line in enumerate(lines, 1):
        line_secrets = set()
        for name in pattern_order:
            if SECRET_PATTERNS[name].search(line):
                line_secrets.add(name)
        for name in pattern_order:
            if name in line_secrets:
                found.append((name, idx))
    return found


def scan_project(root):
    """Scan project files for secrets / Сканувати файли проєкту на наявність секретів"""
    root_path = Path(root)
    files = files_to_publish(root)
    all_secrets = []
    for rel in files:
        p = root_path / rel
        try:
            data = p.read_bytes()  # read once / читаємо один раз
        except OSError:
            continue
        if b"\x00" in data[:8192]:  # binary file / двійковий файл
            continue
        text = data.decode("utf-8", errors="replace")
        for name, line in find_secrets(text):
            all_secrets.append((rel, name, line))
    return all_secrets


# Ukrainian to Latin transliteration map / Карта транслітерації з української на латиницю
TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ie',
    'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i', 'к': 'k', 'л': 'l',
    'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '',
    'ю': 'iu', 'я': 'ia'
}


def repo_name(folder):
    """Generate a GitHub-safe repository name / Згенерувати безпечну для GitHub назву репозиторію"""
    s = "".join(
        TRANSLIT_MAP.get(ch, "" if ch in ("'", "’", "ʼ") else ch)
        for ch in folder.lower()
    )
    s = re.sub(r"[^a-z0-9._]+", "-", s)
    s = s.strip("-.")
    if len(s) > 100:
        s = s[:100].strip("-.")
    return s or "dante-project"


def commit_message(summary_uk, summary_en, files):
    """Format a bilingual commit message / Відформатувати двомовне повідомлення коміту"""
    su = " ".join(summary_uk.strip().split())
    en = " ".join(summary_en.strip().split())
    if not su or not en:
        raise ValueError
    line1 = f"{en} / {su}"
    if len(line1) > 72:
        line1 = en[:72]
    lines = [line1, "", f"UK: {su}", f"EN: {en}", "", "Files / Файли:"]
    if len(files) <= 20:
        lines += [f"- {f}" for f in files]
    else:
        lines += [f"- {f}" for f in files[:20]]
        lines.append(f"- … +{len(files) - 20}")
    lines.append("Published by DANTE")
    return "\n".join(lines)


def publish_commands(repo, visibility, has_git, has_remote, message, description=""):
    """Generate git and gh CLI publishing commands / Згенерувати команди git та gh CLI для публікації"""
    if visibility not in ("private", "public"):
        raise ValueError
    if repo != repo_name(repo):
        raise ValueError
    cmds = []
    if not has_git:
        cmds.append(["git", "init", "-b", "main"])
    cmds.append(["git", "add", "-A"])
    cmds.append(["git", "commit", "-m", message])
    flag = "--private" if visibility == "private" else "--public"
    if not has_remote:
        cmd = ["gh", "repo", "create", repo, flag, "--source", ".", "--remote", "origin", "--push"]
        if description:
            cmd.extend(["--description", description])
        cmds.append(cmd)
    else:
        cmds.append(["git", "push", "-u", "origin", "HEAD"])
    return cmds


def readme_files(readme_uk, readme_en):
    """Generate bilingual README files mapping / Згенерувати мапу двомовних файлів README"""
    uk = readme_uk.rstrip("\n") + "\n"
    en = readme_en.rstrip("\n") + "\n"
    uk_link = "🇬🇧 [English](README.md)"
    en_link = "🇺🇦 [Українською](README.uk.md)"
    if not uk.startswith(uk_link + "\n"):
        uk = f"{uk_link}\n\n{uk}"
    if not en.startswith(en_link + "\n"):
        en = f"{en_link}\n\n{en}"
    return {"README.md": en, "README.uk.md": uk}
