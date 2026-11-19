"""Wallet: no money is ever spent without the author's knowledge.

Rules (from the author, mandatory):
- Free models only by default. A paid model is used only if `allow_paid = true`.
- Before a task that may use a paid model, the estimated cost is shown and the author
  must confirm TWICE, separately, seeing the sum each time.
- Limits per task / day / month (USD). Reaching a limit stops paid calls immediately.
- A paid model without a known price is never used (the cost could not be estimated).
- Every paid call is written to the ledger (wallet.jsonl): model, tokens, cost.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from dante.config import Provider, Settings
from dante.llm import LLM, LLMError, LLMResponse

Confirm = Callable[[str], bool]


class BudgetError(LLMError):
    """A paid call was blocked by the wallet."""


def call_cost_usd(p: Provider, prompt_tokens: int, completion_tokens: int) -> float:
    if p.price_in_usd_per_m is None or p.price_out_usd_per_m is None:
        raise BudgetError(f"{p.name}: price unknown — paid model not allowed")
    return (prompt_tokens * p.price_in_usd_per_m + completion_tokens * p.price_out_usd_per_m) / 1_000_000


class Wallet:
    def __init__(self, settings: Settings, ledger: Path, confirm: Confirm | None = None):
        self.s = settings
        self.ledger = ledger
        self.confirm = confirm
        self.task_spent = 0.0
        self.approved = False

    # ---------- money formatting ----------
    def fmt(self, usd: float) -> str:
        text = f"${usd:.4f}"
        if self.s.uah_per_usd:
            text += f" (≈ {usd * self.s.uah_per_usd:.2f} грн)"
        return text

    # ---------- spent so far ----------
    def spent_since(self, since: datetime) -> float:
        if not self.ledger.exists():
            return 0.0
        total = 0.0
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if datetime.fromisoformat(r["ts"]) >= since:
                    total += float(r["usd"])
            except (ValueError, KeyError):
                continue
        return total

    def spent_today(self) -> float:
        now = datetime.now()
        return self.spent_since(now.replace(hour=0, minute=0, second=0, microsecond=0))

    def spent_month(self) -> float:
        now = datetime.now()
        return self.spent_since(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))

    # ---------- before a task ----------
    def estimate_task(self, paid: list[Provider], attempts: int, prompt_tokens: int, max_tokens: int) -> float:
        """Worst case: every attempt goes to the most expensive paid model."""
        if not paid:
            return 0.0
        return attempts * max(call_cost_usd(p, prompt_tokens, p.max_tokens or max_tokens) for p in paid)

    def approve_task(self, paid: list[Provider], estimate_usd: float) -> bool:
        """Two separate confirmations with the sum. Any 'no' or missing confirm -> False."""
        if not paid:
            return True
        if not self.s.allow_paid or self.confirm is None:
            return False
        names = ", ".join(p.name for p in paid)
        limits = (
            f"Ліміти: задача {self.fmt(self.s.budget_task_usd)}, день {self.fmt(self.s.budget_day_usd)} "
            f"(витрачено {self.fmt(self.spent_today())}), місяць {self.fmt(self.s.budget_month_usd)} "
            f"(витрачено {self.fmt(self.spent_month())})."
        )
        if estimate_usd > self.s.budget_task_usd:
            return False  # cannot fit the per-task limit: do not even ask
        first = self.confirm(
            f"УВАГА: ПЛАТНІ моделі ({names}). Максимальна вартість цієї задачі: {self.fmt(estimate_usd)}. "
            f"{limits} Дозволити? (1 з 2)"
        )
        if not first:
            return False
        second = self.confirm(
            f"ПОВТОРНЕ ПІДТВЕРДЖЕННЯ: витратити до {self.fmt(estimate_usd)} на цю задачу? (2 з 2)"
        )
        self.approved = bool(second)
        self.task_spent = 0.0
        return self.approved

    # ---------- around each paid call ----------
    def check(self, p: Provider, prompt_tokens: int, max_tokens: int) -> None:
        if not self.approved:
            raise BudgetError(f"{p.name}: paid call not approved by the author")
        cost = call_cost_usd(p, prompt_tokens, max_tokens)
        if self.task_spent + cost > self.s.budget_task_usd:
            raise BudgetError(f"{p.name}: task limit {self.fmt(self.s.budget_task_usd)} would be exceeded")
        if self.spent_today() + cost > self.s.budget_day_usd:
            raise BudgetError(f"{p.name}: day limit {self.fmt(self.s.budget_day_usd)} would be exceeded")
        if self.spent_month() + cost > self.s.budget_month_usd:
            raise BudgetError(f"{p.name}: month limit {self.fmt(self.s.budget_month_usd)} would be exceeded")

    def record(self, p: Provider, resp: LLMResponse, est_prompt_tokens: int = 0) -> float:
        # If the provider did not report usage, count our own (safe-side) estimate.
        pt = resp.prompt_tokens or est_prompt_tokens
        ct = resp.completion_tokens or estimate_tokens(resp.content)
        cost = call_cost_usd(p, pt, ct)
        self.task_spent += cost
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"), "provider": p.name, "model": resp.model,
                "prompt_tokens": pt, "completion_tokens": ct, "usd": round(cost, 6),
            }) + "\n")
        return cost


def estimate_tokens(text: str) -> int:
    """Rough upper estimate: ~3 characters per token (safe side for Cyrillic and code)."""
    return len(text) // 3 + 1


class PaidLLM:
    """Wraps a paid model: every call is checked against the wallet and recorded."""

    def __init__(self, provider: Provider, inner: LLM, wallet: Wallet, default_max_tokens: int):
        self.p = provider
        self.inner = inner
        self.wallet = wallet
        self.max_tokens = provider.max_tokens or default_max_tokens

    def complete(self, system: str, user: str) -> LLMResponse:
        est = estimate_tokens(system + user)
        self.wallet.check(self.p, est, self.max_tokens)
        resp = self.inner.complete(system, user)
        self.wallet.record(self.p, resp, est)
        return resp


def build_llm_with_wallet(settings: Settings, wallet: Wallet):
    """Like llm.build_llm, but paid models go through the wallet; unapproved paid models are dropped."""
    from dante.llm import MultiLLM, OpenAICompatibleLLM

    clients, backups = [], []
    for p in settings.active_providers():
        inner = OpenAICompatibleLLM(p, settings)
        if p.paid:
            if not wallet.approved:
                continue
            inner = PaidLLM(p, inner, wallet, settings.max_tokens)
        (backups if p.backup else clients).append((p.name, inner))
    return MultiLLM(clients, settings.strategy, backups)
