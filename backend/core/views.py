import logging
import mimetypes
import re
from collections.abc import Iterator
from pathlib import Path

import redis
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.db import connection
from django.db.models import Avg, Count, F, Q, Sum
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.utils._os import safe_join
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from videos.models import AnalysisRun, Event, RunStatus, Video

logger = logging.getLogger(__name__)

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK_SIZE = 64 * 1024


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


class StatsView(APIView):
    """Dashboard totals (S4.3). Event counts use each video's current run only."""

    def get(self, request: Request) -> Response:
        current_events = Event.objects.filter(run_id=F("video__current_run_id"))
        by_type = (
            current_events.values("event_type")
            .annotate(count=Count("id"))
            .order_by("-count", "event_type")
        )
        by_severity = (
            current_events.values("severity").annotate(count=Count("id")).order_by("severity")
        )
        per_video = (
            Video.objects.filter(current_run__isnull=False)
            .annotate(count=Count("current_run__events"))
            .order_by("-count", "original_name")
            .values("id", "original_name", "count")
        )
        runs = AnalysisRun.objects.aggregate(
            avg_processing_ms=Avg("duration_ms", filter=Q(status=RunStatus.SUCCEEDED)),
            input_tokens=Sum("input_tokens", default=0),
            output_tokens=Sum("output_tokens", default=0),
            cost=Sum("estimated_cost_usd", default=0),
            runs_succeeded=Count("id", filter=Q(status=RunStatus.SUCCEEDED)),
            runs_failed=Count("id", filter=Q(status=RunStatus.FAILED)),
        )
        avg_ms = runs["avg_processing_ms"]
        return Response(
            {
                "events_by_type": list(by_type),
                "events_by_severity": list(by_severity),
                "events_per_video": [
                    {"video_id": str(v["id"]), "name": v["original_name"], "count": v["count"]}
                    for v in per_video
                ],
                "avg_processing_ms": round(avg_ms) if avg_ms is not None else None,
                "total_tokens": runs["input_tokens"] + runs["output_tokens"],
                "total_estimated_cost_usd": f"{runs['cost']:.4f}",
                "runs_succeeded": runs["runs_succeeded"],
                "runs_failed": runs["runs_failed"],
            }
        )


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Return the inclusive (start, end) of a single byte range, or None if unsatisfiable."""
    match = RANGE_RE.match(header.strip())
    if not match or size == 0:
        return None
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    elif last:  # suffix range: the last N bytes
        start, end = max(size - int(last), 0), size - 1
    else:
        return None
    if start > end or start >= size:
        return None
    return start, end


def _read_range(path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def serve_media(request: HttpRequest, path: str) -> HttpResponse:
    """Serve a file from MEDIA_ROOT with HTTP Range support (needed for video seeking)."""
    try:
        full_path = Path(safe_join(settings.MEDIA_ROOT, path))
    except SuspiciousFileOperation as exc:
        raise Http404 from exc
    if not full_path.is_file():
        raise Http404

    size = full_path.stat().st_size
    content_type = mimetypes.guess_type(full_path.name)[0] or "application/octet-stream"
    range_header = request.headers.get("Range")

    if not range_header:
        response = FileResponse(full_path.open("rb"), content_type=content_type)
        response["Accept-Ranges"] = "bytes"
        return response

    byte_range = _parse_range(range_header, size)
    if byte_range is None:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response

    start, end = byte_range
    response = StreamingHttpResponse(
        _read_range(full_path, start, end), status=206, content_type=content_type
    )
    response["Content-Length"] = str(end - start + 1)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    return response


def not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    """handler404: a short JSON body instead of Django's HTML page (used when DEBUG is off)."""
    return JsonResponse({"detail": "Not found."}, status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    """handler500: no stack trace or settings in the response; the error is in the logs."""
    return JsonResponse({"detail": "Internal server error."}, status=500)
