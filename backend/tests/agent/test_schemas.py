import pytest
from pydantic import ValidationError

from agent.schemas import (
    Candidate,
    InspectResult,
    ReportResult,
    SurveyResult,
    VerifyDecision,
    VerifyResult,
)

DECISION = {
    "candidate_id": "c1",
    "decision": "confirm",
    "event_type": "missing_ppe",
    "timestamp_s": 2.0,
    "start_s": 1.0,
    "end_s": 3.0,
    "severity": "medium",
    "confidence": 0.8,
    "explanation": "No hard hat.",
}


def test_valid_payloads() -> None:
    survey = SurveyResult.model_validate(
        {"candidates": [{"event_type": "missing_ppe", "time_s": 1.5, "reason": "No hat."}]}
    )
    assert survey.candidates[0].time_s == 1.5
    assert survey.scene_notes == ""
    inspect = InspectResult.model_validate(
        {"observations": [{"candidate_id": "c1", "seen": True, "time_s": 2, "details": "Hat."}]}
    )
    assert inspect.observations[0].seen is True
    assert VerifyResult.model_validate({"decisions": [DECISION]}).decisions[0].confidence == 0.8
    assert ReportResult.model_validate({"summary": "All good."}).summary == "All good."


@pytest.mark.parametrize(
    "changes",
    [
        {"confidence": 1.2},
        {"confidence": -0.1},
        {"severity": "critical"},
        {"decision": "maybe"},
        {"timestamp_s": -1},
        {"timestamp_s": 5.0},  # after end_s
        {"start_s": 2.5},  # after timestamp_s
        {"explanation": "x" * 501},
    ],
)
def test_invalid_verify_decision(changes: dict) -> None:
    with pytest.raises(ValidationError):
        VerifyDecision.model_validate(DECISION | changes)


@pytest.mark.parametrize(
    "payload",
    [
        {"event_type": "missing_ppe", "time_s": -1, "reason": "x"},
        {"event_type": "missing_ppe", "time_s": 1, "reason": ""},
        {"event_type": "missing_ppe", "time_s": 1, "reason": "x" * 301},
        {"time_s": 1, "reason": "x"},
    ],
)
def test_invalid_candidate(payload: dict) -> None:
    with pytest.raises(ValidationError):
        Candidate.model_validate(payload)


def test_survey_limits_and_missing_fields() -> None:
    candidate = {"event_type": "missing_ppe", "time_s": 1, "reason": "x"}
    with pytest.raises(ValidationError):
        SurveyResult.model_validate({"candidates": [candidate] * 21})
    with pytest.raises(ValidationError):
        SurveyResult.model_validate({"scene_notes": "x" * 501})
    with pytest.raises(ValidationError):
        InspectResult.model_validate({})
    with pytest.raises(ValidationError):
        ReportResult.model_validate({"summary": ""})
