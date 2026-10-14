import logging

import redis
from django.conf import settings
from django.db import connection
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _database_ok() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        logger.exception("Health check: database unreachable")
        return False


def _redis_ok() -> bool:
    try:
        return bool(redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2).ping())
    except Exception:
        logger.exception("Health check: redis unreachable")
        return False


class HealthView(APIView):
    def get(self, request: Request) -> Response:
        database, cache = _database_ok(), _redis_ok()
        healthy = database and cache
        body = {
            "status": "ok" if healthy else "error",
            "database": "ok" if database else "error",
            "redis": "ok" if cache else "error",
        }
        return Response(body, status=200 if healthy else 503)
