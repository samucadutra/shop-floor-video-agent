"""Celery task that runs one analysis (docs/spec.md S5.2).

Phase 3 skeleton: it extracts the survey frames only. The agent is connected in Phase 4.
"""

import logging
from pathlib import Path

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from media_tools.ffmpeg import extract_survey
from videos.models import AnalysisRun, RunStatus, StopReason
from videos.services import RunResult, fail_run, finish_run

logger = logging.getLogger(__name__)

ERROR_MESSAGE = "The analysis failed because of an internal error."


@shared_task(
    bind=True,
    acks_late=True,
    soft_time_limit=settings.AGENT_RUN_TIMEOUT_SECONDS,
    time_limit=settings.AGENT_RUN_TIMEOUT_SECONDS + 30,
)
def analyze_video(self, run_id: str) -> None:
    run = AnalysisRun.objects.select_related("video").filter(pk=run_id).first()
    if run is None or run.status != RunStatus.QUEUED:
        logger.warning("Skipping run %s: not found or not queued", run_id)
        return

    run.status = RunStatus.RUNNING
    run.started_at = timezone.now()
    run.celery_task_id = self.request.id or ""
    run.save(update_fields=["status", "started_at", "celery_task_id"])

    try:
        frames = extract_survey(
            Path(run.video.file.path),
            Path(settings.MEDIA_ROOT) / "frames" / str(run.id),
            settings.SURVEY_INTERVAL_S,
            max_side=settings.FRAME_MAX_SIDE,
        )
        finish_run(run, RunResult(frames_analyzed=len(frames)))
    except SoftTimeLimitExceeded:
        logger.warning("Run %s hit the time limit", run_id)
        message = f"The analysis took longer than {settings.AGENT_RUN_TIMEOUT_SECONDS} seconds."
        fail_run(run, StopReason.TIMEOUT, message)
    except Exception:
        logger.exception("Run %s failed", run_id)
        fail_run(run, StopReason.ERROR, ERROR_MESSAGE)
