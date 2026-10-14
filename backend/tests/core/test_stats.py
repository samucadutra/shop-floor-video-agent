from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from tests.videos.factories import create_event, create_run, create_video
from videos.models import RunStatus

EMPTY = {
    "events_by_type": [],
    "events_by_severity": [],
    "events_per_video": [],
    "avg_processing_ms": None,
    "total_tokens": 0,
    "total_estimated_cost_usd": "0.0000",
    "runs_succeeded": 0,
    "runs_failed": 0,
}


def get_stats() -> dict:
    response = APIClient().get("/api/stats/")
    assert response.status_code == 200
    return response.json()


@pytest.mark.django_db
def test_stats_empty_database() -> None:
    assert get_stats() == EMPTY


@pytest.mark.django_db
def test_stats_two_videos_with_events() -> None:
    yard = create_video("yard.mp4")
    run_a = create_run(
        yard,
        duration_ms=1000,
        input_tokens=100,
        output_tokens=10,
        estimated_cost_usd=Decimal("0.0100"),
    )
    create_event(run_a, 1.0, event_type="missing_ppe", severity="medium")
    create_event(run_a, 5.0, event_type="unsafe_proximity", severity="high")
    yard.current_run = run_a
    yard.save()

    aisle = create_video("aisle.mp4")
    run_b = create_run(
        aisle,
        duration_ms=3000,
        input_tokens=200,
        output_tokens=20,
        estimated_cost_usd=Decimal("0.0200"),
    )
    create_event(run_b, 2.0, event_type="missing_ppe", severity="low")
    aisle.current_run = run_b
    aisle.save()

    # An older run that is not current: its events are not counted.
    old = create_run(aisle, status=RunStatus.FAILED)
    create_event(old, 3.0, event_type="fallen_object_or_spill", severity="high")

    stats = get_stats()

    assert stats["events_by_type"] == [
        {"event_type": "missing_ppe", "count": 2},
        {"event_type": "unsafe_proximity", "count": 1},
    ]
    assert sorted(stats["events_by_severity"], key=lambda r: r["severity"]) == [
        {"severity": "high", "count": 1},
        {"severity": "low", "count": 1},
        {"severity": "medium", "count": 1},
    ]
    assert stats["events_per_video"] == [
        {"video_id": str(yard.id), "name": "yard.mp4", "count": 2},
        {"video_id": str(aisle.id), "name": "aisle.mp4", "count": 1},
    ]
    assert stats["avg_processing_ms"] == 2000
    assert stats["total_tokens"] == 330
    assert stats["total_estimated_cost_usd"] == "0.0300"


@pytest.mark.django_db
def test_stats_counts_failed_runs() -> None:
    video = create_video()
    done = create_run(video, duration_ms=500)
    video.current_run = done
    video.save()
    create_run(video, status=RunStatus.FAILED, duration_ms=9000, input_tokens=50)
    create_run(create_video("other.mp4"), status=RunStatus.FAILED)

    stats = get_stats()

    assert stats["runs_succeeded"] == 1
    assert stats["runs_failed"] == 2
    assert stats["avg_processing_ms"] == 500  # failed runs are not in the average
    assert stats["total_tokens"] == 50
    assert stats["events_per_video"] == [
        {"video_id": str(video.id), "name": "clip.mp4", "count": 0}
    ]
