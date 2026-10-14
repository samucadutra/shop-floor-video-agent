"""The agent's only database access (docs/spec.md S6.7). The only Django import in agent/."""

from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db.models import Max

from agent.state import RunContext
from videos.models import AgentStep, AnalysisRun, Event


def get_run_context(run_id: str) -> RunContext:
    run = AnalysisRun.objects.select_related("video").get(pk=run_id)
    video = run.video
    return RunContext(
        run_id=str(run.id),
        video_path=Path(video.file.path),
        duration_s=video.duration_s,
        sha256=video.sha256,
        filename=video.original_name,
    )


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 4)))


def record_step(run_id: str, *, cost_usd: float, **fields: Any) -> None:
    """Save a step at once with the next index, so the trace grows while the run is going."""
    last = AgentStep.objects.filter(run_id=run_id).aggregate(last=Max("index"))["last"]
    AgentStep.objects.create(
        run_id=run_id,
        index=0 if last is None else last + 1,
        estimated_cost_usd=_money(cost_usd),
        **fields,
    )


def save_event(run_id: str, **fields: Any) -> str:
    video_id = AnalysisRun.objects.values_list("video_id", flat=True).get(pk=run_id)
    event = Event.objects.create(run_id=run_id, video_id=video_id, **fields)
    return str(event.id)
