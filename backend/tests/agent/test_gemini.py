"""GeminiProvider with a fake SDK client and fake SDK errors (no network)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors, types
from tenacity import wait_none

from agent.providers.base import (
    Frame,
    LLMRequest,
    QuotaExhaustedError,
    RetryableLLMError,
)
from agent.providers.client import LLMClient
from agent.providers.gemini import QUOTA_MESSAGE, GeminiProvider, map_error
from agent.schemas import ReportResult

SETTINGS = SimpleNamespace(
    LLM_INPUT_PRICE_PER_MTOK=0,
    LLM_OUTPUT_PRICE_PER_MTOK=0,
    LLM_MAX_RETRIES=3,
    LLM_MAX_REQUESTS_PER_MINUTE=0,
)


def _api_error(code: int, message: str, quota_id: str = "") -> errors.APIError:
    error: dict[str, Any] = {"code": code, "message": message, "status": "SOME_STATUS"}
    if quota_id:
        error["details"] = [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaMetric": "generate_content_requests", "quotaId": quota_id}],
            }
        ]
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": error})


PER_DAY_429 = _api_error(
    429, "You exceeded your current quota.", "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
)
PER_MINUTE_429 = _api_error(
    429, "You exceeded your current quota.", "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
)


class FakeModels:
    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _response(text: str, prompt: int = 1200, out: int = 40, thoughts: int | None = 15) -> Any:
    usage = SimpleNamespace(
        prompt_token_count=prompt, candidates_token_count=out, thoughts_token_count=thoughts
    )
    return SimpleNamespace(text=text, usage_metadata=usage)


def _provider(*replies: Any) -> tuple[GeminiProvider, FakeModels]:
    models = FakeModels(*replies)
    provider = GeminiProvider("test-key", "test-model", 60, client=SimpleNamespace(models=models))
    return provider, models


def _request(frames: tuple[Frame, ...] = ()) -> LLMRequest:
    return LLMRequest(stage="report", prompt="Summarize.", schema=ReportResult, frames=frames)


def test_request_has_prompt_jpeg_parts_and_json_config(tmp_path: Path) -> None:
    jpg = tmp_path / "f.jpg"
    jpg.write_bytes(b"\xff\xd8fake-jpeg")
    provider, models = _provider(_response('{"summary": "ok"}'))

    raw = provider.complete(_request((Frame(1.0, jpg, "window"),)), "Return valid JSON only.")

    call = models.calls[0]
    assert call["model"] == "test-model"
    prompt, part = call["contents"]
    assert prompt == "Summarize.\n\nReturn valid JSON only."
    assert isinstance(part, types.Part)
    assert part.inline_data.mime_type == "image/jpeg"
    assert part.inline_data.data == b"\xff\xd8fake-jpeg"
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].temperature == 0.2
    assert (raw.text, raw.input_tokens, raw.output_tokens) == ('{"summary": "ok"}', 1200, 55)


def test_missing_text_and_usage_are_safe() -> None:
    provider, _ = _provider(SimpleNamespace(text=None, usage_metadata=None))

    raw = provider.complete(_request())

    assert (raw.text, raw.input_tokens, raw.output_tokens) == ("", 0, 0)


def test_timeout_is_passed_to_the_sdk_in_milliseconds() -> None:
    provider = GeminiProvider("test-key", "test-model", 45)

    assert provider.client._api_client._http_options.timeout == 45_000


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PER_DAY_429, QuotaExhaustedError),
        (PER_MINUTE_429, RetryableLLMError),
        (_api_error(429, "Resource has been exhausted (e.g. check quota)."), RetryableLLMError),
        (_api_error(500, "Internal error."), RetryableLLMError),
        (_api_error(503, "The model is overloaded."), RetryableLLMError),
        (_api_error(504, "Deadline exceeded."), RetryableLLMError),
    ],
)
def test_error_mapping(error: errors.APIError, expected: type[Exception]) -> None:
    provider, _ = _provider(error)

    with pytest.raises(expected) as info:
        provider.complete(_request())

    assert info.value.__cause__ is error


def test_quota_error_has_a_clear_message() -> None:
    assert str(map_error(PER_DAY_429)) == QUOTA_MESSAGE


@pytest.mark.parametrize("code", [400, 403, 404])
def test_other_client_errors_are_raised_unchanged(code: int) -> None:
    error = _api_error(code, "Bad request.")
    provider, _ = _provider(error)

    with pytest.raises(errors.ClientError) as info:
        provider.complete(_request())

    assert info.value is error


def test_network_timeout_is_retryable() -> None:
    provider, _ = _provider(httpx.ReadTimeout("timed out"))

    with pytest.raises(RetryableLLMError, match="timed out"):
        provider.complete(_request())


def _client(provider: GeminiProvider) -> LLMClient:
    client = LLMClient(provider, SETTINGS)
    client.wait = wait_none()
    return client


def test_client_retries_503_and_429_then_succeeds() -> None:
    provider, models = _provider(
        _api_error(503, "Overloaded."), PER_MINUTE_429, _response('{"summary": "ok"}')
    )

    result = _client(provider).analyze(_request())

    assert len(models.calls) == 3
    assert result.parsed == ReportResult(summary="ok")


def test_client_does_not_retry_400() -> None:
    provider, models = _provider(_api_error(400, "Bad request."), _response('{"summary": "ok"}'))

    with pytest.raises(errors.ClientError):
        _client(provider).analyze(_request())

    assert len(models.calls) == 1


def test_client_does_not_retry_the_daily_quota() -> None:
    provider, models = _provider(PER_DAY_429, _response('{"summary": "ok"}'))

    with pytest.raises(QuotaExhaustedError, match="daily quota"):
        _client(provider).analyze(_request())

    assert len(models.calls) == 1
