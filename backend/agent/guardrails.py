"""Run limits and the budget check (docs/spec.md S6.5)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentLimits:
    max_iterations: int
    max_frames: int
    max_tokens: int
    max_cost_usd: float
    max_llm_calls: int
    report_reserve_tokens: int


class BudgetExhausted(Exception):
    """A call or a frame extraction would break a limit. `reason` is the stop reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def limit_hit(
    budget: Mapping[str, Any], limits: AgentLimits, *, reserve: bool = True, frames: bool = True
) -> str | None:
    """Return the stop reason, or None.

    With `reserve`, the report's tokens and its one LLM call are kept back. `frames` is off
    for LLM calls, because the frame limit is enforced when frames are extracted.
    """
    if frames and budget["frames"] >= limits.max_frames:
        return "max_frames"
    token_cap = limits.max_tokens - (limits.report_reserve_tokens if reserve else 0)
    if budget["input_tokens"] + budget["output_tokens"] >= token_cap:
        return "max_tokens"
    if limits.max_cost_usd > 0 and budget["cost_usd"] >= limits.max_cost_usd:
        return "max_cost"
    if budget["llm_calls"] >= limits.max_llm_calls - (1 if reserve else 0):
        return "max_llm_calls"
    return None


def budget_exceeded(state: Mapping[str, Any], limits: AgentLimits) -> str | None:
    """Return the stop reason, or None. The report reserve is excluded."""
    return limit_hit(state["budget"], limits)
