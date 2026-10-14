import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from media_tools.ffmpeg import FFmpegError
from tests.videos.factories import create_event, create_run, create_video
from videos.models import AnalysisRun, Event, RunStatus, StopReason, Video, VideoStatus
from videos.services import STALE_RUN_MESSAGE
from videos.tasks import ERROR_MESSAGE, FFMPEG_MESSAGE

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("celery_eager")]


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def video(client: APIClient, make_test_video) -> Video:
    """A 3 s clip uploaded through the API, so the task can extract real frames."""
    path = make_test_video(seconds=3)
    upload = SimpleUploadedFile("clip.mp4", path.read_bytes(), content_type="video/mp4")
    response = client.post("/api/videos/", {"file": upload}, format="multipart")
    assert response.status_code == 201
    return Video.objects.get(pk=response.json()["id"])


def _analyze(client: APIClient, video: Video):
    return client.post(f"/api/videos/{video.id}/analyze/")


def test_status_flow_uploaded_processing_done(
    client: APIClient, video: Video, settings, media_root: Path, django_capture_on_commit_callbacks
) -> None:
    settings.LLM_PROVIDER = "mock"
    settings.LLM_MODEL = ""
    assert video.status == VideoStatus.UPLOADED

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = _analyze(client, video)

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert response.json() == {"run_id": run_id, "status": "queued"}
    video.refresh_from_db()
    assert video.status == VideoStatus.PROCESSING
    assert client.get(f"/api/videos/{video.id}/").json()["active_run_id"] == run_id
    assert len(callbacks) == 1

    callbacks[0]()  # the queued Celery task runs eagerly

    video.refresh_from_db()
    run = AnalysisRun.objects.get(pk=run_id)
    assert video.status == VideoStatus.DONE
    assert video.current_run_id == run.id
    assert run.status == RunStatus.SUCCEEDED
    assert run.stop_reason == StopReason.COMPLETED
    assert (run.provider, run.model) == ("mock", "")
    assert run.frames_analyzed > 0
    assert run.summary
    assert run.started_at and run.finished_at and run.duration_ms is not None
    assert run.celery_task_id
    assert len(list((media_root / "frames" / run_id).glob("*.jpg"))) >= run.frames_analyzed


def test_second_start_returns_409(
    client: APIClient, video: Video, django_capture_on_commit_callbacks
) -> None:
    with django_capture_on_commit_callbacks(execute=False):
        first = _analyze(client, video)
        second = _analyze(client, video)

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json() == {"detail": "An analysis is already running for this video."}
    assert video.runs.count() == 1


def test_analyze_404(client: APIClient) -> None:
    assert client.post(f"/api/videos/{uuid.uuid4()}/analyze/").status_code == 404


@pytest.mark.parametrize(
    ("error", "reason", "message"),
    [
        (FFmpegError("boom"), StopReason.ERROR, FFMPEG_MESSAGE),
        (RuntimeError("boom"), StopReason.ERROR, ERROR_MESSAGE),
        (SoftTimeLimitExceeded(), StopReason.TIMEOUT, "The analysis took longer than the"),
    ],
)
def test_failure_sets_failed_and_keeps_current_run(
    client: APIClient,
    video: Video,
    django_capture_on_commit_callbacks,
    error: Exception,
    reason: str,
    message: str,
) -> None:
    previous = create_run(video)
    create_event(previous)
    video.current_run = previous
    video.status = VideoStatus.DONE
    video.save()

    with (
        patch("videos.tasks.run_agent", side_effect=error),
        django_capture_on_commit_callbacks(execute=True),
    ):
        run_id = _analyze(client, video).json()["run_id"]

    video.refresh_from_db()
    run = AnalysisRun.objects.get(pk=run_id)
    assert video.status == VideoStatus.FAILED
    assert video.current_run_id == previous.id
    assert run.status == RunStatus.FAILED
    assert run.stop_reason == reason
    assert run.error_message.startswith(message)
    body = client.get(f"/api/videos/{video.id}/").json()
    assert body["error_message"] == run.error_message
    assert body["current_run"]["id"] == str(previous.id)
    assert len(client.get(f"/api/videos/{video.id}/events/").json()) == 1


def test_reanalysis_deletes_older_run(
    client: APIClient, video: Video, django_capture_on_commit_callbacks
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        first_id = _analyze(client, video).json()["run_id"]
    create_event(AnalysisRun.objects.get(pk=first_id))

    with django_capture_on_commit_callbacks(execute=True):
        second_id = _analyze(client, video).json()["run_id"]

    video.refresh_from_db()
    assert video.status == VideoStatus.DONE
    assert [str(r.id) for r in video.runs.all()] == [second_id]
    assert str(video.current_run_id) == second_id
    # The older run's events (CASCADE) are gone; only the new run's events are left.
    assert {str(e.run_id) for e in Event.objects.filter(video=video)} <= {second_id}


def _stale_run(status: str = RunStatus.RUNNING) -> AnalysisRun:
    video = create_video(status=VideoStatus.PROCESSING)
    run = create_run(video, status=status)
    old = timezone.now() - timedelta(seconds=600 + 61)
    AnalysisRun.objects.filter(pk=run.pk).update(created_at=old)
    return run


def test_stale_run_is_marked_failed_on_read(client: APIClient, settings) -> None:
    settings.AGENT_RUN_TIMEOUT_SECONDS = 600
    run = _stale_run()

    body = client.get(f"/api/videos/{run.video_id}/").json()

    run.refresh_from_db()
    assert run.status == RunStatus.FAILED
    assert run.stop_reason == StopReason.TIMEOUT
    assert body["status"] == VideoStatus.FAILED
    assert body["active_run_id"] is None
    assert body["error_message"] == STALE_RUN_MESSAGE


def test_recent_active_run_is_not_stale(client: APIClient) -> None:
    run = create_run(create_video(status=VideoStatus.PROCESSING), status=RunStatus.RUNNING)

    body = client.get(f"/api/videos/{run.video_id}/").json()

    assert body["status"] == VideoStatus.PROCESSING
    assert body["active_run_id"] == str(run.id)


def test_stale_run_does_not_block_a_new_analysis(
    client: APIClient, settings, django_capture_on_commit_callbacks
) -> None:
    settings.AGENT_RUN_TIMEOUT_SECONDS = 600
    stale = _stale_run(RunStatus.QUEUED)

    with django_capture_on_commit_callbacks(execute=False):
        response = client.post(f"/api/videos/{stale.video_id}/analyze/")

    stale.refresh_from_db()
    assert response.status_code == 202
    assert stale.status == RunStatus.FAILED
