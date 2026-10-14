"""Celery task that runs one analysis with the agent (docs/spec.md S5.2)."""

import logging
from decimal import Decimal

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from agent.nodes import AgentFailed
from agent.runner import run_agent
from config.logging import log_context
from media_tools.ffmpeg import FFmpegError
from videos.models import AnalysisRun, RunStatus, StopReason
from videos.services import RunResult, fail_run, finish_run

logger = logging.getLogger(__name__)

# User-facing messages (the agent's own failures carry theirs in AgentFailed).
ERROR_MESSAGE = (
    "The analysis failed because of an internal error. Retry it; if it keeps failing, "
    "check the worker logs."
)
FFMPEG_MESSAGE = (
    "Frames could not be extracted from the video (ffmpeg failed). The file may be damaged: "
    "re-encode it as MP4 and upload it again."
)


def timeout_message() -> str:
    return (
        f"The analysis took longer than the {settings.AGENT_RUN_TIMEOUT_SECONDS} s limit and "
        "was stopped. Retry it, or try a shorter video."
    )


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

    with log_context(run_id=str(run.id), video_id=str(run.video_id)):
        _run(self, run)


def _run(task: Task, run: AnalysisRun) -> None:
    run.status = RunStatus.RUNNING
    run.started_at = timezone.now()
    run.celery_task_id = task.request.id or ""
    run.save(update_fields=["status", "started_at", "celery_task_id"])
    logger.info("Analysis started (provider=%s)", run.provider)

    try:
        outcome = run_agent(str(run.id), settings)
        result = RunResult(
            summary=outcome.summary,
            is_partial=outcome.is_partial,
            stop_reason=outcome.stop_reason,
            iterations=outcome.iterations,
            frames_analyzed=outcome.frames_analyzed,
            llm_calls=outcome.llm_calls,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            estimated_cost_usd=Decimal(str(round(outcome.cost_usd, 4))),
        )
        finish_run(run, result)
        logger.info(
            "Analysis finished: stop_reason=%s partial=%s llm_calls=%d",
            result.stop_reason,
            result.is_partial,
            result.llm_calls,
        )
    except AgentFailed as exc:
        logger.warning("Analysis failed: %s", exc)
        fail_run(run, StopReason.ERROR, str(exc))
    except SoftTimeLimitExceeded:
        logger.warning("Analysis hit the time limit")
        fail_run(run, StopReason.TIMEOUT, timeout_message())
    except FFmpegError:
        logger.exception("Analysis failed: frame extraction error")
        fail_run(run, StopReason.ERROR, FFMPEG_MESSAGE)
    except Exception:
        logger.exception("Analysis failed: unexpected error")
        fail_run(run, StopReason.ERROR, ERROR_MESSAGE)
