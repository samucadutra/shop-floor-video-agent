import pytest

from agent.guardrails import AgentLimits, budget_exceeded, limit_hit

LIMITS = AgentLimits(
    max_iterations=3,
    max_frames=100,
    max_tokens=10_000,
    max_cost_usd=0.5,
    max_llm_calls=10,
    report_reserve_tokens=1_000,
)
FRESH = {"frames": 0, "llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({}, None),
        ({"frames": 100}, "max_frames"),
        ({"input_tokens": 8_000, "output_tokens": 1_000}, "max_tokens"),  # reserve excluded
        ({"cost_usd": 0.5}, "max_cost"),
        ({"llm_calls": 9}, "max_llm_calls"),  # one call kept for the report
    ],
)
def test_budget_exceeded(changes: dict, reason: str | None) -> None:
    assert budget_exceeded({"budget": FRESH | changes}, LIMITS) == reason


def test_report_may_use_the_reserve() -> None:
    budget = FRESH | {"input_tokens": 9_000, "llm_calls": 9, "frames": 100}

    assert limit_hit(budget, LIMITS, reserve=False, frames=False) is None
    assert limit_hit(budget | {"llm_calls": 10}, LIMITS, reserve=False) == "max_frames"


def test_cost_limit_is_off_when_zero() -> None:
    limits = AgentLimits(3, 100, 10_000, 0.0, 10, 1_000)

    assert budget_exceeded({"budget": FRESH | {"cost_usd": 99.0}}, limits) is None
