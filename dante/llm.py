"""Bridge to a language model.

Uses the OpenAI-compatible chat API over plain HTTP (standard library only),
so one client covers Qwen, OpenAI, OpenRouter and local servers.
`FakeLLM` returns scripted answers for dry runs and tests — no network, no cost.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from dante import __version__
from dante.config import Provider, Settings

# Some providers (Groq behind Cloudflare) reject the default Python user agent.
USER_AGENT = f"DANTE/{__version__}"


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0


class LLM(Protocol):
    def complete(self, system: str, user: str) -> LLMResponse: ...


class LLMError(RuntimeError):
    pass


class QuotaExhausted(LLMError):
    """Free quota/credit is over: this provider must not be used again (never switch to paid)."""


_QUOTA_WORDS = ("insufficient", "balance", "quota exceeded", "exceeded your", "credit", "payment required",
                "billing", "top up", "recharge")


class OpenAICompatibleLLM:
    def __init__(self, provider: Provider, settings: Settings):
        if not provider.api_key:
            raise LLMError(
                f"No API key for {provider.name}. Set the environment variable {provider.api_key_env}."
            )
        self.p = provider
        self.s = settings
        self.max_wait_s = 65.0  # MultiLLM lowers it when other models can take over

    def complete(self, system: str, user: str, max_tokens: int | None = None,
                 timeout_s: int | None = None, retries: int = 3) -> LLMResponse:
        payload = {
            "model": self.p.model,
            "temperature": self.s.temperature,
            "max_tokens": max_tokens or self.p.max_tokens or self.s.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.p.reasoning_effort:
            payload["reasoning_effort"] = self.p.reasoning_effort
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.p.base_url.rstrip("/") + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.p.api_key}",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )

        last_error: Exception | None = None
        attempt = 0
        rate_waits = 0
        while attempt < retries:
            start = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=timeout_s or self.s.request_timeout_s) as r:
                    data = json.loads(r.read().decode("utf-8"))
                usage = data.get("usage") or {}
                return LLMResponse(
                    content=data["choices"][0]["message"]["content"] or "",
                    model=f"{self.p.name}:{data.get('model', self.p.model)}",
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    latency_s=round(time.monotonic() - start, 3),
                )
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:600]
                last_error = LLMError(f"HTTP {e.code}: {detail}")
                low = detail.lower()
                if e.code == 402 or (e.code in (400, 403, 429) and any(w in low for w in _QUOTA_WORDS)
                                     and "rate limit" not in low and "per minute" not in low):
                    raise QuotaExhausted(f"{self.p.name}: free quota/credit is over (HTTP {e.code}): {detail[:200]}")
                if e.code == 429 and "too large" not in detail.lower() and rate_waits < 5:
                    # Rate limit: wait as long as the server asks, not counted as an attempt.
                    # A long wait is not worth it when other models can answer now.
                    wait = _retry_after(e, detail)
                    if wait > self.max_wait_s:
                        raise LLMError(f"{self.p.name}: rate limited, free again in ~{int(wait)} s")
                    rate_waits += 1
                    time.sleep(wait)
                    continue
                if e.code not in (500, 502, 503, 504):
                    break  # not worth retrying (bad key, bad request, too large)
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
                last_error = LLMError(f"{type(e).__name__}: {e}")
            attempt += 1
            if attempt < retries:
                time.sleep(2 ** (attempt - 1))
        raise last_error or LLMError(f"Unknown error from {self.p.name}")


class FakeLLM:
    """Returns scripted answers in order. Used by --dry-run and tests."""

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        self.calls.append((system, user))
        if not self.answers:
            raise LLMError("FakeLLM has no more scripted answers")
        return LLMResponse(content=self.answers.pop(0), model="fake")


def _retry_after(e: urllib.error.HTTPError, detail: str) -> float:
    """Seconds to wait after HTTP 429, from the Retry-After header or the message text."""
    header = e.headers.get("retry-after") if e.headers else None
    try:
        if header:
            return min(float(header) + 0.5, 65.0)
    except ValueError:
        pass
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", detail)
    if m:
        return min(int(m.group(1) or 0) * 60 + float(m.group(2)) + 0.5, 65.0)
    return 10.0


def list_models(provider: Provider, timeout_s: int = 30) -> list[str]:
    """Ask a provider which models it offers. Also proves the key works. Free."""
    req = urllib.request.Request(
        provider.base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {provider.api_key}", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise LLMError(f"{type(e).__name__}: {e}") from e
    return sorted(m.get("id", "?").removeprefix("models/") for m in data.get("data", []))


class MultiLLM:
    """Several models behind one interface.

    strategy="rotate":   call N starts with model N (round robin), so a failed
                         attempt is retried by a different model.
    strategy="fallback": every call starts with the first model.
    In both cases, if a model errors (no credit, network, outage), the next one is tried.
    """

    def __init__(self, clients: list[tuple[str, LLM]], strategy: str = "rotate",
                 backups: list[tuple[str, LLM]] | None = None):
        if not clients and not backups:
            raise LLMError("No models available: set at least one API key (see `dante check`).")
        self.clients = clients
        self.backups = backups or []
        self.disabled: set[str] = set()
        self.strategy = strategy
        self._calls = 0
        self.errors: list[str] = []
        self.last_failures: list[str] = []
        if len(clients) + len(self.backups) > 1:
            for _name, c in clients:
                if hasattr(c, "max_wait_s"):
                    c.max_wait_s = 15.0

    def complete(self, system: str, user: str) -> LLMResponse:
        n = len(self.clients)
        start = (self._calls % n if self.strategy == "rotate" else 0) if n else 0
        self._calls += 1
        failures = []
        order = [self.clients[(start + i) % n] for i in range(n)] + self.backups
        for name, client in order:
            if name in self.disabled:
                continue
            try:
                resp = client.complete(system, user)
                self.last_failures = failures
                return resp
            except QuotaExhausted as e:
                self.disabled.add(name)  # free quota over: switch off for this run, never go paid
                failures.append(f"{name}: {e}")
            except LLMError as e:
                failures.append(f"{name}: {e}")
        self.errors.extend(failures)
        raise LLMError("All models failed: " + " | ".join(failures))


def build_llm(settings: Settings) -> MultiLLM:
    act = settings.active_providers()
    main = [(p.name, OpenAICompatibleLLM(p, settings)) for p in act if not p.backup]
    backups = [(p.name, OpenAICompatibleLLM(p, settings)) for p in act if p.backup]
    return MultiLLM(main, settings.strategy, backups)
