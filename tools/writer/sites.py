"""Site definitions and utilities for web AI chats. / Визначення сайтів та утиліти для веб-чатів ШІ."""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Any
from urllib.parse import urlparse

@dataclass(frozen=True)
class Site:
    """A known AI chat site definition. / Визначення відомого сайту чату ШІ."""
    id: str
    name: str
    url: str
    host: str

# Tuple of known sites / Кортеж відомих сайтів
SITES: Tuple[Site, ...] = (
    Site("chatgpt", "ChatGPT", "https://chatgpt.com/", "chatgpt.com"),
    Site("gemini", "Gemini", "https://gemini.google.com/app", "gemini.google.com"),
    Site("qwen", "Qwen", "https://chat.qwen.ai/", "chat.qwen.ai"),
    Site("deepseek", "DeepSeek", "https://chat.deepseek.com/", "chat.deepseek.com"),
    Site("mistral", "Mistral Le Chat", "https://chat.mistral.ai/chat", "chat.mistral.ai"),
)

def find(url: str) -> Optional[Site]:
    """Find a known site by URL host. / Знайти відомий сайт за хостом URL."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
    except Exception:
        return None
    
    for site in SITES:
        if hostname == site.host or hostname.endswith("." + site.host):
            return site
    return None

def looks_logged_out(url: str, title: str = "") -> bool:
    """Check if the page looks like a sign-in or login page. / Перевірити, чи сторінка схожа на сторінку входу."""
    combined = f"{url} {title}".lower()
    keywords = ["sign-in", "signin", "log-in", "login", "auth", "accounts.google.com", "sign_in"]
    for kw in keywords:
        if kw in combined:
            return True
    return False

def chat_tabs(tabs: List[dict]) -> List[dict]:
    """Filter and enrich tab list for known AI chat sites. / Відфільтрувати та збагатити список вкладки для відомих сайтів ШІ."""
    out = []
    for tab in tabs:
        if tab.get("type") != "page":
            continue
        url = tab.get("url", "")
        title = tab.get("title", "")
        site = find(url)
        if site:
            logged_out = looks_logged_out(url, title)
            new_tab = dict(tab)
            new_tab["site"] = site.id
            new_tab["ready"] = not logged_out
            out.append(new_tab)
    return out

def status_text(found: List[dict], lang: str = "uk") -> str:
    """Generate status text for all known sites. / Згенерувати текст статусу для всіх відомих сайтів."""
    found_map = {}
    for item in found:
        site_id = item.get("site")
        if site_id:
            found_map[site_id] = item.get("ready", False)

    lines = []
    for site in SITES:
        is_found = site.id in found_map
        ready = found_map.get(site.id, False)

        if lang == "uk":
            if is_found and ready:
                status = "готовий"
            else:
                status = "немає входу"
        else:
            if is_found and ready:
                status = "ready"
            else:
                status = "not signed in"

        lines.append(f"{site.name}: {status}")

    return "\n".join(lines)
