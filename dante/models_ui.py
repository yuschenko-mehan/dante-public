"""Logic behind the "Моделі" window: ready-made services, the model list, free checks.

No Tk here, so everything can be tested without a screen. Money rule: the window never sends
a chat request to a paid model (a check would cost money); asking for the list of models is free.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dante import config, models_hub
from dante.llm import USER_AGENT


@dataclass(frozen=True)
class Preset:
    id: str
    label_uk: str
    label_en: str
    base_url: str
    key_env: str          # "" = no key (local)
    signup: str           # where to get a key / the program
    paid: bool = False    # ticked by default (safe for unknown services)

    def label(self, lang: str) -> str:
        return self.label_uk if lang == "uk" else self.label_en

    @property
    def needs_key(self) -> bool:
        return bool(self.key_env)


# Only addresses checked against the services' own docs. Model names change often, so the
# form asks the service for its list ("Отримати список") instead of guessing.
PRESETS: tuple[Preset, ...] = (
    Preset("custom", "Свій сервіс (OpenAI-сумісний)", "Own service (OpenAI-compatible)", "", "MY_API_KEY", "", paid=True),
    Preset("ollama", "Ollama — модель на цьому ПК", "Ollama — model on this PC", "http://127.0.0.1:11434/v1", "",
           "https://ollama.com/library"),
    Preset("lmstudio", "LM Studio — модель на цьому ПК", "LM Studio — model on this PC", "http://127.0.0.1:1234/v1", "",
           "https://lmstudio.ai"),
    Preset("gemini", "Google Gemini (інша модель)", "Google Gemini (another model)",
           "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "https://aistudio.google.com/apikey"),
    Preset("groq", "Groq (інша модель)", "Groq (another model)", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
           "https://console.groq.com/keys"),
    Preset("openrouter", "OpenRouter (інша модель)", "OpenRouter (another model)", "https://openrouter.ai/api/v1",
           "OPENROUTER_API_KEY", "https://openrouter.ai/keys"),
    Preset("nvidia", "NVIDIA build (інша модель)", "NVIDIA build (another model)", "https://integrate.api.nvidia.com/v1",
           "NVIDIA_API_KEY", "https://build.nvidia.com"),
    Preset("cerebras", "Cerebras (дуже швидкі)", "Cerebras (very fast)", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY",
           "https://cloud.cerebras.ai"),
    Preset("sambanova", "SambaNova", "SambaNova", "https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY",
           "https://cloud.sambanova.ai"),
    Preset("mistral", "Mistral (безкоштовний план)", "Mistral (free plan)", "https://api.mistral.ai/v1", "MISTRAL_API_KEY",
           "https://console.mistral.ai/api-keys"),
    Preset("cohere", "Cohere", "Cohere", "https://api.cohere.ai/compatibility/v1", "COHERE_API_KEY",
           "https://dashboard.cohere.com/api-keys"),
    Preset("huggingface", "Hugging Face", "Hugging Face", "https://router.huggingface.co/v1", "HF_TOKEN",
           "https://huggingface.co/settings/tokens"),
)


def preset(pid: str) -> Preset:
    return next((p for p in PRESETS if p.id == pid), PRESETS[0])


def suggest_name(p: Preset, model: str, taken: set[str]) -> str:
    """A free, valid name like 'cerebras-llama-3-3-70b'."""
    import re
    tail = re.sub(r"[^a-z0-9]+", "-", model.lower().split("/")[-1]).strip("-")
    base = re.sub(r"-+", "-", f"{p.id if p.id != 'custom' else 'my'}-{tail}".strip("-"))[:28].strip("-") or "my-model"
    name, i = base, 2
    while name in taken or name in models_hub.BUILTIN_NAMES:
        name, i = f"{base[:26]}-{i}", i + 1
    return name


@dataclass
class Row:
    name: str
    model: str
    own: bool        # added by the author (can be changed or removed)
    has_key: bool    # key found (or not needed)
    paid: bool


def rows(models_path: Path | None = None, keys_path: Path | None = None) -> list[Row]:
    """All models DANTE knows: built-in first, then the author's own."""
    s = config.load_settings(Path("__no_toml__"), models_path)
    own = {m["name"] for m in models_hub.load(models_path or config.MODELS_FILE)}
    keys = config._file_keys(keys_path)
    import os
    out = []
    for p in s.providers:
        has = (not p.needs_key) or bool(os.environ.get(p.api_key_env) or keys.get(p.api_key_env))
        out.append(Row(p.name, p.model, p.name in own, has, p.paid))
    return sorted(out, key=lambda r: (r.own, r.name))


def _request(url: str, key: str, body: dict | None, timeout: float) -> dict:
    headers = {"User-Agent": USER_AGENT}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:200]
        if key:
            text = text.replace(key, "***")
        raise RuntimeError(f"HTTP {e.code}: {text}") from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"{type(e).__name__}: {e}") from None


def fetch_models(base_url: str, key: str, timeout: float = 20) -> list[str]:
    """Ask the service for its models (free). Also shows that the address and key work."""
    data = _request(base_url.rstrip("/") + "/models", key, None, timeout)
    items = data.get("data", data.get("models", [])) if isinstance(data, dict) else []
    names = {str(m.get("id") or m.get("name") or "").removeprefix("models/") for m in items if isinstance(m, dict)}
    return sorted(n for n in names if n)


def ping(base_url: str, model: str, key: str, paid: bool, timeout: float = 40) -> str:
    """One tiny chat request. Refused for paid models (it would cost money)."""
    if paid:
        raise PermissionError("paid")
    data = _request(base_url.rstrip("/") + "/chat/completions", key,
                    {"model": model, "max_tokens": 16, "temperature": 0,
                     "messages": [{"role": "user", "content": "Answer with one word: OK"}]}, timeout)
    return (data["choices"][0]["message"].get("content") or "").strip()[:60]
