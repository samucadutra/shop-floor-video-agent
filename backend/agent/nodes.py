"""Graph nodes: survey, plan, inspect, verify, report (docs/spec.md S6.4).

Each node records one AgentStep (inspect records one per window) and returns a state update.
"""

import math
import time
from pathlib import Path
from typing import Any

from agent import prompts, tools
from agent.guardrails import BudgetExhausted, budget_exceeded
from agent.providers.base import LLMOutputError, RetryableLLMError
from agent.schemas import InspectResult, ReportResult, SurveyResult, VerifyResult
from agent.state import AgentDeps, AgentState, CandidateState, Window

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}
# LLM failures that end a step: invalid output after the retry, or no answer after the backoff.
STEP_ERRORS = (LLMOutputError, RetryableLLMError)


class AgentFailed(Exception):
    """The run cannot continue (survey or report failed). The message is safe for users."""


# Helpers ----------------------------------------------------------------------------------


def _record(
    deps: AgentDeps,
    node: str,
    iteration: int,
    input_summary: str,
    decision: str,
    started: float,
    *,
    error: str = "",
) -> None:
    step = deps.step
    status = "error" if error else ("retried" if step.retried else "ok")
    deps.repository.record_step(
        deps.run.run_id,
        node=node,
        iteration=iteration,
        input_summary=input_summary,
        decision=decision,
        tool_calls=step.tool_calls,
        input_tokens=step.input_tokens,
        output_tokens=step.output_tokens,
        cost_usd=step.cost_usd,
        latency_ms=int((time.monotonic() - started) * 1000),
        status=status,
        error_message=error,
    )


def _stop(state: AgentState, reason: str) -> dict[str, Any]:
    """Mark the run partial. The first stop reason wins."""
    return {"is_partial": True, "stop_reason": state["stop_reason"] or reason}


def _ref(deps: AgentDeps, path: Path) -> str:
    """Frame path relative to MEDIA_ROOT (never an absolute path)."""
    try:
        return str(path.relative_to(deps.media_root))
    except ValueError:
        return path.name


def _why(exc: Exception) -> str:
    if isinstance(exc, RetryableLLMError):
        return "the LLM provider did not answer after several retries"
    return "the model returned invalid output"


def _brief(candidate: CandidateState) -> dict[str, Any]:
    keys = ("id", "event_type", "time_s", "reason")
    return {k: candidate[k] for k in keys}


def _drop(candidate: CandidateState, reason: str) -> str:
    candidate["status"] = "dropped"
    candidate["drop_reason"] = reason
    return f"dropped {candidate['id']} {candidate['event_type']}: {reason}"


# Nodes ------------------------------------------------------------------------------------


def survey(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    started = time.monotonic()
    deps.begin_step()
    duration, params = deps.run.duration_s, deps.params
    frames = tools.get_frames(deps, 0.0, duration, 1 / params.survey_interval_s, mode="survey")
    batches = [
        frames[i : i + params.frames_per_call]
        for i in range(0, len(frames), params.frames_per_call)
    ]
    scenes = sum(f.source == "scene" for f in frames)
    input_summary = (
        f"{len(frames)} frames ({len(frames) - scenes} interval + {scenes} scene change), "
        f"0–{duration:.1f} s, {len(batches)} batch(es)"
    )

    updates: dict[str, Any] = {}
    raw, notes, ignored = [], [], []
    for batch in batches:
        prompt = prompts.survey_prompt(deps.event_types, batch)
        payload = {"frame_times": [f.timestamp_s for f in batch]}
        try:
            result = tools.analyze_frames(
                deps, batch, prompt, stage="survey", schema=SurveyResult, payload=payload
            )
        except STEP_ERRORS as exc:
            _record(deps, "survey", 0, input_summary, "survey failed", started, error=str(exc))
            raise AgentFailed(f"The survey step failed: {_why(exc)}.") from exc
        except BudgetExhausted as exc:
            updates = _stop(state, exc.reason)
            ignored.append(f"remaining batches skipped ({exc.reason})")
            break
        raw.extend(result.candidates)
        if result.scene_notes:
            notes.append(result.scene_notes)

    candidates: list[CandidateState] = []
    for c in raw:
        label = f"{c.event_type} ~{c.time_s:.1f} s"
        if deps.event_type(c.event_type) is None:
            ignored.append(f"{label}: unknown event type")
            continue
        if c.time_s > duration:
            ignored.append(f"{label}: after the end of the video")
            continue
        same = next(
            (
                k
                for k in candidates
                if k["event_type"] == c.event_type
                and abs(k["time_s"] - c.time_s) <= params.window_padding_s
            ),
            None,
        )
        if same:
            ignored.append(f"{label}: same as {same['id']}")
            continue
        candidates.append(
            CandidateState(
                id=f"c{len(candidates) + 1}",
                event_type=c.event_type,
                time_s=c.time_s,
                reason=c.reason,
                status="open",
                looks=0,
                drop_reason="",
            )
        )

    found = ", ".join(f"{c['event_type']} ~{c['time_s']:.1f} s ({c['id']})" for c in candidates)
    decision = f"{len(candidates)} candidate(s)" + (f": {found}" if found else "")
    if ignored:
        decision += "; ignored: " + "; ".join(ignored)
    error = f"Budget limit reached: {updates['stop_reason']}" if updates else ""
    _record(deps, "survey", 0, input_summary, decision, started, error=error)
    return {
        "survey_frames": [
            {"timestamp_s": f.timestamp_s, "path": _ref(deps, f.path), "source": f.source}
            for f in frames
        ],
        "scene_notes": notes,
        "candidates": candidates,
        "budget": dict(deps.budget),
        **updates,
    }


def plan(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    """Deterministic: choose the windows to inspect in this iteration (no LLM call)."""
    started = time.monotonic()
    deps.begin_step()
    params, limits, duration = deps.params, deps.limits, deps.run.duration_s
    iteration = state["iteration"] + 1
    open_ = [c for c in state["candidates"] if c["status"] == "open"]
    frames_used = deps.budget["frames"]
    input_summary = (
        f"iteration {iteration}: {len(open_)} open candidate(s), "
        f"{frames_used} of {limits.max_frames} frames used"
    )
    if state["stop_reason"] or not open_:
        why = f"stopped ({state['stop_reason']})" if state["stop_reason"] else "nothing open"
        _record(deps, "plan", iteration, input_summary, f"no windows: {why}", started)
        return {"windows": [], "iteration": iteration}

    # One window per candidate, wider on each new look, then merge the overlapping ones.
    spans = []
    for c in open_:
        pad = params.window_padding_s * (1 + c["looks"])
        spans.append([max(0.0, c["time_s"] - pad), min(duration, c["time_s"] + pad), [c]])
    merged: list[list] = []
    for start, end, members in sorted(spans, key=lambda s: s[0]):
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
            merged[-1][2].extend(members)
        else:
            merged.append([start, end, list(members)])

    def rank(span: list) -> tuple:
        severity = max(
            SEVERITY_RANK[deps.event_type(c["event_type"]).default_severity]  # type: ignore[union-attr]
            for c in span[2]
        )
        return (-severity, -len(span[2]), span[0])

    windows: list[Window] = []
    chosen, skipped = [], []
    for start, end, members in sorted(merged, key=rank):
        need = math.ceil((end - start) * params.inspect_fps)
        names = ", ".join(f"{c['id']} {c['event_type']}" for c in members)
        label = f"{start:.1f}–{end:.1f} s ({names})"
        if frames_used + need <= limits.max_frames:
            frames_used += need
            chosen.append(label)
            windows.append(
                Window(
                    id=f"w{iteration}.{len(windows) + 1}",
                    start_s=round(start, 2),
                    end_s=round(end, 2),
                    candidate_ids=[c["id"] for c in members],
                    question=prompts.window_question(deps.event_types, members),
                )
            )
        else:
            skipped.append(f"{label}: needs {need} frames, {limits.max_frames - frames_used} left")

    updates: dict[str, Any] = {}
    parts = []
    if chosen:
        parts.append("inspect " + "; ".join(chosen))
    if skipped:
        parts.append("skip " + "; ".join(skipped))
    if not windows:
        updates = _stop(state, "max_frames")
        parts.append("no window fits the frame budget: go to report")
    _record(deps, "plan", iteration, input_summary, " | ".join(parts), started)
    return {"windows": windows, "iteration": iteration, "observations": [], **updates}


def inspect(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    """One focused LLM call per window, on frames at INSPECT_FPS."""
    candidates = [CandidateState(**c) for c in state["candidates"]]
    by_id = {c["id"]: c for c in candidates}
    observations: list[dict] = []
    updates: dict[str, Any] = {}
    windows = state["windows"]

    for n, window in enumerate(windows):
        started = time.monotonic()
        deps.begin_step()
        members = [by_id[i] for i in window["candidate_ids"]]
        span = f"{window['start_s']:.1f}–{window['end_s']:.1f} s"
        input_summary = f"window {window['id']} {span}, question: {window['question']}"
        try:
            frames = tools.get_frames(
                deps, window["start_s"], window["end_s"], deps.params.inspect_fps
            )
            input_summary = f"{len(frames)} frames, {input_summary}"
            prompt = prompts.inspect_prompt(deps.event_types, frames, window["question"])
            result = tools.analyze_frames(
                deps,
                frames,
                prompt,
                stage="inspect",
                schema=InspectResult,
                payload={"candidates": [_brief(c) for c in members]},
            )
        except BudgetExhausted as exc:
            updates = _stop(state, exc.reason)
            left = len(windows) - n
            decision = f"stopped: {exc.reason}; {left} window(s) not inspected"
            _record(
                deps,
                "inspect",
                state["iteration"],
                input_summary,
                decision,
                started,
                error=f"Budget limit reached: {exc.reason}",
            )
            break
        except STEP_ERRORS as exc:
            lines = []
            for c in members:
                c["looks"] += 1
                lines.append(_drop(c, "analysis failed"))
            _record(
                deps,
                "inspect",
                state["iteration"],
                input_summary,
                "; ".join(lines),
                started,
                error=str(exc),
            )
            continue

        lines = []
        frame_refs = [[f.timestamp_s, _ref(deps, f.path)] for f in frames]
        for c in members:
            c["looks"] += 1
        for o in result.observations:
            if o.candidate_id not in window["candidate_ids"]:
                lines.append(f"ignored observation for unknown candidate {o.candidate_id}")
                continue
            observations.append({**o.model_dump(), "window_id": window["id"], "frames": frame_refs})
            seen = f"seen at {o.time_s:.1f} s" if o.seen else "not seen"
            lines.append(f"{o.candidate_id} {seen}: {o.details[:120]}")
        _record(deps, "inspect", state["iteration"], input_summary, "; ".join(lines), started)

    return {
        "candidates": candidates,
        "observations": observations,
        "budget": dict(deps.budget),
        **updates,
    }


def _frame_ref(observations: list[dict], candidate_id: str, timestamp_s: float) -> str:
    """The inspected frame closest to the event time, or the time itself."""
    frames = [f for o in observations if o["candidate_id"] == candidate_id for f in o["frames"]]
    if not frames:
        return f"{timestamp_s:.1f}"
    return min(frames, key=lambda f: abs(f[0] - timestamp_s))[1]


def verify(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    """One text only LLM call per iteration: confirm, drop or keep each candidate open."""
    started = time.monotonic()
    deps.begin_step()
    candidates = [CandidateState(**c) for c in state["candidates"]]
    confirmed_events = list(state["confirmed_events"])
    observations = state["observations"]
    in_windows = {cid for w in state["windows"] for cid in w["candidate_ids"]}
    targets = {c["id"]: c for c in candidates if c["id"] in in_windows and c["status"] == "open"}
    seen_obs = [
        {k: o[k] for k in ("candidate_id", "seen", "time_s", "details")}
        for o in observations
        if o["candidate_id"] in targets
    ]
    input_summary = f"{len(targets)} candidate(s), {len(seen_obs)} observation(s) (text only)"
    updates: dict[str, Any] = {}
    lines: list[str] = []
    error = ""

    if not targets:
        lines.append("nothing to verify")
    else:
        briefs = [_brief(c) for c in targets.values()]
        prompt = prompts.verify_prompt(deps.event_types, briefs, seen_obs)
        try:
            result = tools.analyze_frames(
                deps,
                [],
                prompt,
                stage="verify",
                schema=VerifyResult,
                payload={"candidates": briefs, "observations": seen_obs},
            )
        except BudgetExhausted as exc:
            updates = _stop(state, exc.reason)
            error = f"Budget limit reached: {exc.reason}"
            lines.append(f"not verified ({exc.reason})")
        except STEP_ERRORS as exc:
            error = str(exc)
            lines.extend(_drop(c, "verification failed") for c in targets.values())
        else:
            threshold = deps.params.confidence_threshold
            for d in result.decisions:
                c = targets.get(d.candidate_id)
                if c is None or c["status"] != "open":
                    lines.append(f"ignored decision for {d.candidate_id}")
                elif d.decision == "uncertain":
                    lines.append(f"{c['id']} uncertain: needs another look")
                elif d.decision == "drop":
                    lines.append(_drop(c, d.drop_reason or d.explanation or "not confirmed"))
                elif d.confidence < threshold:
                    lines.append(_drop(c, f"confidence {d.confidence:.2f} below {threshold}"))
                else:
                    try:
                        event_id = tools.save_event(
                            deps,
                            d.event_type,
                            d.timestamp_s,
                            d.start_s,
                            d.end_s,
                            d.severity,
                            d.confidence,
                            d.explanation,
                            _frame_ref(observations, c["id"], d.timestamp_s),
                        )
                    except ValueError as exc:
                        lines.append(_drop(c, f"invalid event ({exc})"))
                        continue
                    c["status"] = "confirmed"
                    confirmed_events.append(
                        {
                            "id": event_id,
                            "event_type": d.event_type,
                            "timestamp_s": d.timestamp_s,
                            "severity": d.severity,
                            "confidence": d.confidence,
                        }
                    )
                    lines.append(
                        f"confirmed {c['id']} {d.event_type} at {d.timestamp_s:.1f} s "
                        f"({d.severity}, confidence {d.confidence:.2f})"
                    )

    # Stop conditions (S6.5), decided here because routing functions cannot change the state.
    still_open = [c for c in candidates if c["status"] == "open"]
    if still_open and not (updates or state["stop_reason"]):
        reason = budget_exceeded({"budget": deps.budget}, deps.limits)
        if reason:
            updates = _stop(state, reason)
            lines.append(f"stop: {reason}")
        elif state["iteration"] >= deps.limits.max_iterations:
            lines.extend(_drop(c, "unresolved") for c in still_open)
            updates = _stop(state, "max_iterations")
            lines.append("stop: max_iterations")

    _record(
        deps, "verify", state["iteration"], input_summary, "; ".join(lines), started, error=error
    )
    return {
        "candidates": candidates,
        "confirmed_events": confirmed_events,
        "budget": dict(deps.budget),
        **updates,
    }


def report(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    """One text only LLM call that writes the summary. It may use the reserved budget."""
    started = time.monotonic()
    deps.begin_step()
    events = [
        {k: e[k] for k in ("event_type", "timestamp_s", "severity", "confidence")}
        for e in state["confirmed_events"]
    ]
    dropped = [
        {"event_type": c["event_type"], "time_s": c["time_s"], "drop_reason": c["drop_reason"]}
        for c in state["candidates"]
        if c["status"] == "dropped"
    ]
    stop_reason, is_partial = state["stop_reason"], state["is_partial"]
    input_summary = (
        f"{len(events)} confirmed event(s), {len(dropped)} dropped candidate(s), "
        f"{len(state['scene_notes'])} scene note(s)"
    )
    prompt = prompts.report_prompt(
        deps.event_types, events, state["scene_notes"], dropped, stop_reason
    )
    payload = {"events": events, "dropped": dropped, "scene_notes": state["scene_notes"]}
    error = ""
    try:
        result = tools.analyze_frames(
            deps, [], prompt, stage="report", schema=ReportResult, payload=payload
        )
        summary = result.summary
    except STEP_ERRORS as exc:
        _record(
            deps,
            "report",
            state["iteration"],
            input_summary,
            "report failed",
            started,
            error=str(exc),
        )
        raise AgentFailed(f"The report step failed: {_why(exc)}.") from exc
    except BudgetExhausted as exc:
        stop_reason, is_partial = stop_reason or exc.reason, True
        error = f"Budget limit reached: {exc.reason}"
        summary = (
            f"{len(events)} event(s) confirmed. The summary could not be written because a "
            f"budget limit was reached ({exc.reason})."
        )

    stop_reason = stop_reason or "completed"
    decision = f"summary written ({len(summary)} chars); stop reason: {stop_reason}"
    if is_partial:
        decision += " (partial result)"
    _record(deps, "report", state["iteration"], input_summary, decision, started, error=error)
    return {
        "summary": summary,
        "stop_reason": stop_reason,
        "is_partial": is_partial,
        "budget": dict(deps.budget),
    }
