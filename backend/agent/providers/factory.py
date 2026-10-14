"""Builds the provider selected by LLM_PROVIDER (docs/spec.md S7.3)."""

from dataclasses import dataclass
from typing import Any

from agent.providers.base import BaseProvider

# Settings each provider needs. Messages name the variable, never its value.
REQUIRED_SETTINGS: dict[str, tuple[str, ...]] = {
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL"),
    "mock": (),
}


class ProviderConfigError(Exception):
    """The selected provider is unknown or its configuration is missing."""


@dataclass(frozen=True)
class VideoInfo:
    sha256: str
    filename: str
    duration_s: float


def check_provider_config(settings: Any) -> None:
    """Raise ProviderConfigError if LLM_PROVIDER is unknown or a required variable is empty."""
    name = settings.LLM_PROVIDER
    if name not in REQUIRED_SETTINGS:
        choices = ", ".join(REQUIRED_SETTINGS)
        raise ProviderConfigError(f"Unknown LLM_PROVIDER '{name}'. Use one of: {choices}.")
    missing = [var for var in REQUIRED_SETTINGS[name] if not getattr(settings, var, "")]
    if missing:
        raise ProviderConfigError(f"LLM_PROVIDER={name} needs {', '.join(missing)} to be set.")


def build_provider(settings: Any, video_info: VideoInfo) -> BaseProvider:
    check_provider_config(settings)
    name = settings.LLM_PROVIDER
    if name == "gemini":
        from agent.providers.gemini import GeminiProvider

        return GeminiProvider(
            settings.GEMINI_API_KEY, settings.GEMINI_MODEL, float(settings.LLM_TIMEOUT_SECONDS)
        )
    from agent.providers.mock import MockProvider

    return MockProvider(video_info, latency_ms=int(settings.MOCK_LATENCY_MS))
