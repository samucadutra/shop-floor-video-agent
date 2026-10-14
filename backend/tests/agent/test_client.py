from types import SimpleNamespace

import pytest
from tenacity import wait_none

from agent.providers.base import (
    BaseProvider,
    LLMOutputError,
    LLMRequest,
    QuotaExhaustedError,
    RawResponse,
    RetryableLLMError,
)
from agent.providers.client import LLMClient, RateLimiter, parse_json_output
from agent.schemas import ReportResult

SETTINGS = SimpleNamespace(
    LLM_INPUT_PRICE_PER_MTOK=0.5,
    LLM_OUTPUT_PRICE_PER_MTOK=2.0,
    LLM_MAX_RETRIES=3,
    LLM_MAX_REQUESTS_PER_MINUTE=0,
)


class FakeProvider(BaseProvider):
    """Returns the given texts in order; an exception in the list is raised instead."""

    name = "fake"
    model = "fake-model"

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.instructions: list[str | None] = []
        self.calls = 0

    def complete(self, request: LLMRequest, extra_instruction: str | None = None) -> RawResponse:
        self.calls += 1
        self.instructions.append(extra_instruction)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return RawResponse(reply, input_tokens=100, output_tokens=10)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class CountingLimiter(RateLimiter):
    def __init__(self) -> None:
        super().__init__(0)
        self.acquired = 0

    def acquire(self) -> None:
        self.acquired += 1


def _client(provider: BaseProvider, limiter: RateLimiter | None = None, **changes) -> LLMClient:
    client = LLMClient(provider, SimpleNamespace(**(vars(SETTINGS) | changes)), limiter)
    client.wait = wait_none()  # no real backoff sleeps in tests
    return client


def _request() -> LLMRequest:
    return LLMRequest(stage="report", prompt="Summarize.", schema=ReportResult)


def test_fenced_json_is_parsed() -> None:
    parsed = parse_json_output('Sure:\n```json\n{"summary": "ok"}\n```', ReportResult)

    assert parsed == ReportResult(summary="ok")


def test_valid_reply_uses_one_attempt_and_computes_cost() -> None:
    result = _client(FakeProvider('{"summary": "ok"}')).analyze(_request())

    assert result.attempts == 1
    assert (result.input_tokens, result.output_tokens) == (100, 10)
    assert result.cost_usd == pytest.approx((100 * 0.5 + 10 * 2.0) / 1e6)


def test_invalid_reply_is_retried_once_with_the_error() -> None:
    provider = FakeProvider('{"summary": ""}', '{"summary": "fixed"}')

    result = _client(provider).analyze(_request())

    assert result.attempts == 2
    assert result.parsed == ReportResult(summary="fixed")
    assert (result.input_tokens, result.output_tokens) == (200, 20)
    assert provider.instructions[0] is None
    assert "summary" in provider.instructions[1]
    assert provider.instructions[1].endswith("Return valid JSON only.")


def test_two_invalid_replies_raise_with_usage() -> None:
    provider = FakeProvider("not json", '{"wrong": 1}')

    with pytest.raises(LLMOutputError) as info:
        _client(provider).analyze(_request())

    assert (info.value.input_tokens, info.value.output_tokens) == (200, 20)


@pytest.mark.parametrize("status", ["HTTP 429", "HTTP 503"])
def test_retryable_errors_are_retried_with_backoff(status: str) -> None:
    provider = FakeProvider(
        RetryableLLMError(status), RetryableLLMError(status), '{"summary": "ok"}'
    )

    result = _client(provider).analyze(_request())

    assert provider.calls == 3
    assert result.parsed == ReportResult(summary="ok")
    assert result.attempts == 1  # backoff retries are not validation attempts


def test_backoff_gives_up_after_max_retries() -> None:
    provider = FakeProvider(*[RetryableLLMError("HTTP 503")] * 5)

    with pytest.raises(RetryableLLMError):
        _client(provider, LLM_MAX_RETRIES=2).analyze(_request())

    assert provider.calls == 3


def test_backoff_wait_is_exponential_with_a_cap() -> None:
    wait = LLMClient(FakeProvider(), SETTINGS).wait
    states = [SimpleNamespace(attempt_number=n) for n in (1, 2, 3, 10)]

    waits = [wait(state) for state in states]

    assert 2 <= waits[0] <= 3 and 4 <= waits[1] <= 5 and 8 <= waits[2] <= 9
    assert waits[3] == 30


def test_quota_error_is_not_retried() -> None:
    provider = FakeProvider(QuotaExhaustedError("daily quota"), '{"summary": "ok"}')

    with pytest.raises(QuotaExhaustedError):
        _client(provider).analyze(_request())

    assert provider.calls == 1


def test_other_errors_are_not_retried() -> None:
    provider = FakeProvider(PermissionError("HTTP 400"), '{"summary": "ok"}')

    with pytest.raises(PermissionError):
        _client(provider).analyze(_request())

    assert provider.calls == 1


def test_throttle_waits_once_over_the_limit() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, clock=clock, sleep=clock.sleep)

    limiter.acquire()
    clock.now += 10
    limiter.acquire()
    clock.now += 5
    limiter.acquire()  # third call within 60 s: waits until the first one leaves the window

    assert clock.sleeps == [pytest.approx(45)]
    clock.now += 1
    limiter.acquire()  # the window now holds the calls at t+10 and t+60, one too many
    assert clock.sleeps == [pytest.approx(45), pytest.approx(9)]


def test_throttle_is_off_when_the_limit_is_zero() -> None:
    clock = FakeClock()
    limiter = RateLimiter(0, clock=clock, sleep=clock.sleep)

    for _ in range(100):
        limiter.acquire()

    assert clock.sleeps == []


def test_every_attempt_goes_through_the_throttle() -> None:
    limiter = CountingLimiter()
    provider = FakeProvider(RetryableLLMError("HTTP 429"), "not json", '{"summary": "ok"}')

    _client(provider, limiter).analyze(_request())

    assert limiter.acquired == 3


def test_unthrottled_provider_skips_the_throttle() -> None:
    limiter = CountingLimiter()
    provider = FakeProvider('{"summary": "ok"}')
    provider.throttled = False

    _client(provider, limiter).analyze(_request())

    assert limiter.acquired == 0


def test_cost_uses_prices_per_million_tokens() -> None:
    client = _client(FakeProvider(), LLM_INPUT_PRICE_PER_MTOK=0.3, LLM_OUTPUT_PRICE_PER_MTOK=2.5)

    assert client.cost(1_000_000, 0) == pytest.approx(0.3)
    assert client.cost(20_000, 4_000) == pytest.approx(0.006 + 0.01)
    assert client.cost(0, 0) == 0
