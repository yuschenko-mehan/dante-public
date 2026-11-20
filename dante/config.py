"""Settings for DANTE.

One source of truth: a `dante.toml` file plus environment variables.
API keys are never stored in the file — only in environment variables
(one per provider, e.g. QWEN_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path


@dataclass(frozen=True)
class Provider:
    """One model behind an OpenAI-compatible chat API."""

    name: str
    base_url: str
    model: str
    api_key_env: str
    # Optional "low"/"medium"/"high" thinking budget (OpenAI-style). None = model default.
    reasoning_effort: str | None = None
    # Optional cap on answer length for this provider (free tiers limit tokens per minute).
    max_tokens: int | None = None
    # Money: paid providers are OFF unless allowed, and every paid task needs two confirmations.
    paid: bool = False
    price_in_usd_per_m: float | None = None   # USD per 1M input tokens (must be set to use a paid model)
    price_out_usd_per_m: float | None = None  # USD per 1M output tokens
    # Local models (Ollama) need no key. Backup models are used only when all main ones fail.
    needs_key: bool = True
    backup: bool = False

    @property
    def api_key(self) -> str | None:
        if not self.needs_key:
            return "local"
        return os.environ.get(self.api_key_env) or _file_keys().get(self.api_key_env) or None


# keys.txt next to the dante package: lines like  GEMINI_API_KEY=...
KEYS_FILE = Path(__file__).resolve().parents[1] / "keys.txt"
# models the author added in the "Моделі" window (see models_hub.py); no keys inside
MODELS_FILE = Path(__file__).resolve().parents[1] / "models.json"
# DANTE's memory of past mistakes / пам'ять Данте про минулі помилки (see lessons.py)
LESSONS_FILE = Path(__file__).resolve().parents[1] / "lessons.json"


def _file_keys(path: Path | None = None) -> dict[str, str]:
    path = path or KEYS_FILE
    if not path.exists():
        return {}
    keys = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            keys[name.strip()] = value
    return keys


DEFAULT_PROVIDERS: tuple[Provider, ...] = (
    Provider("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen-plus", "QWEN_API_KEY", paid=True),
    Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite", "GEMINI_API_KEY"),
    Provider("claude", "https://api.anthropic.com/v1", "claude-sonnet-5-5", "ANTHROPIC_API_KEY", paid=True),
    # Free tiers (limits apply; check `dante models` for current model names):
    Provider("groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "GROQ_API_KEY",
             reasoning_effort="low", max_tokens=4000),  # free tier ~8000 tokens/min; low effort leaves room for code
    Provider("qwen-groq", "https://api.groq.com/openai/v1", "qwen/qwen3.8-27b", "GROQ_API_KEY", max_tokens=1000),  # Groq free tier: 1000 output tokens/min
    Provider("mistral", "https://api.mistral.ai/v1", "mistral-small-latest", "MISTRAL_API_KEY", paid=True),
    Provider("openrouter", "https://openrouter.ai/api/v1", "openrouter/free", "OPENROUTER_API_KEY"),
    # Individual free models on OpenRouter (all share one OpenRouter key and its daily free limit):
    Provider("gemma", "https://openrouter.ai/api/v1", "google/gemma-4-31b-it:free", "OPENROUTER_API_KEY"),
    Provider("nemotron", "https://openrouter.ai/api/v1", "nvidia/nemotron-3-ultra-550b-a55b:free", "OPENROUTER_API_KEY"),
    Provider("ernie", "https://openrouter.ai/api/v1", "baidu/ernie-5.5-flash-preview:free", "OPENROUTER_API_KEY"),
    Provider("north-code", "https://openrouter.ai/api/v1", "cohere/north-mini-code:free", "OPENROUTER_API_KEY"),
    # More free tiers (18.11.2026). Free = no card on the account; when a free quota ends the
    # provider answers 402/"insufficient balance" and DANTE switches it off for the run (wallet rule).
    Provider("nvidia", "https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct", "NVIDIA_API_KEY"),
    Provider("glm", "https://api.z.ai/api/paas/v4", "glm-4.7-flash", "ZAI_API_KEY"),
    Provider("siliconflow", "https://api.siliconflow.com/v1", "Qwen/Qwen2.5-Coder-32B-Instruct", "SILICONFLOW_API_KEY"),
    Provider("deepseek", "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY"),
    Provider("plamo", "https://api.platform.preferredai.jp/v1", "plamo-3.0-prime", "PLAMO_API_KEY"),
    # Local model on this PC via Ollama: free, works offline; BACKUP only (slower, weaker on a 2 GB GPU).
    Provider("local", "http://127.0.0.1:11434/v1", "qwen2.5-coder:3b", "", needs_key=False, backup=True, max_tokens=2000),
    Provider("local-7b", "http://127.0.0.1:11434/v1", "dante-coder-7b", "", needs_key=False, backup=True, max_tokens=2000),  # stronger, slower (5.7 tok/s on the author's PC)
)


@dataclass(frozen=True)
class Settings:
    providers: tuple[Provider, ...] = DEFAULT_PROVIDERS
    # Order in which models are used. Providers without a key are skipped.
    order: tuple[str, ...] = (
        "gemini", "groq", "nvidia", "glm", "qwen-groq", "deepseek", "siliconflow",
        "nemotron", "gemma", "ernie", "north-code", "plamo",
        "qwen", "claude", "mistral", "openrouter", "local", "local-7b",
    )
    # "rotate": each new attempt goes to the next model (a fresh pair of eyes on the error).
    # "fallback": always start with the first model; next one only if a call fails.
    strategy: str = "rotate"

    temperature: float = 0.2
    max_tokens: int = 4096
    request_timeout_s: int = 120

    max_fix_attempts: int = 3
    # Own failed attempts before the Academy is asked (2 = after two mistakes, ask on the third).
    # Власних невдалих спроб до звернення в Академію (2 = після двох помилок, на третю — Академія).
    solo_attempts: int = 2
    command_timeout_s: int = 300

    # Money (see wallet.py). Paid models are never used unless allow_paid = true AND the
    # author confirms the estimated cost twice. Limits in USD; 0 = nothing may be spent.
    allow_paid: bool = False
    budget_task_usd: float = 0.0
    budget_day_usd: float = 0.0
    budget_month_usd: float = 0.0
    uah_per_usd: float | None = None   # exchange rate for showing sums in hryvnias (set by the author)
    task_time_limit_s: int = 900        # stop a task that runs longer than this

    audit_dir: str = "audit"
    # Files the LLM is never allowed to write, relative to the project root.
    protected_paths: tuple[str, ...] = field(default=(".env", ".git", "dante.toml", "keys.txt", "models.json", "lessons.json"))

    def active_providers(self) -> list[Provider]:
        """Providers in `order` that have an API key set."""
        by_name = {p.name: p for p in self.providers}
        missing = [n for n in self.order if n not in by_name]
        if missing:
            raise ValueError(f"Unknown provider(s) in order: {', '.join(missing)}")
        return [
            by_name[n] for n in self.order
            if by_name[n].api_key and (self.allow_paid or not by_name[n].paid)
        ]


def hub_providers(path: Path | None = None) -> tuple[Provider, ...]:
    """Models added in the "Моделі" window. Local ones (this PC) are backups, like the built-in local models."""
    from dante import models_hub
    out = []
    for m in models_hub.load(path or MODELS_FILE):
        local = m["base_url"].startswith(("http://localhost", "http://127.0.0.1"))
        out.append(Provider(m["name"], m["base_url"], m["model"], m["key_env"], paid=m["paid"],
                            price_in_usd_per_m=m["price_in"] or None, price_out_usd_per_m=m["price_out"] or None,
                            needs_key=m["needs_key"], backup=local))
    return tuple(out)


def with_hub(s: Settings, models_path: Path | None = None) -> Settings:
    """Add the author's own models: providers by name (built-ins win), order before the backup models."""
    names = {p.name for p in s.providers}
    extra = [p for p in hub_providers(models_path) if p.name not in names]
    if not extra:
        return s
    order = list(s.order)
    first_backup = next((i for i, n in enumerate(order) if n in ("local", "local-7b")), len(order))
    new = [p.name for p in extra if p.name not in order]
    order[first_backup:first_backup] = new
    return replace(s, providers=tuple(s.providers) + tuple(extra), order=tuple(order))


def load_settings(path: Path | None = None, models_path: Path | None = None) -> Settings:
    """Load settings from a TOML file (missing file -> defaults; unknown keys -> error) plus models.json."""
    s = with_hub(_load_toml(path), models_path)
    import os
    if os.environ.get("DANTE_NO_ROUTING") == "1":
        return s
    from dante import routing
    return routing.apply_routing(s)


def _load_toml(path: Path | None = None) -> Settings:
    if path is None:
        path = Path("dante.toml")
    if not path.exists():
        return Settings()

    with path.open("rb") as f:
        data = tomllib.load(f)

    known = {f.name for f in fields(Settings)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unknown settings in {path}: {', '.join(sorted(unknown))}")

    if "providers" in data:
        # Merge: TOML entries override/add to the defaults by name.
        merged = {p.name: p for p in DEFAULT_PROVIDERS}
        for name, cfg in data["providers"].items():
            base = merged.get(name)
            values = {
                "base_url": cfg.get("base_url", base.base_url if base else None),
                "model": cfg.get("model", base.model if base else None),
                "api_key_env": cfg.get("api_key_env", base.api_key_env if base else None),
            }
            effort = cfg.get("reasoning_effort", base.reasoning_effort if base else None)
            cap = cfg.get("max_tokens", base.max_tokens if base else None)
            extra = {
                "needs_key": cfg.get("needs_key", base.needs_key if base else True),
                "backup": cfg.get("backup", base.backup if base else False),
            }
            money = {
                "paid": cfg.get("paid", base.paid if base else True),  # unknown new provider = paid (safe)
                "price_in_usd_per_m": cfg.get("price_in_usd_per_m", base.price_in_usd_per_m if base else None),
                "price_out_usd_per_m": cfg.get("price_out_usd_per_m", base.price_out_usd_per_m if base else None),
            }
            if None in values.values():
                raise ValueError(f"Provider '{name}' needs base_url, model and api_key_env")
            merged[name] = Provider(name=name, reasoning_effort=effort, max_tokens=cap, **money, **extra, **values)
        data["providers"] = tuple(merged.values())
    for key in ("order", "protected_paths"):
        if key in data:
            data[key] = tuple(data[key])
    if data.get("strategy", "rotate") not in ("rotate", "fallback"):
        raise ValueError("strategy must be 'rotate' or 'fallback'")
    return Settings(**data)
