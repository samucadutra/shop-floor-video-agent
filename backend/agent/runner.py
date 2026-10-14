"""run_agent: builds the dependencies and invokes the graph for one run."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent import repository
from agent.event_types import load_event_types
from agent.graph import RECURSION_LIMIT, build_graph
from agent.nodes import AgentFailed
from agent.providers.base import QuotaExhaustedError
from agent.providers.client import LLMClient
from agent.providers.factory import ProviderConfigError, VideoInfo, build_provider
from agent.state import AgentDeps, AgentParams, AgentState, new_budget


@dataclass(frozen=True)
class AgentOutcome:
    summary: str
    is_partial: bool
    stop_reason: str
    iterations: int
    frames_analyzed: int
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


def build_params(settings: Any) -> AgentParams:
    return AgentParams(
        survey_interval_s=settings.SURVEY_INTERVAL_S,
        scene_threshold=settings.SCENE_THRESHOLD,
        inspect_fps=settings.INSPECT_FPS,
        window_padding_s=settings.WINDOW_PADDING_S,
        frames_per_call=settings.FRAMES_PER_CALL,
        frame_max_side=settings.FRAME_MAX_SIDE,
        confidence_threshold=settings.CONFIDENCE_THRESHOLD,
    )


def run_agent(run_id: str, settings: Any) -> AgentOutcome:
    """Run the agent on one AnalysisRun. Raises AgentFailed with a user-safe message."""
    run = repository.get_run_context(run_id)
    event_types = load_event_types(settings.EVENT_TYPES_FILE)
    try:
        provider = build_provider(settings, VideoInfo(run.sha256, run.filename, run.duration_s))
    except ProviderConfigError as exc:
        raise AgentFailed(str(exc)) from exc

    media_root = Path(settings.MEDIA_ROOT)
    deps = AgentDeps(
        run=run,
        client=LLMClient(provider, settings),
        limits=settings.AGENT,
        params=build_params(settings),
        event_types=event_types,
        repository=repository,
        frames_dir=media_root / "frames" / run_id,
        media_root=media_root,
    )
    initial = AgentState(
        run_id=run_id,
        video_path=str(run.video_path),
        duration_s=run.duration_s,
        event_types=[t.model_dump() for t in event_types],
        survey_frames=[],
        scene_notes=[],
        candidates=[],
        windows=[],
        observations=[],
        confirmed_events=[],
        iteration=0,
        budget=new_budget(),
        is_partial=False,
        stop_reason=None,
        summary="",
    )
    try:
        final = build_graph(deps).invoke(initial, config={"recursion_limit": RECURSION_LIMIT})
    except QuotaExhaustedError as exc:
        raise AgentFailed(str(exc)) from exc  # the provider's message is user-safe
    budget = final["budget"]
    return AgentOutcome(
        summary=final["summary"],
        is_partial=final["is_partial"],
        stop_reason=final["stop_reason"] or "completed",
        iterations=final["iteration"],
        frames_analyzed=budget["frames"],
        llm_calls=budget["llm_calls"],
        input_tokens=budget["input_tokens"],
        output_tokens=budget["output_tokens"],
        cost_usd=budget["cost_usd"],
    )
