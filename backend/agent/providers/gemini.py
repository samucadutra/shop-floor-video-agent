"""Google Gemini provider (docs/spec.md S7.3). Only maps requests and errors; see LLMClient."""

import json
import re
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from agent.providers.base import (
    BaseProvider,
    LLMRequest,
    QuotaExhaustedError,
    RawResponse,
    RetryableLLMError,
    prompt_text,
)

QUOTA_MESSAGE = "Gemini free tier daily quota reached, try again tomorrow or use the mock provider."
PER_DAY = re.compile(r"per\s*day", re.IGNORECASE)
RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}


def map_error(exc: errors.APIError) -> Exception:
    """A per-day quota 429 is final; other 429, timeouts and 5xx can be retried."""
    if exc.code == 429 and PER_DAY.search(f"{exc.message} {json.dumps(exc.details, default=str)}"):
        return QuotaExhaustedError(QUOTA_MESSAGE)
    if exc.code in RETRYABLE_CODES or exc.code >= 500:
        return RetryableLLMError(f"Gemini returned HTTP {exc.code} {exc.status or ''}".strip())
    return exc


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(
        self, api_key: str, model: str, timeout_s: float, client: Any | None = None
    ) -> None:
        self.model = model
        http_options = types.HttpOptions(timeout=int(timeout_s * 1000))  # milliseconds
        self.client = client or genai.Client(api_key=api_key, http_options=http_options)

    def complete(self, request: LLMRequest, extra_instruction: str | None = None) -> RawResponse:
        images = [
            types.Part.from_bytes(data=f.path.read_bytes(), mime_type="image/jpeg")
            for f in request.frames
        ]
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt_text(request, extra_instruction), *images],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.2
                ),
            )
        except errors.APIError as exc:
            mapped = map_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        except httpx.TimeoutException as exc:
            raise RetryableLLMError("Gemini request timed out") from exc
        except httpx.TransportError as exc:
            raise RetryableLLMError("Gemini connection error") from exc

        usage = response.usage_metadata
        return RawResponse(
            text=response.text or "",
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            # Thinking tokens are billed as output, so they count toward the cost.
            output_tokens=(
                (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                if usage
                else 0
            ),
        )
