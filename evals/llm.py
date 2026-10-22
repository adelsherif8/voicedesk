"""Shared OpenAI client plus a thread-safe meter that enforces the run's cost cap."""

import threading
from dataclasses import dataclass, field

from openai import OpenAI

from evals import config


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Usage:
    model: str
    prompt: int = 0
    cached: int = 0
    completion: int = 0

    @property
    def cost(self) -> float:
        p_in, p_cached, p_out = config.PRICES.get(self.model, config.PRICES["gpt-4.1"])
        fresh = self.prompt - self.cached
        return (fresh * p_in + self.cached * p_cached + self.completion * p_out) / 1e6


@dataclass
class Meter:
    cap: float
    spent: float = 0.0
    by_role: dict = field(default_factory=dict)
    parent: "Meter | None" = None     # a per-call meter also charges the run's meter
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def child(self) -> "Meter":
        return Meter(cap=float("inf"), parent=self)

    def charge(self, role: str, usage: Usage) -> None:
        with self._lock:
            self.spent += usage.cost
            self.by_role[role] = self.by_role.get(role, 0.0) + usage.cost
        if self.parent:
            self.parent.charge(role, usage)
        self.check()

    def check(self) -> None:
        if self.parent:
            self.parent.check()
        with self._lock:
            if self.spent > self.cap:
                raise BudgetExceeded(f"spent ${self.spent:.4f}, cap is ${self.cap:.2f}")


_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.openai_key(), max_retries=4, timeout=60)
    return _client


def chat(meter: Meter, role: str, model: str, messages: list, **kw):
    """One chat completion, charged to `role` on the meter. Returns (message, Usage)."""
    meter.check()
    model_base = _base_model(model)
    r = client().chat.completions.create(model=model, messages=messages, **kw)
    u = r.usage
    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    usage = Usage(model_base, u.prompt_tokens, cached, u.completion_tokens)
    meter.charge(role, usage)
    return r.choices[0].message, usage


def _base_model(model: str) -> str:
    for name in sorted(config.PRICES, key=len, reverse=True):
        if model.startswith(name):
            return name
    return model
