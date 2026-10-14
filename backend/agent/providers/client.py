"""LLMClient: throttle, backoff, parsing, validation with one retry and cost (spec S7.2)."""

import json
import logging
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)
from tenacity.wait import wait_base

from agent.providers.base import (
    BaseProvider,
    LLMOutputError,
    LLMRequest,
    LLMResult,
    RawResponse,
    RetryableLLMError,
)

logger = logging.getLogger(__name__)

FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)
MAX_ERROR_CHARS = 1000
WINDOW_S = 60.0


class RateLimiter:
    """Sliding window: at most `max_per_minute` calls in any 60 s. Sleeps until a slot is free."""

    def __init__(
        self,
        max_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.max_per_minute = max_per_minute
        self.clock = clock
        self.sleep = sleep
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        if self.max_per_minute <= 0:
            return
        with self.lock:
            while True:
                now = self.clock()
                while self.calls and now - self.calls[0] >= WINDOW_S:
                    self.calls.popleft()
                if len(self.calls) < self.max_per_minute:
                    self.calls.append(now)
                    return
                wait = WINDOW_S - (now - self.calls[0])
                logger.info("LLM throttle: waiting %.1f s for a free request slot", wait)
                self.sleep(wait)


_limiters: dict[int, RateLimiter] = {}


def shared_rate_limiter(max_per_minute: int) -> RateLimiter:
    """One limiter per process, so the limit also holds across consecutive runs."""
    if max_per_minute not in _limiters:
        _limiters[max_per_minute] = RateLimiter(max_per_minute)
    return _limiters[max_per_minute]


def parse_json_output(text: str, schema: type[BaseModel]) -> BaseModel:
    """Take the first JSON object in `text` (code fences stripped) and validate it."""
    cleaned = FENCE.sub("", text)
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("No JSON object found in the reply.")
    obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    return schema.model_validate(obj)


class LLMClient:
    def __init__(
        self, provider: BaseProvider, settings: Any, limiter: RateLimiter | None = None
    ) -> None:
        self.provider = provider
        self.input_price = float(settings.LLM_INPUT_PRICE_PER_MTOK)
        self.output_price = float(settings.LLM_OUTPUT_PRICE_PER_MTOK)
        self.max_retries = int(settings.LLM_MAX_RETRIES)
        self.limiter = limiter or shared_rate_limiter(int(settings.LLM_MAX_REQUESTS_PER_MINUTE))
        self.wait: wait_base = wait_exponential_jitter(initial=2, max=30)

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1e6

    def _complete(self, request: LLMRequest, extra_instruction: str | None) -> RawResponse:
        """One provider call: throttled, retried with backoff on RetryableLLMError only."""

        def attempt() -> RawResponse:
            if self.provider.throttled:
                self.limiter.acquire()
            return self.provider.complete(request, extra_instruction)

        retrying = Retrying(
            retry=retry_if_exception_type(RetryableLLMError),
            stop=stop_after_attempt(self.max_retries + 1),
            wait=self.wait,
            before_sleep=self._log_retry,
            reraise=True,
        )
        return retrying(attempt)

    def _log_retry(self, state: Any) -> None:
        logger.warning(
            "LLM call retry provider=%s attempt=%d error=%s wait_s=%.1f",
            self.provider.name,
            state.attempt_number,
            state.outcome.exception(),
            state.next_action.sleep if state.next_action else 0,
        )

    def analyze(self, request: LLMRequest) -> LLMResult:
        started = time.monotonic()
        raw = self._complete(request, None)
        input_tokens, output_tokens, attempts = raw.input_tokens, raw.output_tokens, 1
        try:
            parsed = parse_json_output(raw.text, request.schema)
        except (ValueError, ValidationError) as exc:
            instruction = f"{str(exc)[:MAX_ERROR_CHARS]}\nReturn valid JSON only."
            raw = self._complete(request, instruction)
            input_tokens += raw.input_tokens
            output_tokens += raw.output_tokens
            attempts = 2
            try:
                parsed = parse_json_output(raw.text, request.schema)
            except (ValueError, ValidationError) as retry_exc:
                raise LLMOutputError(
                    f"The model returned invalid {request.stage} output twice.",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                ) from retry_exc

        latency_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "LLM call stage=%s provider=%s model=%s attempts=%d tokens=%d/%d latency_ms=%d",
            request.stage,
            self.provider.name,
            self.provider.model,
            attempts,
            input_tokens,
            output_tokens,
            latency_ms,
        )
        return LLMResult(
            parsed=parsed,
            raw_text=raw.text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            attempts=attempts,
            cost_usd=self.cost(input_tokens, output_tokens),
        )
