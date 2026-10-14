from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings as django_settings
from django.test import Client

ALLOWED = "http://localhost:3000"
BLOCKED = "http://evil.example"


@pytest.fixture
def cors(settings) -> None:
    settings.CORS_ALLOWED_ORIGINS = [ALLOWED]


# CORS -------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_cors_allows_the_frontend_origin(client: Client, cors) -> None:
    response = client.get("/api/videos/", headers={"Origin": ALLOWED})

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED


@pytest.mark.django_db
def test_cors_blocks_other_origins(client: Client, cors) -> None:
    response = client.get("/api/videos/", headers={"Origin": BLOCKED})

    assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.parametrize(("origin", "allowed"), [(ALLOWED, True), (BLOCKED, False)])
def test_cors_preflight(client: Client, cors, origin: str, allowed: bool) -> None:
    response = client.options(
        "/api/videos/",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )

    assert ("Access-Control-Allow-Origin" in response.headers) is allowed


# DEBUG=false error pages ------------------------------------------------------------------


def test_unknown_url_returns_json_404_without_debug(client: Client, settings) -> None:
    settings.DEBUG = False

    response = client.get("/api/nope/")

    assert response.status_code == 404
    assert response.headers["Content-Type"] == "application/json"
    assert response.json() == {"detail": "Not found."}


def test_server_error_returns_json_500_without_stack_trace(settings) -> None:
    settings.DEBUG = False
    client = Client(raise_request_exception=False)

    with patch("core.views.HealthView.get", side_effect=RuntimeError("secret internals")):
        response = client.get("/api/health/")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert b"secret internals" not in response.content
    assert b"Traceback" not in response.content


# Environment variables --------------------------------------------------------------------


def _env_example() -> Path:
    """Repo root in a checkout (CI); /app in the backend container (mounted read-only)."""
    base = Path(django_settings.BASE_DIR)
    for path in (base / ".env.example", base.parent / ".env.example"):
        if path.is_file():
            return path
    raise AssertionError(".env.example not found next to or above the backend directory")


def test_env_example_lists_exactly_the_documented_variables() -> None:
    keys = [
        line.split("=", 1)[0].strip()
        for line in _env_example().read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert len(keys) == len(set(keys)), "duplicate keys in .env.example"
    assert set(keys) == set(django_settings.ENV_VARS)


def test_env_example_has_no_secret_values() -> None:
    for line in _env_example().read_text().splitlines():
        name, _, value = line.partition("=")
        if name.endswith("_API_KEY"):
            assert value == "", f"{name} must be empty in .env.example"
