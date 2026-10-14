"""Analysis run lifecycle: start, finish, fail and stale detection (docs/spec.md S5)."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from videos.models import (
    ACTIVE_RUN_STATUSES,
    AnalysisRun,
    RunStatus,
    StopReason,
    Video,
    VideoStatus,
)

STALE_RUN_MESSAGE = (
    "Worker stopped before finishing (it may have crashed or restarted). Retry the analysis."
)


class RunAlreadyActive(Exception):
    """The video already has a queued or running analysis."""


@dataclass(frozen=True)
class RunResult:
    """What a finished run reports back (metrics, summary and stop reason)."""

    summary: str = ""
    is_partial: bool = False
    stop_reason: str = StopReason.COMPLETED
    iterations: int = 0
    frames_analyzed: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")


def start_analysis(video: Video) -> AnalysisRun:
    """Create a queued run and enqueue the Celery task once the transaction commits."""
    from videos.tasks import analyze_video

    try:
        with transaction.atomic():
            video = Video.objects.select_for_update().get(pk=video.pk)
            mark_stale_runs(video)
            if video.runs.filter(status__in=ACTIVE_RUN_STATUSES).exists():
                raise RunAlreadyActive
            run = AnalysisRun.objects.create(
                video=video,
                status=RunStatus.QUEUED,
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
            )
            video.status = VideoStatus.PROCESSING
            video.save(update_fields=["status", "updated_at"])
            transaction.on_commit(lambda: analyze_video.delay(str(run.id)))
    except IntegrityError as exc:
        # The one_active_run_per_video constraint is the database-level guard.
        raise RunAlreadyActive from exc
    return run


def _close(run: AnalysisRun, status: str) -> None:
    now = timezone.now()
    run.status = status
    run.finished_at = now
    if run.started_at:
        run.duration_ms = int((now - run.started_at).total_seconds() * 1000)


def finish_run(run: AnalysisRun, result: RunResult) -> None:
    """Save the result, make it the video's current run and delete the video's other runs."""
    with transaction.atomic():
        video = Video.objects.select_for_update().get(pk=run.video_id)
        _close(run, RunStatus.SUCCEEDED)
        run.summary = result.summary
        run.is_partial = result.is_partial
        run.stop_reason = result.stop_reason
        run.iterations = result.iterations
        run.frames_analyzed = result.frames_analyzed
        run.llm_calls = result.llm_calls
        run.input_tokens = result.input_tokens
        run.output_tokens = result.output_tokens
        run.estimated_cost_usd = result.estimated_cost_usd
        run.save()

        video.current_run = run
        video.status = VideoStatus.DONE
        video.save(update_fields=["current_run", "status", "updated_at"])
        # CASCADE removes the events and steps of the older runs.
        video.runs.exclude(pk=run.pk).delete()


def fail_run(run: AnalysisRun, reason: str, message: str) -> None:
    """Mark the run and its video as failed. The video's current_run is left as it was."""
    with transaction.atomic():
        _close(run, RunStatus.FAILED)
        run.stop_reason = reason
        run.error_message = message
        run.save(
            update_fields=["status", "finished_at", "duration_ms", "stop_reason", "error_message"]
        )
        Video.objects.filter(pk=run.video_id).update(
            status=VideoStatus.FAILED, updated_at=timezone.now()
        )


def mark_stale_runs(video: Video) -> int:
    """Fail active runs older than the run timeout (a worker that died). Returns how many."""
    limit = timedelta(seconds=settings.AGENT_RUN_TIMEOUT_SECONDS + 60)
    stale = video.runs.filter(status__in=ACTIVE_RUN_STATUSES, created_at__lt=timezone.now() - limit)
    count = 0
    for run in stale:
        fail_run(run, StopReason.TIMEOUT, STALE_RUN_MESSAGE)
        count += 1
    if count:
        video.refresh_from_db(fields=["status"])
    return count
