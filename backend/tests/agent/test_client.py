from types import SimpleNamespace

import pytest

from agent.providers.base import BaseProvider, LLMOutputError, LLMRequest, RawResponse
from agent.providers.client import LLMClient, parse_json_output
from agent.schemas import ReportResult

SETTINGS = SimpleNamespace(LLM_INPUT_PRICE_PER_MTOK=0.5, LLM_OUTPUT_PRICE_PER_MTOK=2.0)


class FakeProvider(BaseProvider):
    name = "fake"
    model = "fake-model"

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.instructions: list[str | None] = []

    def complete(self, request: LLMRequest, extra_instruction: str | None = None) -> RawResponse:
        self.instructions.append(extra_instruction)
        return RawResponse(self.texts.pop(0), input_tokens=100, output_tokens=10)


def _request() -> LLMRequest:
    return LLMRequest(stage="report", prompt="Summarize.", schema=ReportResult)


def test_fenced_json_is_parsed() -> None:
    parsed = parse_json_output('Sure:\n```json\n{"summary": "ok"}\n```', ReportResult)

    assert parsed == ReportResult(summary="ok")


def test_valid_reply_uses_one_attempt_and_computes_cost() -> None:
    result = LLMClient(FakeProvider('{"summary": "ok"}'), SETTINGS).analyze(_request())

    assert result.attempts == 1
    assert (result.input_tokens, result.output_tokens) == (100, 10)
    assert result.cost_usd == pytest.approx((100 * 0.5 + 10 * 2.0) / 1e6)


def test_invalid_reply_is_retried_once_with_the_error() -> None:
    provider = FakeProvider('{"summary": ""}', '{"summary": "fixed"}')

    result = LLMClient(provider, SETTINGS).analyze(_request())

    assert result.attempts == 2
    assert result.parsed == ReportResult(summary="fixed")
    assert (result.input_tokens, result.output_tokens) == (200, 20)
    assert provider.instructions[0] is None
    assert "summary" in provider.instructions[1]
    assert provider.instructions[1].endswith("Return valid JSON only.")


def test_two_invalid_replies_raise_with_usage() -> None:
    provider = FakeProvider("not json", '{"wrong": 1}')

    with pytest.raises(LLMOutputError) as info:
        LLMClient(provider, SETTINGS).analyze(_request())

    assert (info.value.input_tokens, info.value.output_tokens) == (200, 20)
