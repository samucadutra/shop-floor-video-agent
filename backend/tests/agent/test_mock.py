from pathlib import Path

import pytest

from agent.providers.base import Frame, LLMRequest
from agent.providers.factory import VideoInfo
from agent.providers.mock import FIXTURES_DIR, MockFixture, MockProvider, load_fixture
from agent.schemas import SurveyResult

SAMPLE_1_SHA = "e20b2a53363817e70a236b7139b48a6c85bd14ba822f8f741ab64500e2e55a75"


@pytest.mark.parametrize("path", sorted(FIXTURES_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_every_fixture_is_valid(path: Path) -> None:
    import yaml

    fixture = MockFixture.model_validate(yaml.safe_load(path.read_text()))
    for event in fixture.events:
        assert event.start_s <= event.time_s <= event.end_s


def test_lookup_by_sha256_then_filename_then_generic() -> None:
    by_sha = load_fixture(VideoInfo(SAMPLE_1_SHA, "renamed.mp4", 25.4))
    by_name = load_fixture(VideoInfo("0" * 64, "16106604.mp4", 25.4))
    generic = load_fixture(VideoInfo("0" * 64, "other.mp4", 10.0))

    assert by_sha.filename == by_name.filename == "16106604.mp4"
    assert [e.time_s for e in generic.events] == [2.0, 8.0]
    assert generic.decoys[0].time_s == 5.0
    assert all("no fixture" in e.explanation for e in generic.events)


def test_survey_returns_items_inside_the_frames_only() -> None:
    provider = MockProvider(VideoInfo(SAMPLE_1_SHA, "16106604.mp4", 25.4))
    frames = tuple(Frame(t, Path(f"{t}.jpg"), "survey") for t in (0.0, 2.0, 4.0))
    request = LLMRequest(stage="survey", prompt="p" * 400, schema=SurveyResult, frames=frames)

    response = provider.complete(request)

    survey = SurveyResult.model_validate_json(response.text)
    assert [(c.event_type, c.time_s) for c in survey.candidates] == [("missing_ppe", 2.0)]
    assert response.input_tokens == 300 + 260 * 3 + 100
    assert response.output_tokens == len(response.text) // 4
