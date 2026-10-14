"""Pydantic schemas for the LLM output of each stage (docs/spec.md S8).

Checks that need run context (known event type, known candidate id, time <= duration)
are done in the nodes after parsing.
"""

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

Severity = Literal["low", "medium", "high"]


class Candidate(BaseModel):
    event_type: str
    time_s: float = Field(ge=0)
    reason: str = Field(min_length=1, max_length=300)


class SurveyResult(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list, max_length=20)
    scene_notes: str = Field(default="", max_length=500)


class Observation(BaseModel):
    candidate_id: str
    seen: bool
    time_s: float = Field(ge=0)
    details: str = Field(max_length=500)


class InspectResult(BaseModel):
    observations: list[Observation]


class VerifyDecision(BaseModel):
    candidate_id: str
    decision: Literal["confirm", "drop", "uncertain"]
    event_type: str
    timestamp_s: float = Field(ge=0)
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(max_length=500)
    drop_reason: str | None = None

    @model_validator(mode="after")
    def check_window(self) -> Self:
        if not self.start_s <= self.timestamp_s <= self.end_s:
            raise ValueError("start_s <= timestamp_s <= end_s must hold")
        return self


class VerifyResult(BaseModel):
    decisions: list[VerifyDecision]


class ReportResult(BaseModel):
    summary: str = Field(min_length=1, max_length=1500)
