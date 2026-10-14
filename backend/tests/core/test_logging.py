import io
import json
import logging

import pytest

from config.logging import (
    REDACTED,
    ContextFilter,
    JsonLogFormatter,
    RedactionFilter,
    log_context,
)

GEMINI_KEY = "AIzaSyD-abcdefghijklmnopqrstuvwxyz012345"
OPENAI_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz"


@pytest.fixture
def capture() -> tuple[logging.Logger, io.StringIO]:
    """A logger wired like settings.LOGGING (both filters on the handler), writing to a buffer."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(ContextFilter())
    handler.addFilter(RedactionFilter(environ={"MY_API_KEY": "s3cr3t-value-123"}))
    logger = logging.getLogger("tests.logging")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, stream


def _lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def _redact(text: str, environ: dict[str, str] | None = None) -> str:
    return RedactionFilter(environ=environ or {}).redact(text)


@pytest.mark.parametrize(
    "name",
    ["GEMINI_API_KEY", "DJANGO_SECRET_KEY", "AWS_SECRET", "POSTGRES_PASSWORD"],
)
def test_env_values_with_secret_names_are_redacted(name: str) -> None:
    text = _redact("connecting with value-of-the-secret now", {name: "value-of-the-secret"})

    assert text == f"connecting with {REDACTED} now"


def test_env_values_with_other_names_are_kept() -> None:
    assert _redact("model gemini-flash", {"GEMINI_MODEL": "gemini-flash"}) == "model gemini-flash"


def test_short_env_values_are_not_redacted() -> None:
    # A 3 letter local password would otherwise break words like "application".
    assert _redact("application started", {"POSTGRES_PASSWORD": "app"}) == "application started"


def test_secret_env_values_are_read_from_os_environ(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "from-the-environment-123")

    assert RedactionFilter().redact("key=from-the-environment-123") == f"key={REDACTED}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"request failed for key {GEMINI_KEY}", f"request failed for key {REDACTED}"),
        (f"OPENAI {OPENAI_KEY} rejected", f"OPENAI {REDACTED} rejected"),
        ("Authorization: Bearer eyJhbGciOi.payload.sig", f"Authorization: {REDACTED}"),
    ],
)
def test_known_key_patterns_are_redacted(text: str, expected: str) -> None:
    assert _redact(text) == expected


def test_short_lookalikes_are_kept() -> None:
    assert _redact("sk-123 and AIza-short") == "sk-123 and AIza-short"


def test_secrets_in_arguments_and_tracebacks_are_redacted(capture) -> None:
    logger, stream = capture

    logger.info("calling with %s and %s", GEMINI_KEY, "s3cr3t-value-123")
    try:
        raise RuntimeError(f"HTTP 400 for {OPENAI_KEY}")
    except RuntimeError:
        logger.exception("provider error")

    output = stream.getvalue()
    for secret in (GEMINI_KEY, OPENAI_KEY, "s3cr3t-value-123"):
        assert secret not in output
    first, second = _lines(stream)
    assert first["message"] == f"calling with {REDACTED} and {REDACTED}"
    assert "RuntimeError: HTTP 400 for [REDACTED]" in second["exc_info"]


def test_json_lines_have_the_standard_fields(capture) -> None:
    logger, stream = capture

    logger.warning("hello %s", "world")

    [line] = _lines(stream)
    assert line["message"] == "hello world"
    assert line["level"] == "WARNING"
    assert line["logger"] == "tests.logging"
    assert line["timestamp"]
    assert "run_id" not in line


def test_context_is_added_while_set(capture) -> None:
    logger, stream = capture

    with log_context(run_id="r1", video_id="v1"):
        with log_context(node="survey"):
            logger.info("in node")
        logger.info("in run")
    logger.info("outside")

    in_node, in_run, outside = _lines(stream)
    assert (in_node["run_id"], in_node["video_id"], in_node["node"]) == ("r1", "v1", "survey")
    assert (in_run["run_id"], "node" in in_run) == ("r1", False)
    assert "run_id" not in outside


def test_settings_use_the_json_handler_for_django_and_root(settings) -> None:
    handler = settings.LOGGING["handlers"]["console"]
    assert handler["formatter"] == "json"
    assert handler["filters"] == ["context", "redact"]
    assert settings.LOGGING["root"]["handlers"] == ["console"]
    assert settings.LOGGING["loggers"]["django"]["handlers"] == ["console"]
