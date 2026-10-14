"""Builds the provider selected by LLM_PROVIDER (docs/spec.md S7.3)."""

from dataclasses import dataclass
from typing import Any

from agent.providers.base import BaseProvider


class ProviderConfigError(Exception):
    """The selected provider is unknown or its configuration is missing."""


@dataclass(frozen=True)
class VideoInfo:
    sha256: str
    filename: str
    duration_s: float


def build_provider(settings: Any, video_info: VideoInfo) -> BaseProvider:
    name = settings.LLM_PROVIDER
    if name == "mock":
        from agent.providers.mock import MockProvider

        return MockProvider(video_info, latency_ms=int(settings.MOCK_LATENCY_MS))
    # gemini, anthropic and openai are added in Phase 5.
    raise ProviderConfigError(f"The LLM provider '{name}' is not available yet. Use 'mock'.")
