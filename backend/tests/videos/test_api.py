import uuid

import pytest
from rest_framework.test import APIClient

from tests.videos.factories import create_event, create_run, create_step, create_video
from videos.models import RunStatus


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_list_is_paginated_and_counts_current_run_events(client: APIClient) -> None:
    analyzed = create_video("analyzed.mp4", status="done")
    run = create_run(analyzed)
    create_event(run, 1.0)
    create_event(run, 5.0)
    analyzed.current_run = run
    analyzed.save()
    create_video("new.mp4")

    response = client.get("/api/videos/")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 2
    counts = {item["original_name"]: item["event_count"] for item in body["results"]}
    assert counts == {"analyzed.mp4": 2, "new.mp4": 0}
    assert set(body["results"][0]) == {
        "id",
        "original_name",
        "status",
        "duration_s",
        "event_count",
        "created_at",
    }


@pytest.mark.django_db
def test_list_ignores_events_of_old_runs(client: APIClient) -> None:
    video = create_video()
    old = create_run(video)
    create_event(old)
    video.current_run = create_run(video)
    video.save()

    item = client.get("/api/videos/").json()["results"][0]

    assert item["event_count"] == 0


@pytest.mark.django_db
def test_detail_includes_run_summary_and_active_run(client: APIClient) -> None:
    video = create_video(status="processing")
    done = create_run(video, summary="All good.")
    video.current_run = done
    video.save()
    active = create_run(video, status=RunStatus.RUNNING)

    body = client.get(f"/api/videos/{video.id}/").json()

    assert body["current_run"]["id"] == str(done.id)
    assert body["current_run"]["summary"] == "All good."
    assert body["active_run_id"] == str(active.id)
    assert body["error_message"] is None


@pytest.mark.django_db
def test_detail_shows_error_of_latest_failed_run(client: APIClient) -> None:
    video = create_video(status="failed")
    create_run(video, status=RunStatus.FAILED, error_message="Quota reached.")

    body = client.get(f"/api/videos/{video.id}/").json()

    assert body["error_message"] == "Quota reached."
    assert body["active_run_id"] is None


@pytest.mark.django_db
def test_detail_404(client: APIClient) -> None:
    assert client.get(f"/api/videos/{uuid.uuid4()}/").status_code == 404


@pytest.mark.django_db
def test_events_empty_without_a_run(client: APIClient) -> None:
    video = create_video()

    response = client.get(f"/api/videos/{video.id}/events/")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_events_of_current_run_sorted_by_time(client: APIClient) -> None:
    video = create_video()
    run = create_run(video)
    create_event(run, 9.0, event_type="unsafe_proximity", severity="high")
    create_event(run, 2.0)
    video.current_run = run
    video.save()

    events = client.get(f"/api/videos/{video.id}/events/").json()

    assert [e["timestamp_s"] for e in events] == [2.0, 9.0]
    assert events[1]["event_type"] == "unsafe_proximity"
    assert set(events[0]) == {
        "id",
        "event_type",
        "timestamp_s",
        "start_s",
        "end_s",
        "severity",
        "confidence",
        "explanation",
        "frame_ref",
    }


@pytest.mark.django_db
def test_trace_returns_steps_in_order(client: APIClient) -> None:
    run = create_run(create_video())
    create_step(run, 1, "plan")
    create_step(run, 0, "survey")

    response = client.get(f"/api/runs/{run.id}/trace/")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == str(run.id)
    assert [s["node"] for s in body["steps"]] == ["survey", "plan"]
    assert "run" not in body["steps"][0]


@pytest.mark.django_db
def test_trace_404(client: APIClient) -> None:
    assert client.get(f"/api/runs/{uuid.uuid4()}/trace/").status_code == 404
