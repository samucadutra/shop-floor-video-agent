"""Deterministic, fixture driven provider for offline demos and tests (docs/spec.md S7.4).

Its replies are JSON text that goes through the same validation path as a real provider.
"""

import json
import time
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agent.providers.base import BaseProvider, LLMRequest, RawResponse, Stage
from agent.providers.factory import VideoInfo
from agent.schemas import Severity

FIXTURES_DIR = Path(__file__).parent / "mock_fixtures"
GENERIC_FIXTURE = FIXTURES_DIR / "generic.yaml"
BROKEN_JSON = '{"this is": not valid json'


class FixtureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    time_s: float = Field(ge=0)
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    explanation: str
    uncertain: bool = False  # test hook: verify always answers "uncertain"


class FixtureDecoy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    time_s: float = Field(ge=0)
    reason: str
    drop_reason: str


class MockFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str | None = None
    filename: str | None = None
    relative_times: bool = False  # times are fractions of the video duration (generic.yaml)
    scene_notes: str = ""
    events: list[FixtureEvent] = Field(default_factory=list)
    decoys: list[FixtureDecoy] = Field(default_factory=list)
    # Test hooks.
    invalid_json_once: list[Stage] = Field(default_factory=list)
    error_on: list[Stage] = Field(default_factory=list)

    def scaled_to(self, duration_s: float) -> Self:
        if not self.relative_times:
            return self
        events = [
            e.model_copy(
                update={
                    "time_s": round(e.time_s * duration_s, 2),
                    "start_s": round(e.start_s * duration_s, 2),
                    "end_s": round(e.end_s * duration_s, 2),
                }
            )
            for e in self.events
        ]
        decoys = [
            d.model_copy(update={"time_s": round(d.time_s * duration_s, 2)}) for d in self.decoys
        ]
        return self.model_copy(update={"events": events, "decoys": decoys, "relative_times": False})


def _read(path: Path) -> MockFixture:
    return MockFixture.model_validate(yaml.safe_load(path.read_text()))


def load_fixture(video_info: VideoInfo) -> MockFixture:
    """Match by SHA-256, then by file name; fall back to generic.yaml."""
    fixtures = [_read(p) for p in sorted(FIXTURES_DIR.glob("*.yaml")) if p != GENERIC_FIXTURE]
    match = next((f for f in fixtures if f.sha256 and f.sha256 == video_info.sha256), None)
    if match is None:
        match = next(
            (f for f in fixtures if f.filename and f.filename == video_info.filename), None
        )
    if match is None:
        match = _read(GENERIC_FIXTURE)
    return match.scaled_to(video_info.duration_s)


class MockProvider(BaseProvider):
    name = "mock"
    model = ""
    throttled = False

    def __init__(self, video_info: VideoInfo, latency_ms: int = 0) -> None:
        self.fixture = load_fixture(video_info)
        self.latency_ms = latency_ms
        self._broken_once: set[str] = set()

    def complete(self, request: LLMRequest, extra_instruction: str | None = None) -> RawResponse:
        if self.latency_ms:
            time.sleep(self.latency_ms / 1000)
        text = self._reply(request)
        return RawResponse(
            text=text,
            input_tokens=300 + 260 * len(request.frames) + len(request.prompt) // 4,
            output_tokens=len(text) // 4,
        )

    def _reply(self, request: LLMRequest) -> str:
        stage = request.stage
        if stage in self.fixture.error_on:
            return BROKEN_JSON
        if stage in self.fixture.invalid_json_once and stage not in self._broken_once:
            self._broken_once.add(stage)
            return BROKEN_JSON
        body = getattr(self, f"_{stage}")(request)
        return json.dumps(body)

    def _item(self, candidate: dict[str, Any]) -> FixtureEvent | FixtureDecoy | None:
        """The fixture event or decoy of the same type closest in time to a candidate."""
        items = [
            i
            for i in [*self.fixture.events, *self.fixture.decoys]
            if i.event_type == candidate["event_type"]
        ]
        return min(items, key=lambda i: abs(i.time_s - candidate["time_s"]), default=None)

    def _survey(self, request: LLMRequest) -> dict[str, Any]:
        times = [f.timestamp_s for f in request.frames]
        low, high = min(times) - 1, max(times) + 1
        candidates = [
            {"event_type": e.event_type, "time_s": e.time_s, "reason": e.explanation[:300]}
            for e in self.fixture.events
            if low <= e.time_s <= high
        ] + [
            {"event_type": d.event_type, "time_s": d.time_s, "reason": d.reason[:300]}
            for d in self.fixture.decoys
            if low <= d.time_s <= high
        ]
        return {"candidates": candidates, "scene_notes": self.fixture.scene_notes[:500]}

    def _inspect(self, request: LLMRequest) -> dict[str, Any]:
        observations = []
        for candidate in request.payload["candidates"]:
            item = self._item(candidate)
            seen = isinstance(item, FixtureEvent)
            if isinstance(item, FixtureEvent):
                details = item.explanation
            elif isinstance(item, FixtureDecoy):
                details = item.drop_reason
            else:
                details = "Nothing matching was seen in these frames."
            observations.append(
                {
                    "candidate_id": candidate["id"],
                    "seen": seen,
                    "time_s": item.time_s if seen and item else candidate["time_s"],
                    "details": details[:500],
                }
            )
        return {"observations": observations}

    def _verify(self, request: LLMRequest) -> dict[str, Any]:
        decisions = []
        for candidate in request.payload["candidates"]:
            item = self._item(candidate)
            if isinstance(item, FixtureEvent):
                decisions.append(
                    {
                        "candidate_id": candidate["id"],
                        "decision": "uncertain" if item.uncertain else "confirm",
                        "event_type": item.event_type,
                        "timestamp_s": item.time_s,
                        "start_s": item.start_s,
                        "end_s": item.end_s,
                        "severity": item.severity,
                        "confidence": item.confidence,
                        "explanation": item.explanation[:500],
                    }
                )
            else:
                reason = item.drop_reason if item else "Not seen in the frames."
                decisions.append(
                    {
                        "candidate_id": candidate["id"],
                        "decision": "drop",
                        "event_type": candidate["event_type"],
                        "timestamp_s": candidate["time_s"],
                        "start_s": candidate["time_s"],
                        "end_s": candidate["time_s"],
                        "severity": "low",
                        "confidence": 0.1,
                        "explanation": reason[:500],
                        "drop_reason": reason,
                    }
                )
        return {"decisions": decisions}

    def _report(self, request: LLMRequest) -> dict[str, Any]:
        events = request.payload["events"]
        parts = [self.fixture.scene_notes] if self.fixture.scene_notes else []
        if events:
            found = "; ".join(
                f"{e['event_type'].replace('_', ' ')} at {e['timestamp_s']:.1f} s ({e['severity']})"
                for e in events
            )
            parts.append(f"{len(events)} event(s) confirmed: {found}.")
        else:
            parts.append("No safety events were confirmed.")
        dropped = len(request.payload["dropped"])
        if dropped:
            parts.append(f"{dropped} candidate(s) were dropped after a closer look.")
        return {"summary": " ".join(parts)[:1500]}
