"""Prompt builders, one per stage (docs/spec.md S6.8).

Prompts never include file system paths or settings.
"""

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from agent.event_types import EventType
from agent.providers.base import Frame
from agent.schemas import InspectResult, ReportResult, SurveyResult, VerifyResult

ROLE = "You are a safety inspector reviewing factory floor video frames."


def _event_types(event_types: Sequence[EventType]) -> str:
    lines = [f"- {t.key}: {t.description}" for t in event_types]
    return "Event types to look for:\n" + "\n".join(lines)


def _frames(frames: Sequence[Frame]) -> str:
    lines = [f"Image {i}: t = {f.timestamp_s:.2f} s" for i, f in enumerate(frames, start=1)]
    return "Frames (the images are attached in this order):\n" + "\n".join(lines)


def _compact(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"))


def _reply_format(schema: type[BaseModel]) -> str:
    return "Reply with JSON only, matching this JSON Schema:\n" + _compact(
        schema.model_json_schema()
    )


def _join(*parts: str) -> str:
    return "\n\n".join(parts)


def survey_prompt(event_types: Sequence[EventType], frames: Sequence[Frame]) -> str:
    task = (
        "Task: look at these low rate frames and list candidate moments that may show one of "
        "the event types. Give the event type key, the approximate time in seconds and a short "
        "reason. Only use the keys listed above. Also write short scene notes (place, machines, "
        "people). List nothing if nothing looks relevant."
    )
    return _join(
        ROLE, _event_types(event_types), _frames(frames), task, _reply_format(SurveyResult)
    )


def window_question(event_types: Sequence[EventType], candidates: Sequence[dict]) -> str:
    """The focused question for one window, from the event descriptions and candidate reasons."""
    by_key = {t.key: t for t in event_types}
    lines = []
    for c in candidates:
        description = by_key[c["event_type"]].description
        lines.append(
            f"{c['id']} ({c['event_type']}, ~{c['time_s']:.1f} s): {c['reason']} "
            f"Check: {description}"
        )
    return "Is each of these candidates really visible?\n" + "\n".join(lines)


def inspect_prompt(event_types: Sequence[EventType], frames: Sequence[Frame], question: str) -> str:
    task = (
        "Task: these frames are a closer look at a short time window. For each candidate in the "
        "question, give one observation: its candidate_id, whether it is seen, the time in "
        "seconds where it is clearest, and details of what you see.\n\n"
        f"Question: {question}"
    )
    return _join(
        ROLE, _event_types(event_types), _frames(frames), task, _reply_format(InspectResult)
    )


def verify_prompt(
    event_types: Sequence[EventType], candidates: Sequence[dict], observations: Sequence[dict]
) -> str:
    task = (
        "Task: decide each candidate from the observations (no images). Use 'confirm' when the "
        "event is clearly visible, 'drop' when it is not (give a drop_reason), and 'uncertain' "
        "when another, closer look is needed. Give the event type, the exact timestamp, the "
        "start and end of the event, a severity (low, medium or high), a confidence between 0 "
        "and 1 and a one sentence explanation.\n\n"
        f"Candidates: {_compact(candidates)}\n\nObservations: {_compact(observations)}"
    )
    return _join(ROLE, _event_types(event_types), task, _reply_format(VerifyResult))


def report_prompt(
    event_types: Sequence[EventType],
    events: Sequence[dict],
    scene_notes: Sequence[str],
    dropped: Sequence[dict],
    stop_reason: str | None,
) -> str:
    partial = (
        f"The analysis stopped early ({stop_reason}); say that the result is partial."
        if stop_reason
        else "The analysis finished normally."
    )
    task = (
        "Task: write a short summary of the whole video for a safety manager: the scene, each "
        "confirmed event with its time, and what was checked and dropped. "
        f"{partial}\n\n"
        f"Scene notes: {_compact(list(scene_notes))}\n\n"
        f"Confirmed events: {_compact(list(events))}\n\n"
        f"Dropped candidates: {_compact(list(dropped))}"
    )
    return _join(ROLE, _event_types(event_types), task, _reply_format(ReportResult))
