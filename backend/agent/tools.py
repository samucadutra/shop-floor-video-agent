"""The agent's tools: get_frames, analyze_frames, save_event (docs/spec.md S6.6).

Plain functions bound to AgentDeps. Each call is added to the current step's tool_calls.
"""

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel

from agent.guardrails import BudgetExhausted, limit_hit
from agent.providers.base import (
    Frame,
    LLMOutputError,
    LLMRequest,
    QuotaExhaustedError,
    RetryableLLMError,
    Stage,
)
from agent.state import AgentDeps
from media_tools.ffmpeg import ExtractedFrame, extract_scenes, extract_survey, extract_window

SCENE_MIN_GAP_S = 1.0


def _log(deps: AgentDeps, tool: str, args: dict[str, Any], output_summary: str) -> None:
    deps.step.tool_calls.append({"tool": tool, "args": args, "output_summary": output_summary})


def _frames(extracted: list[ExtractedFrame], source: Literal["survey", "scene", "window"]):
    return [Frame(f.timestamp_s, f.path, source) for f in extracted]


def _survey_frames(deps: AgentDeps) -> tuple[list[Frame], str]:
    """Interval frames + scene change frames, within 50% of the frame limit."""
    params, duration = deps.params, deps.run.duration_s
    cap = max(1, deps.limits.max_frames // 2)
    interval = params.survey_interval_s
    if duration / interval + 1 > cap:
        interval = duration / max(cap - 1, 1)  # widen the interval to stay within the cap
    video, out, side = deps.run.video_path, deps.frames_dir, params.frame_max_side

    survey = _frames(extract_survey(video, out, interval, max_side=side), "survey")[:cap]
    scenes = [
        f
        for f in _frames(extract_scenes(video, out, params.scene_threshold, max_side=side), "scene")
        if all(abs(f.timestamp_s - s.timestamp_s) >= SCENE_MIN_GAP_S for s in survey)
    ][: cap - len(survey)]
    frames = sorted(survey + scenes, key=lambda f: f.timestamp_s)
    note = f"{len(survey)} interval frames (1 per {interval:g} s) + {len(scenes)} scene frames"
    return frames, note


def get_frames(
    deps: AgentDeps,
    start: float,
    end: float,
    fps: float,
    *,
    mode: Literal["survey", "window"] = "window",
) -> list[Frame]:
    """Extract frames to MEDIA_ROOT/frames/<run_id>/, cached per run, counted against the budget."""
    args = {"start": round(start, 2), "end": round(end, 2), "fps": round(fps, 3), "mode": mode}
    key = (mode, round(start, 2), round(end, 2), fps)
    if key in deps.frame_cache:
        frames = deps.frame_cache[key]
        _log(deps, "get_frames", args, f"{len(frames)} frames (cached)")
        return frames

    if mode == "survey":
        frames, note = _survey_frames(deps)
    else:
        extracted = extract_window(
            deps.run.video_path,
            deps.frames_dir,
            start,
            end,
            fps,
            max_side=deps.params.frame_max_side,
        )
        frames, note = _frames(extracted, "window"), f"{len(extracted)} frames"

    if deps.budget["frames"] + len(frames) > deps.limits.max_frames:
        _log(deps, "get_frames", args, f"blocked: {len(frames)} frames would pass max_frames")
        raise BudgetExhausted("max_frames")
    deps.budget["frames"] += len(frames)
    deps.frame_cache[key] = frames
    _log(deps, "get_frames", args, note)
    return frames


def analyze_frames[T: BaseModel](
    deps: AgentDeps,
    frames: list[Frame],
    prompt: str,
    *,
    stage: Stage,
    schema: type[T],
    payload: Mapping[str, Any],
) -> T:
    """Call the LLM through LLMClient and add tokens, cost and calls to the budget."""
    args = {"stage": stage, "frames": len(frames)}
    # Only the report may use the reserved tokens and the last LLM call.
    reason = limit_hit(deps.budget, deps.limits, reserve=stage != "report", frames=False)
    if reason:
        _log(deps, "analyze_frames", args, f"blocked: {reason}")
        raise BudgetExhausted(reason)

    request = LLMRequest(stage, prompt, schema, tuple(frames), payload)
    try:
        result = deps.client.analyze(request)
    except LLMOutputError as exc:
        _add_usage(deps, exc.input_tokens, exc.output_tokens, calls=2)
        _log(deps, "analyze_frames", args, "invalid output after a retry")
        raise
    except (RetryableLLMError, QuotaExhaustedError) as exc:
        _log(deps, "analyze_frames", args, f"failed: {exc}")
        raise

    _add_usage(deps, result.input_tokens, result.output_tokens, calls=result.attempts)
    deps.step.retried = deps.step.retried or result.attempts > 1
    _log(
        deps,
        "analyze_frames",
        args,
        f"{schema.__name__}, {result.attempts} attempt(s), "
        f"{result.input_tokens}+{result.output_tokens} tokens",
    )
    return result.parsed  # type: ignore[return-value]


def _add_usage(deps: AgentDeps, input_tokens: int, output_tokens: int, *, calls: int) -> None:
    cost = deps.client.cost(input_tokens, output_tokens)
    deps.budget["llm_calls"] += calls
    deps.budget["input_tokens"] += input_tokens
    deps.budget["output_tokens"] += output_tokens
    deps.budget["cost_usd"] += cost
    deps.step.input_tokens += input_tokens
    deps.step.output_tokens += output_tokens
    deps.step.cost_usd += cost


def save_event(
    deps: AgentDeps,
    event_type: str,
    timestamp_s: float,
    start_s: float,
    end_s: float,
    severity: str,
    confidence: float,
    explanation: str,
    frame_ref: str,
) -> str:
    """Validate and persist a confirmed event. Raises ValueError on invalid values."""
    duration = deps.run.duration_s
    if deps.event_type(event_type) is None:
        raise ValueError(f"unknown event type {event_type!r}")
    if not 0 <= confidence <= 1:
        raise ValueError(f"confidence {confidence} is outside 0-1")
    if not 0 <= timestamp_s <= duration:
        raise ValueError(f"timestamp {timestamp_s} s is outside the video (0-{duration} s)")

    event_id = deps.repository.save_event(
        deps.run.run_id,
        event_type=event_type,
        timestamp_s=timestamp_s,
        start_s=max(0.0, min(start_s, timestamp_s)),
        end_s=min(duration, max(end_s, timestamp_s)),
        severity=severity,
        confidence=confidence,
        explanation=explanation,
        frame_ref=frame_ref,
    )
    _log(
        deps,
        "save_event",
        {"event_type": event_type, "timestamp_s": timestamp_s, "severity": severity},
        f"event {event_id}",
    )
    return event_id
