"""LLMClient: parsing, validation with one retry, and cost (docs/spec.md S7.2).

The throttle and the backoff on RetryableLLMError are added in Phase 5.
"""

import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from agent.providers.base import BaseProvider, LLMOutputError, LLMRequest, LLMResult, RawResponse

logger = logging.getLogger(__name__)

FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)
MAX_ERROR_CHARS = 1000


def parse_json_output(text: str, schema: type[BaseModel]) -> BaseModel:
    """Take the first JSON object in `text` (code fences stripped) and validate it."""
    cleaned = FENCE.sub("", text)
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("No JSON object found in the reply.")
    obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    return schema.model_validate(obj)


class LLMClient:
    def __init__(self, provider: BaseProvider, settings: Any) -> None:
        self.provider = provider
        self.input_price = float(settings.LLM_INPUT_PRICE_PER_MTOK)
        self.output_price = float(settings.LLM_OUTPUT_PRICE_PER_MTOK)

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1e6

    def _complete(self, request: LLMRequest, extra_instruction: str | None) -> RawResponse:
        return self.provider.complete(request, extra_instruction)

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
