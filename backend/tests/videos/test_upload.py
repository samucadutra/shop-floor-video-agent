from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from videos.models import Video, VideoStatus


def _upload(path: Path, name: str | None = None, content_type: str = "video/mp4"):
    upload = SimpleUploadedFile(name or path.name, path.read_bytes(), content_type=content_type)
    return APIClient().post("/api/videos/", {"file": upload}, format="multipart")


def _error(response) -> str:
    return " ".join(response.json()["file"])


@pytest.mark.django_db
def test_valid_upload_saves_video_and_metadata(make_test_video, media_root: Path) -> None:
    response = _upload(make_test_video(seconds=3), name="forklift aisle.mp4")

    assert response.status_code == 201
    body = response.json()
    assert body["original_name"] == "forklift aisle.mp4"
    assert body["status"] == VideoStatus.UPLOADED
    assert body["duration_s"] == pytest.approx(3, abs=0.2)
    assert (body["width"], body["height"]) == (320, 240)
    assert body["fps"] == 25
    assert body["current_run"] is None
    assert body["active_run_id"] is None
    assert body["file_url"] == f"http://testserver/media/videos/{body['id']}.mp4"

    video = Video.objects.get(id=body["id"])
    assert len(video.sha256) == 64
    # Stored under the generated id, never under the user's file name.
    assert (media_root / "videos" / f"{body['id']}.mp4").is_file()


@pytest.mark.django_db
def test_octet_stream_content_type_is_accepted(make_test_video) -> None:
    response = _upload(make_test_video(), content_type="application/octet-stream")

    assert response.status_code == 201


@pytest.mark.django_db
def test_wrong_extension_is_rejected(make_test_video) -> None:
    response = _upload(make_test_video(), name="clip.avi")

    assert response.status_code == 400
    assert "Unsupported file type" in _error(response)
    assert Video.objects.count() == 0


@pytest.mark.django_db
def test_wrong_content_type_is_rejected(make_test_video) -> None:
    response = _upload(make_test_video(), content_type="text/plain")

    assert response.status_code == 400
    assert "Unsupported file type" in _error(response)


@pytest.mark.django_db
def test_fake_video_is_rejected(tmp_path: Path) -> None:
    fake = tmp_path / "fake.mp4"
    fake.write_text("not a video")

    response = _upload(fake)

    assert response.status_code == 400
    assert "could not be read as a video" in _error(response)
    assert Video.objects.count() == 0


@pytest.mark.django_db
def test_too_large_is_rejected(make_test_video, settings) -> None:
    settings.MAX_UPLOAD_BYTES = 1000

    response = _upload(make_test_video())

    assert response.status_code == 400
    assert "too large" in _error(response)


@pytest.mark.django_db
def test_too_long_is_rejected(make_test_video, settings) -> None:
    settings.MAX_VIDEO_SECONDS = 2

    response = _upload(make_test_video(seconds=4))

    assert response.status_code == 400
    assert "too long" in _error(response)
    assert Video.objects.count() == 0


@pytest.mark.django_db
def test_missing_file_is_rejected() -> None:
    response = APIClient().post("/api/videos/", {}, format="multipart")

    assert response.status_code == 400
