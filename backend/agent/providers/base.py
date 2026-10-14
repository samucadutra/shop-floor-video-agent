"""Provider interface shared by every LLM provider (docs/spec.md S7.1)."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

Stage = Literal["survey", "inspect", "verify", "report"]


@dataclass(frozen=True)
class Frame:
    timestamp_s: float
    path: Path
    source: Literal["survey", "scene", "window"]


@dataclass(frozen=True)
class LLMRequest:
    stage: Stage
    prompt: str
    schema: type[BaseModel]
    frames: tuple[Frame, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)  # data the prompt was built from


@dataclass(frozen=True)
class RawResponse:
    text: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMResult:
    parsed: BaseModel
    raw_text: str
    input_tokens: int  # summed over attempts
    output_tokens: int
    latency_ms: int
    attempts: int  # 1 or 2 (validation retry)
    cost_usd: float


class RetryableLLMError(Exception):
    """429, 5xx and timeouts."""


class QuotaExhaustedError(Exception):
    """Daily free tier quota used up: not retried."""


class LLMOutputError(Exception):
    """Invalid output after the retry. Carries the usage of both attempts."""

    def __init__(self, message: str, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        super().__init__(message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class BaseProvider(ABC):
    name: str
    model: str
    throttled: bool = True  # False for providers with no rate limit (the mock)

    @abstractmethod
    def complete(self, request: LLMRequest, extra_instruction: str | None = None) -> RawResponse:
        """Send the request to the model and return its raw text and token usage."""


def prompt_text(request: LLMRequest, extra_instruction: str | None) -> str:
    """The prompt, with the validation retry instruction appended when there is one."""
    if not extra_instruction:
        return request.prompt
    return f"{request.prompt}\n\n{extra_instruction}"
