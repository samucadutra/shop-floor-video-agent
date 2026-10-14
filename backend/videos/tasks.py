"""Celery task that runs one analysis with the agent (docs/spec.md S5.2)."""

import logging
from decimal import Decimal

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from agent.nodes import AgentFailed
from agent.runner import run_agent
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
    except AgentFailed as exc:
        logger.warning("Run %s failed: %s", run_id, exc)
        fail_run(run, StopReason.ERROR, str(exc))
    except SoftTimeLimitExceeded:
        logger.warning("Run %s hit the time limit", run_id)
        message = f"The analysis took longer than {settings.AGENT_RUN_TIMEOUT_SECONDS} seconds."
        fail_run(run, StopReason.TIMEOUT, message)
    except Exception:
        logger.exception("Run %s failed", run_id)
        fail_run(run, StopReason.ERROR, ERROR_MESSAGE)
