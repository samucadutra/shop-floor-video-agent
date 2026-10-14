"""Agent state and dependencies (docs/spec.md S1 design rule, S6.2)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict

from agent.event_types import EventType
from agent.guardrails import AgentLimits
from agent.providers.base import Frame
from agent.providers.client import LLMClient


class Budget(TypedDict):
    frames: int
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CandidateState(TypedDict):
    id: str  # "c1", "c2", ...
    event_type: str
    time_s: float
    reason: str
    status: Literal["open", "confirmed", "dropped"]
    looks: int  # how many times it was inspected
    drop_reason: str


class Window(TypedDict):
    id: str
    start_s: float
    end_s: float
    candidate_ids: list[str]
    question: str


class AgentState(TypedDict):
    run_id: str
    video_path: str
    duration_s: float
    event_types: list[dict]
    survey_frames: list[dict]  # Frame as dict (timestamp_s, path, source)
    scene_notes: list[str]
    candidates: list[CandidateState]
    windows: list[Window]  # windows chosen in the current iteration
    observations: list[dict]  # Observation dicts from the current iteration
    confirmed_events: list[dict]  # saved events: id, event_type, timestamp_s, severity, confidence
    iteration: int
    budget: Budget
    is_partial: bool
    stop_reason: str | None
    summary: str


def new_budget() -> Budget:
    return Budget(frames=0, llm_calls=0, input_tokens=0, output_tokens=0, cost_usd=0.0)


@dataclass(frozen=True)
class RunContext:
    run_id: str
    video_path: Path
    duration_s: float
    sha256: str
    filename: str


@dataclass(frozen=True)
class AgentParams:
    survey_interval_s: float
    scene_threshold: float
    inspect_fps: float
    window_padding_s: float
    frames_per_call: int
    frame_max_side: int
    confidence_threshold: float


class Repository(Protocol):
    """The agent's only database access (agent/repository.py)."""

    def record_step(self, run_id: str, **fields: Any) -> None: ...

    def save_event(self, run_id: str, **fields: Any) -> str: ...


@dataclass
class StepLog:
    """Tool calls and LLM usage of the step being recorded."""

    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    retried: bool = False


@dataclass
class AgentDeps:
    run: RunContext
    client: LLMClient
    limits: AgentLimits
    params: AgentParams
    event_types: list[EventType]
    repository: Repository
    frames_dir: Path
    media_root: Path
    budget: Budget = field(default_factory=new_budget)
    step: StepLog = field(default_factory=StepLog)
    frame_cache: dict[tuple, list[Frame]] = field(default_factory=dict)

    def begin_step(self) -> StepLog:
        self.step = StepLog()
        return self.step

    def event_type(self, key: str) -> EventType | None:
        return next((t for t in self.event_types if t.key == key), None)
