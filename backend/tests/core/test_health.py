from unittest.mock import patch

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_ok() -> None:
    response = APIClient().get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}


@pytest.mark.django_db
def test_health_reports_redis_down() -> None:
    with patch("core.views.redis.Redis.from_url", side_effect=ConnectionError("down")):
        response = APIClient().get("/api/health/")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "ok", "redis": "error"}
