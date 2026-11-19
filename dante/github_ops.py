"""Publish a project to GitHub: checks, bilingual texts, git / gh commands.
Викладання проєкту на GitHub: перевірки, двомовні тексти, команди git / gh.

Safety / Безпека:
- secrets are searched before every push; if found, nothing is sent
  секрети шукаються перед кожним викладанням; якщо знайдено — нічого не надсилається
- keys.txt, .env, dante.toml, models.json never go out (also checked in the whole git history)
  keys.txt, .env, dante.toml, models.json ніколи не викладаються (перевіряється і вся історія git)
- a new repository is private unless the author chose "public"
  новий репозиторій приватний, якщо автор не обрав «публічний»
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from dante import github_pub as G

# Where Windows installers put the tools / Куди їх ставлять інсталятори Windows
KNOWN = {
    "git": [r"C:\Program Files\Git\cmd\git.exe"],
    "gh": [r"C:\Program Files\GitHub CLI\gh.exe", r"C:\Program Files (x86)\GitHub CLI\gh.exe"],
}
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def find_tool(name: str) -> str | None:
    """Full path of git / gh, or None / Повний шлях до git / gh або None."""
    found = shutil.which(name)
    if found:
        return found
    for p in KNOWN.get(name, []):
        if Path(p).exists():
            return p
    return None


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> tuple[int, str]:
    """Run a command, return (exit code, output) / Виконати команду, повернути (код, вивід)."""
    tool = find_tool(cmd[0]) or cmd[0]
    env = dict(os.environ, GH_PROMPT_DISABLED="1", GIT_TERMINAL_PROMPT="0")
    try:
        r = subprocess.run([tool, *cmd[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env, creationflags=NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def github_user() -> str | None:
    """Login of the connected GitHub account / Логін підключеного акаунта GitHub."""
    if not find_tool("gh"):
        return None
    code, out = run(["gh", "api", "user", "--jq", ".login"], timeout=30)
    login = out.strip().splitlines()[-1] if code == 0 and out.strip() else ""
    return login if re.fullmatch(r"[A-Za-z0-9-]{1,39}", login) else None


def status() -> dict:
    """What is ready: git, gh, account / Що готово: git, gh, акаунт."""
    return {"git": find_tool("git"), "gh": find_tool("gh"), "user": github_user()}


def history_leaks(root: Path) -> list[str]:
    """Excluded files that were EVER committed (they would be pushed with history).
    Виключені файли, які колись потрапили в коміти (вони пішли б разом з історією)."""
    if not (root / ".git").exists():
        return []
    code, out = run(["git", "log", "--all", "--name-only", "--format="], cwd=root, timeout=120)
    if code != 0:
        return []
    bad = set()
    for line in out.splitlines():
        name = line.strip().split("/")[-1]
        if name and G._is_excluded(Path(name)):
            bad.add(line.strip())
    return sorted(bad)


def ensure_gitignore(root: Path) -> list[str]:
    """Add the safe lines to .gitignore, return what was added / Додати безпечні рядки в .gitignore."""
    path = root / ".gitignore"
    have = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    missing = [x for x in G.GITIGNORE.splitlines() if x and x not in have]
    if missing:
        text = "\n".join(have).rstrip("\n")
        path.write_text((text + "\n" if text else "") + "\n".join(missing) + "\n", encoding="utf-8")
    return missing


TEXTS_PROMPT = (
    "You write GitHub texts for a small project, in English AND Ukrainian. Answer ONLY with JSON: "
    '{"summary_en": "...", "summary_uk": "...", "description_en": "..."%s}. '
    "summary_* = one line (max 60 chars) saying what changed; description_en = one line (max 100 chars) about the "
    "project.%s Plain, friendly language for non-programmers too."
)
README_PART = (
    ', "readme_en": "...", "readme_uk": "..."',
    " readme_* = a short README in Markdown: title, what it does, how to run it, how to run the tests "
    "(Ukrainian one is a real translation, not a summary).",
)


def _fallback(root: Path, task: str, need_readme: bool) -> dict:
    """Texts without a model / Тексти без моделі."""
    name = root.name
    files = G.files_to_publish(root)[:30]
    listing = "\n".join(f"- `{f}`" for f in files)
    d = {"summary_uk": (task or "Оновлення проєкту")[:60], "summary_en": "Project update",
         "description_en": f"{name} — made with DANTE"}
    if need_readme:
        d["readme_en"] = f"# {name}\n\nMade with DANTE.\n\n## Files\n\n{listing}\n\n## Tests\n\n    python -m unittest\n"
        d["readme_uk"] = f"# {name}\n\nЗроблено з Данте.\n\n## Файли\n\n{listing}\n\n## Тести\n\n    python -m unittest\n"
    return d


def make_texts(root: Path, task: str, llm, need_readme: bool) -> dict:
    """Bilingual summary, description and (if needed) README from a free model.
    Двомовні підсумок, опис і (якщо треба) README від безкоштовної моделі."""
    base = _fallback(root, task, need_readme)
    if llm is None:
        return base
    files = G.files_to_publish(root)
    sample = ""
    for rel in files[:12]:
        if rel.endswith((".py", ".rs", ".js", ".ts", ".md", ".toml", ".txt", ".bat", ".ps1", ".html")):
            sample += f"\n--- {rel} ---\n" + (root / rel).read_text(encoding="utf-8", errors="replace")[:1200]
        if len(sample) > 7000:
            break
    extra = README_PART if need_readme else ("", "")
    prompt = f"PROJECT: {root.name}\nLAST TASK: {task or '-'}\nFILES: {', '.join(files[:60])}\n{sample}"
    try:
        resp = llm.complete(TEXTS_PROMPT % extra, prompt)
        m = re.search(r"\{.*\}", resp.content, re.S)
        data = json.loads(m.group(0)) if m else {}
    except Exception:  # model down: plain texts / модель недоступна: прості тексти
        return base
    for k in base:
        v = data.get(k)
        if isinstance(v, str) and v.strip() and not G.find_secrets(v):
            base[k] = v.strip()
    return base


def publish(root: Path, visibility: str = "private", task: str = "", llm=None, new_ok: bool = False,
            out=print) -> int:
    """Check, describe and push the project. 0 = done.
    Перевірити, описати й викласти проєкт. 0 = готово.
    new_ok: creating a NEW repository was confirmed by the author / створення НОВОГО репозиторію підтверджено."""
    root = Path(root).resolve()
    st = status()
    if not st["git"]:
        out("✗ Немає git / git is missing: встановіть у формі GitHub.")
        return 2
    if not st["gh"] or not st["user"]:
        out("✗ GitHub не підключено / not connected: кнопка «Підключити GitHub».")
        return 2
    leaks = G.scan_project(root)
    if leaks:
        out("✗ Знайдено схожі на секрети рядки — нічого не викладено / Possible secrets found — nothing was sent:")
        for rel, kind, line in leaks[:20]:
            out(f"   {rel}:{line}  ({kind})")
        out("   Приберіть ключі з коду (тримайте їх у keys.txt) / Move keys to keys.txt.")
        return 3
    hist = history_leaks(root)
    if hist:
        out("✗ У історії git є службові файли / Private files are in the git history: " + ", ".join(hist[:10]))
        out("   Викладати не можна, доки їх не прибрати з історії / Cannot publish until they are removed.")
        return 3
    has_git = (root / ".git").exists()
    code, _ = run(["git", "remote", "get-url", "origin"], cwd=root) if has_git else (1, "")
    has_remote = code == 0
    if not has_remote and not new_ok:
        out("Новий репозиторій потребує вашого підтвердження / A new repository needs your confirmation:")
        out("   натисніть «Викласти на GitHub» у вікні / press “Publish to GitHub” in the window.")
        return 4
    added = ensure_gitignore(root)
    if added:
        out(".gitignore: + " + ", ".join(added))
    need_readme = not (root / "README.md").exists() or not (root / "README.uk.md").exists()
    texts = make_texts(root, task, llm, need_readme)
    if need_readme:
        for name, text in G.readme_files(texts["readme_uk"], texts["readme_en"]).items():
            if not (root / name).exists():
                (root / name).write_text(text, encoding="utf-8")
                out(f"+ {name}")
    if not has_git:
        rc, txt = run(["git", "init", "-b", "main"], cwd=root)
        if rc != 0:
            out(txt)
            return 1
    # commit author = the GitHub account (private noreply e-mail) / автор комітів = акаунт GitHub
    if run(["git", "config", "user.email"], cwd=root)[0] != 0:
        code, uid = run(["gh", "api", "user", "--jq", ".id"])
        uid = uid.strip() if code == 0 and uid.strip().isdigit() else "0"
        run(["git", "config", "user.name", st["user"]], cwd=root)
        run(["git", "config", "user.email", f"{uid}+{st['user']}@users.noreply.github.com"], cwd=root)
    files = G.files_to_publish(root)
    message = G.commit_message(texts["summary_uk"], texts["summary_en"], files)
    repo = G.repo_name(root.name)
    cmds = G.publish_commands(repo, visibility, has_git=True, has_remote=has_remote, message=message,
                              description=texts["description_en"][:300])
    for cmd in cmds:
        out("PS> " + " ".join(cmd[:4]) + (" …" if len(cmd) > 4 else ""))
        rc, txt = run(cmd, cwd=root, timeout=600)
        if rc != 0 and cmd[:2] == ["git", "commit"] and ("nothing to commit" in txt or "нічого" in txt):
            out("   (нових змін немає / nothing new to commit)")
            continue
        if rc != 0:
            out(txt.strip()[-1500:])
            out("✗ Не вдалося / Failed.")
            return 1
    rc, url = run(["gh", "repo", "view", "--json", "url", "--jq", ".url"], cwd=root, timeout=60)
    out(f"✓ Викладено / Published: {url.strip() if rc == 0 else repo}")
    out(f"   {texts['summary_uk']}  /  {texts['summary_en']}")
    return 0
