from types import SimpleNamespace

import pytest

from agent.providers.factory import (
    ProviderConfigError,
    VideoInfo,
    build_provider,
    check_provider_config,
)
from agent.providers.gemini import GeminiProvider
from agent.providers.mock import MockProvider
from config.celery import check_llm_provider

VIDEO = VideoInfo(sha256="0" * 64, filename="clip.mp4", duration_s=10)
SECRET = "AIzaSy-not-a-real-key-0123456789"


def _settings(**values) -> SimpleNamespace:
    defaults = {
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": SECRET,
        "GEMINI_MODEL": "test-model",
        "LLM_TIMEOUT_SECONDS": 60,
        "MOCK_LATENCY_MS": 0,
    }
    return SimpleNamespace(**(defaults | values))


def test_gemini_is_built_with_the_model_from_settings() -> None:
    provider = build_provider(_settings(), VIDEO)

    assert isinstance(provider, GeminiProvider)
    assert (provider.name, provider.model) == ("gemini", "test-model")


def test_mock_needs_no_settings() -> None:
    provider = build_provider(_settings(LLM_PROVIDER="mock", GEMINI_API_KEY=""), VIDEO)

    assert isinstance(provider, MockProvider)


@pytest.mark.parametrize(
    ("changes", "missing"),
    [
        ({"GEMINI_API_KEY": ""}, "GEMINI_API_KEY"),
        ({"GEMINI_MODEL": ""}, "GEMINI_MODEL"),
        ({"GEMINI_API_KEY": "", "GEMINI_MODEL": ""}, "GEMINI_API_KEY, GEMINI_MODEL"),
    ],
)
def test_missing_gemini_settings_fail_fast(changes: dict, missing: str) -> None:
    with pytest.raises(ProviderConfigError) as info:
        build_provider(_settings(**changes), VIDEO)

    assert str(info.value) == f"LLM_PROVIDER=gemini needs {missing} to be set."
    assert SECRET not in str(info.value)
    assert "test-model" not in str(info.value)


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ProviderConfigError, match="Unknown LLM_PROVIDER 'nope'"):
        check_provider_config(_settings(LLM_PROVIDER="nope"))


def test_worker_does_not_start_without_the_api_key(settings) -> None:
    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = ""
    settings.GEMINI_MODEL = "test-model"

    with pytest.raises(SystemExit, match="GEMINI_API_KEY"):
        check_llm_provider()


def test_worker_starts_with_the_mock(settings) -> None:
    check_llm_provider()  # conftest selects the mock provider
