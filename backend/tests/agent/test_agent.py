"""Full agent runs with the mock provider on a 10 s test clip (no network)."""

import dataclasses
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from agent import runner
from agent.providers import mock
from agent.providers.base import LLMRequest, QuotaExhaustedError, RawResponse, RetryableLLMError
from agent.providers.gemini import QUOTA_MESSAGE
from videos.models import AgentStep, AnalysisRun, Event, Video

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("celery_eager")]

# Survey frames of the 10 s clip are at 0, 2, 4, 6 and 8 s.
TEST_FIXTURE = {
    "filename": "clip.mp4",
    "scene_notes": "Test pattern clip.",
    "events": [
        {
            "event_type": "missing_ppe",
            "time_s": 1.0,
            "start_s": 0.0,
            "end_s": 2.0,
            "severity": "medium",
            "confidence": 0.9,
            "explanation": "A worker without a hard hat.",
        },
        {
            "event_type": "unsafe_proximity",
            "time_s": 9.0,
            "start_s": 8.0,
            "end_s": 10.0,
            "severity": "high",
            "confidence": 0.8,
            "explanation": "A worker next to a moving forklift.",
        },
    ],
    "decoys": [
        {
            "event_type": "missing_ppe",
            "time_s": 5.0,
            "reason": "Head partly hidden.",
            "drop_reason": "The worker wears a hard hat.",
        }
    ],
}


@pytest.fixture
def write_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Point the mock at a temporary fixture directory and write the test fixture there."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    monkeypatch.setattr(mock, "FIXTURES_DIR", fixtures)

    def _write(**changes) -> None:
        data = TEST_FIXTURE | changes
        (fixtures / "clip.yaml").write_text(yaml.safe_dump(data))

    _write()
    return _write


@pytest.fixture
def video(make_test_video, write_fixture) -> Video:
    path = make_test_video(seconds=10)
    upload = SimpleUploadedFile("clip.mp4", path.read_bytes(), content_type="video/mp4")
    response = APIClient().post("/api/videos/", {"file": upload}, format="multipart")
    assert response.status_code == 201
    return Video.objects.get(pk=response.json()["id"])


@pytest.fixture
def analyze(django_capture_on_commit_callbacks) -> Callable[[Video], AnalysisRun]:
    """Start an analysis through the API and run the Celery task eagerly."""

    def _analyze(video: Video) -> AnalysisRun:
        with django_capture_on_commit_callbacks(execute=True):
            response = APIClient().post(f"/api/videos/{video.id}/analyze/")
        assert response.status_code == 202
        return AnalysisRun.objects.get(pk=response.json()["run_id"])

    return _analyze


@pytest.fixture
def limits(settings) -> Callable[..., None]:
    def _set(**changes) -> None:
        settings.AGENT = dataclasses.replace(settings.AGENT, **changes)

    return _set


class FailingProvider(mock.MockProvider):
    """The mock, but calls for `stage` raise `error` (as a real provider would)."""

    name = "fake"
    throttled = True

    def __init__(self, video_info, stage: str, error: Exception) -> None:
        super().__init__(video_info)
        self.stage, self.error = stage, error

    def complete(self, request: LLMRequest, extra_instruction: str | None = None) -> RawResponse:
        if request.stage == self.stage:
            raise self.error
        return super().complete(request, extra_instruction)


@pytest.fixture
def failing_provider(monkeypatch: pytest.MonkeyPatch, settings) -> Callable[[str, Exception], None]:
    settings.LLM_MAX_RETRIES = 0  # backoff itself is tested in test_client.py

    def _use(stage: str, error: Exception) -> None:
        monkeypatch.setattr(
            runner, "build_provider", lambda _s, info: FailingProvider(info, stage, error)
        )

    return _use


def _steps(run: AnalysisRun) -> list[AgentStep]:
    return list(AgentStep.objects.filter(run=run).order_by("index"))


def _events(run: AnalysisRun) -> list[tuple[str, float]]:
    return [(e.event_type, e.timestamp_s) for e in Event.objects.filter(run=run)]


def test_full_run_saves_events_summary_and_trace(video: Video, analyze) -> None:
    run = analyze(video)

    run.refresh_from_db()
    video.refresh_from_db()
    assert run.status == "succeeded"
    assert video.status == "done"
    assert (run.is_partial, run.stop_reason) == (False, "completed")
    assert _events(run) == [("missing_ppe", 1.0), ("unsafe_proximity", 9.0)]
    assert "2 event(s) confirmed" in run.summary
    assert run.iterations == 1
    assert run.llm_calls == 6  # survey, 3 inspect windows, verify, report
    assert run.frames_analyzed > 0 and run.input_tokens > 0 and run.output_tokens > 0

    steps = _steps(run)
    assert len(steps) >= 5
    assert [s.node for s in steps] == [
        "survey", "plan", "inspect", "inspect", "inspect", "verify", "report",
    ]  # fmt: skip
    assert [s.index for s in steps] == list(range(len(steps)))
    assert all(s.status == "ok" for s in steps)
    assert steps[0].tool_calls[0]["tool"] == "get_frames"

    verify = next(s for s in steps if s.node == "verify")
    assert "dropped c3 missing_ppe: The worker wears a hard hat." in verify.decision

    event = Event.objects.get(run=run, event_type="missing_ppe")
    assert event.frame_ref.startswith(f"frames/{run.id}/win_")
    assert event.frame_ref.endswith(".jpg")


def test_video_without_fixture_gets_generic_demo_events(make_test_video, analyze) -> None:
    path = make_test_video(seconds=10, name="other.mp4")
    upload = SimpleUploadedFile("other.mp4", path.read_bytes(), content_type="video/mp4")
    video = Video.objects.get(
        pk=APIClient().post("/api/videos/", {"file": upload}, format="multipart").json()["id"]
    )

    run = analyze(video)

    events = list(Event.objects.filter(run=run))
    assert [e.event_type for e in events] == ["missing_ppe", "fallen_object_or_spill"]
    assert all("no fixture" in e.explanation for e in events)


def test_max_iterations_stops_with_a_partial_result(
    video: Video, analyze, write_fixture, limits
) -> None:
    uncertain = dict(TEST_FIXTURE["events"][0], uncertain=True)
    write_fixture(events=[uncertain], decoys=[])
    limits(max_iterations=2)

    run = analyze(video)

    run.refresh_from_db()
    assert run.status == "succeeded"
    assert (run.is_partial, run.stop_reason, run.iterations) == (True, "max_iterations", 2)
    assert _events(run) == []
    last_verify = [s for s in _steps(run) if s.node == "verify"][-1]
    assert "dropped c1 missing_ppe: unresolved" in last_verify.decision


def test_max_frames_stops_with_a_partial_result(video: Video, analyze, limits) -> None:
    # Survey uses 5 frames; only the high severity window (6 frames) fits in 12.
    limits(max_frames=12)

    run = analyze(video)

    run.refresh_from_db()
    assert (run.is_partial, run.stop_reason) == (True, "max_frames")
    assert _events(run) == [("unsafe_proximity", 9.0)]
    assert run.frames_analyzed <= 12
    plans = [s for s in _steps(run) if s.node == "plan"]
    assert "skip" in plans[0].decision
    assert "no window fits the frame budget" in plans[-1].decision


def test_max_tokens_stops_with_a_partial_result(video: Video, analyze, limits) -> None:
    # The survey call fits; every later call (except the report) is over the limit.
    limits(max_tokens=100_001, report_reserve_tokens=100_000)

    run = analyze(video)

    run.refresh_from_db()
    assert (run.status, run.is_partial, run.stop_reason) == ("succeeded", True, "max_tokens")
    assert _events(run) == []
    assert run.summary
    assert _steps(run)[-1].node == "report"


def test_max_llm_calls_stops_with_a_partial_result(video: Video, analyze, limits) -> None:
    limits(max_llm_calls=3)

    run = analyze(video)

    run.refresh_from_db()
    assert (run.is_partial, run.stop_reason) == (True, "max_llm_calls")
    assert run.llm_calls == 3  # survey, one inspect window, report
    inspects = [s for s in _steps(run) if s.node == "inspect"]
    assert inspects[-1].status == "error"
    assert "max_llm_calls" in inspects[-1].error_message


def test_invalid_json_once_gives_a_retried_step(video: Video, analyze, write_fixture) -> None:
    write_fixture(invalid_json_once=["verify"])

    run = analyze(video)

    run.refresh_from_db()
    assert run.status == "succeeded"
    verify = next(s for s in _steps(run) if s.node == "verify")
    assert verify.status == "retried"
    assert len(_events(run)) == 2


def test_survey_error_fails_the_run(video: Video, analyze, write_fixture) -> None:
    write_fixture(error_on=["survey"])

    run = analyze(video)

    run.refresh_from_db()
    video.refresh_from_db()
    assert (run.status, run.stop_reason, video.status) == ("failed", "error", "failed")
    assert run.error_message.startswith("The survey step failed")
    steps = _steps(run)
    assert [(s.node, s.status) for s in steps] == [("survey", "error")]


def test_inspect_error_drops_candidates_and_continues(video: Video, analyze, write_fixture) -> None:
    write_fixture(error_on=["inspect"])

    run = analyze(video)

    run.refresh_from_db()
    assert run.status == "succeeded"
    assert _events(run) == []
    steps = _steps(run)
    inspects = [s for s in steps if s.node == "inspect"]
    assert inspects and all(s.status == "error" for s in inspects)
    assert "analysis failed" in inspects[0].decision
    assert steps[-1].node == "report"


def test_reanalysis_does_not_duplicate_events(video: Video, analyze) -> None:
    analyze(video)
    second = analyze(video)

    video.refresh_from_db()
    assert video.current_run_id == second.id
    assert AnalysisRun.objects.filter(video=video).count() == 1
    assert Event.objects.filter(video=video).count() == 2


def test_quota_error_fails_the_run_with_a_clear_message(
    video: Video, analyze, failing_provider
) -> None:
    failing_provider("inspect", QuotaExhaustedError(QUOTA_MESSAGE))

    run = analyze(video)

    run.refresh_from_db()
    video.refresh_from_db()
    assert (run.status, run.stop_reason, video.status) == ("failed", "error", "failed")
    assert run.error_message == QUOTA_MESSAGE
    assert "daily quota" in video_detail_error(video)


def test_provider_down_after_retries_fails_the_survey(
    video: Video, analyze, failing_provider
) -> None:
    failing_provider("survey", RetryableLLMError("Gemini returned HTTP 503"))

    run = analyze(video)

    run.refresh_from_db()
    assert (run.status, run.stop_reason) == ("failed", "error")
    assert run.error_message == (
        "The survey step failed: the LLM provider did not answer after several retries."
    )
    [step] = _steps(run)
    assert (step.node, step.status, step.error_message) == (
        "survey",
        "error",
        "Gemini returned HTTP 503",
    )


def test_provider_down_during_inspect_drops_candidates_and_continues(
    video: Video, analyze, failing_provider
) -> None:
    failing_provider("inspect", RetryableLLMError("Gemini request timed out"))

    run = analyze(video)

    run.refresh_from_db()
    assert run.status == "succeeded"
    inspects = [s for s in _steps(run) if s.node == "inspect"]
    assert inspects and all(s.status == "error" for s in inspects)
    assert "analysis failed" in inspects[0].decision


def video_detail_error(video: Video) -> str:
    return APIClient().get(f"/api/videos/{video.id}/").json()["error_message"]
