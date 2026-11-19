"""DANTE updater module: self-updates from GitHub releases safely.
Модуль оновлення ДАНТЕ: безпечне самооновлення з релізів на GitHub.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime, timedelta  # datetime and timedelta for time calculations / datetime та timedelta для обчислень часу
from pathlib import Path

# Repository constants / Константи репозиторію
REPO = "yuschenko-mehan/dante-public"
API_URL = "https://api.github.com/repos/yuschenko-mehan/dante-public/releases/latest"
TRUSTED = "https://github.com/yuschenko-mehan/dante-public/releases/download/"

# Files of the author that an update never overwrites
# Файли автора, які оновлення ніколи не перезаписує
KEEP = {
    "keys.txt",
    "dante.toml",
    "models.json",
    "lessons.json",
    "idle.json",
    "contest.json",
    "settings.json",
    "github.json",
}


def parse_version(s: str) -> tuple[int, ...]:
    """Parse version string into a tuple of integers.
    Розпарсити рядок версії в кортеж цілих чисел.
    """
    # Remove leading 'v' or 'V' if present / Видалити початковий 'v' або 'V', якщо він є
    if s.startswith(("v", "V")):
        s = s[1:]
    parts = s.split(".")
    res: list[int] = []
    for p in parts:
        if not p.isdigit():
            return ()
        res.append(int(p))
    return tuple(res) if res else ()


def is_newer(remote: str, local: str) -> bool:
    """Check if remote version is newer than local version.
    Перевірити, чи віддалена версія новіша за локальну.
    """
    r_ver = parse_version(remote)
    l_ver = parse_version(local)
    if not r_ver or not l_ver:
        return False
    return r_ver > l_ver


def pick_release(rel: dict) -> dict | None:
    """Pick and validate release dictionary from GitHub API.
    Обрати та перевірити словник релізу з API GitHub.
    """
    if not isinstance(rel, dict):
        return None
    if rel.get("draft") or rel.get("prerelease"):
        return None

    tag_name = rel.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name:
        return None

    version = tag_name.lstrip("vV")
    if not parse_version(version):
        return None

    assets = rel.get("assets")
    if not isinstance(assets, list):
        return None

    zip_name = f"dante-{version}.zip"
    sha_name = f"dante-{version}.zip.sha256"

    zip_url = None
    sha_url = None

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        if not url.startswith(TRUSTED):
            continue
        if name == zip_name:
            zip_url = url
        elif name == sha_name:
            sha_url = url

    if not zip_url or not sha_url:
        return None

    notes = rel.get("body") if isinstance(rel.get("body"), str) else ""

    return {
        "version": version,
        "zip_url": zip_url,
        "sha_url": sha_url,
        "notes": notes,
    }


def check(local_version: str, fetch_json) -> dict | None:
    """Check for updates using fetch_json function.
    Перевірити наявність оновлень за допомогою функції fetch_json.
    """
    try:
        data = fetch_json(API_URL)
        rel = pick_release(data)
        if rel and is_newer(rel["version"], local_version):
            return rel
    except Exception:
        return None
    return None


def verify(data: bytes, sha_text: str) -> bool:
    """Verify data against sha256 checksum text.
    Перевірити дані за текстом контрольної суми sha256.
    """
    if not isinstance(sha_text, str) or not sha_text.strip():
        return False
    expected = sha_text.strip().split()[0].lower()
    actual = hashlib.sha256(data).hexdigest().lower()
    return expected == actual


def install(zip_bytes: bytes, app_dir: Path, backup_dir: Path) -> list[str]:
    """Safely install update from zip bytes.
    Безпечно встановити оновлення з байтів zip.
    """
    # Load zip into memory / Завантажити zip у пам'ять
    zip_buffer = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_buffer, "r") as z:
        # First pass: validate all members / Перший прохід: перевірити всі елементи
        for info in z.infolist():
            name = info.filename
            # Reject absolute paths, drive letters, or any ".." traversal / Відхилити абсолютні шляхи, букви диска або ".."
            p = Path(name)
            if p.is_absolute() or ".." in p.parts or any(sep in name for sep in ("/", "\\")) and p.drive:
                raise ValueError(f"Dangerous path in zip: {name}")
            if ":" in name or name.startswith("/") or name.startswith("\\"):
                raise ValueError(f"Dangerous path in zip: {name}")

        written: list[str] = []
        # Second pass: write files / Другий прохід: запис файлів
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or name.endswith("/"):
                continue

            rel_path = Path(name).as_posix()  # use forward slashes / використати прямі слеші
            target_path = app_dir / rel_path
            file_name = Path(name).name

            # Skip author-kept files if they already exist / Пропустити файли, які автор зберігає, якщо вони існують
            if file_name in KEEP and target_path.exists():
                continue

            # Backup existing file if present / Резервне копіювання існуючого файлу, якщо він є
            if target_path.exists():
                backup_path = backup_dir / rel_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_bytes(target_path.read_bytes())

            # Write new file / Записати новий файл
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(z.read(info))
            written.append(rel_path)

        return sorted(written)


def rollback(app_dir: Path, backup_dir: Path) -> int:
    """Rollback installed files from backup directory.
    Відкотити встановлені файли з директорії резервних копій.
    """
    if not backup_dir.exists():
        return 0
    count = 0
    for src in backup_dir.rglob("*"):
        if src.is_file():
            rel_path = src.relative_to(backup_dir)
            dst = app_dir / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            count += 1
    return count


def due(last_check: str | None, now: datetime) -> bool:
    """Check if an update check is due.
    Перевірити, чи настав час перевірки оновлень.
    """
    if last_check is None:
        return True
    try:
        dt = datetime.fromisoformat(last_check)
    except Exception:
        return True
    # At least 20 hours must have passed / Має пройти принаймні 20 годин
    return (now - dt) >= timedelta(hours=20)


# --- Step 2: download, policy, run / Крок 2: завантаження, налаштування, запуск (Claude) ---
import json as _json
import urllib.request as _urlreq

KEEP.add("update.json")
DEFAULT_POLICY = {"auto_check": True, "auto_install": False, "last_check": None}


def _get(url: str, timeout: int) -> bytes:
    """HTTP GET with our User-Agent / HTTP GET з нашим User-Agent."""
    req = _urlreq.Request(url, headers={"User-Agent": "DANTE-updater"})
    with _urlreq.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_json(url: str, timeout: int = 20) -> dict:
    """Download and parse JSON / Завантажити й розібрати JSON."""
    return _json.loads(_get(url, timeout).decode("utf-8"))


def fetch_bytes(url: str, timeout: int = 120) -> bytes:
    """Download bytes / Завантажити байти."""
    return _get(url, timeout)


def load_policy(path: Path) -> dict:
    """Update settings with defaults; a broken file gives defaults / Налаштування оновлень; зіпсований файл — типові."""
    p = dict(DEFAULT_POLICY)
    try:
        d = _json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(d, dict):
            p.update(d)
    except Exception:
        pass
    return p


def save_policy(path: Path, policy: dict) -> None:
    """Save update settings / Зберегти налаштування оновлень."""
    Path(path).write_text(_json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")


def run_update(app_dir: Path, local_version: str, *, install_now: bool, fetch_json=None, fetch_bytes=None, now=None) -> str:
    """Check (and maybe install) the newest release; returns a short status.
    Перевірити (і, можливо, встановити) найновіший реліз; повертає короткий стан."""
    import sys
    me = sys.modules[__name__]
    fj = fetch_json or me.fetch_json
    fb = fetch_bytes or me.fetch_bytes
    app_dir = Path(app_dir)
    pol_path = app_dir / "update.json"
    pol = load_policy(pol_path)
    pol["last_check"] = (now or datetime.now()).isoformat()
    save_policy(pol_path, pol)
    rel = check(local_version, fj)
    if rel is None:
        return "up-to-date"
    if not install_now:
        return f"available {rel['version']}"
    try:
        data = fb(rel["zip_url"])
        sha = fb(rel["sha_url"]).decode("utf-8", "replace")
    except Exception:
        return "offline"
    if not verify(data, sha):
        return "bad-checksum"
    install(data, app_dir, app_dir / "update-backup" / local_version)
    return f"installed {rel['version']}"
