from pathlib import Path

import pytest
from django.test import Client

CONTENT = bytes(range(256)) * 4  # 1024 bytes


@pytest.fixture
def media_file(media_root: Path) -> str:
    (media_root / "videos").mkdir()
    (media_root / "videos" / "clip.mp4").write_bytes(CONTENT)
    return "/media/videos/clip.mp4"


def _body(response) -> bytes:
    return b"".join(response.streaming_content)


def test_full_file_advertises_ranges(media_file: str) -> None:
    response = Client().get(media_file)

    assert response.status_code == 200
    assert response["Accept-Ranges"] == "bytes"
    assert response["Content-Type"] == "video/mp4"
    assert _body(response) == CONTENT


@pytest.mark.parametrize(
    ("header", "start", "end"),
    [("bytes=0-99", 0, 99), ("bytes=100-", 100, 1023), ("bytes=-50", 974, 1023)],
)
def test_range_returns_partial_content(media_file: str, header: str, start: int, end: int) -> None:
    response = Client().get(media_file, headers={"Range": header})

    assert response.status_code == 206
    assert response["Content-Range"] == f"bytes {start}-{end}/1024"
    assert response["Content-Length"] == str(end - start + 1)
    assert _body(response) == CONTENT[start : end + 1]


def test_range_end_is_clamped_to_file_size(media_file: str) -> None:
    response = Client().get(media_file, headers={"Range": "bytes=1000-5000"})

    assert response.status_code == 206
    assert response["Content-Range"] == "bytes 1000-1023/1024"


def test_unsatisfiable_range_returns_416(media_file: str) -> None:
    response = Client().get(media_file, headers={"Range": "bytes=2000-3000"})

    assert response.status_code == 416
    assert response["Content-Range"] == "bytes */1024"


def test_path_traversal_returns_404(media_file: str) -> None:
    assert Client().get("/media/../../etc/passwd").status_code == 404


def test_directory_and_missing_file_return_404(media_file: str) -> None:
    assert Client().get("/media/videos/").status_code == 404
    assert Client().get("/media/videos/missing.mp4").status_code == 404
