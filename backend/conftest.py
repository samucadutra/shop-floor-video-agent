import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path: Path) -> Path:
    """Every test writes uploads and frames to its own temporary MEDIA_ROOT."""
    root = tmp_path / "media"
    root.mkdir()
    settings.MEDIA_ROOT = root
    return root


@pytest.fixture(autouse=True)
def mock_llm(settings) -> None:
    """Tests never call a real LLM: the mock provider, with no delay."""
    settings.LLM_PROVIDER = "mock"
    settings.LLM_MODEL = ""
    settings.MOCK_LATENCY_MS = 0
    settings.LLM_MAX_REQUESTS_PER_MINUTE = 0  # no throttle waits in tests


@pytest.fixture
def make_test_video(tmp_path: Path) -> Callable[..., Path]:
    """Return a factory that creates a small test clip with ffmpeg's testsrc."""

    def _make(seconds: float = 3, name: str = "clip.mp4", size: str = "320x240") -> Path:
        path = tmp_path / name
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=duration={seconds}:size={size}:rate=25",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            timeout=60,
        )
        return path

    return _make


@pytest.fixture
def celery_eager() -> Iterator[None]:
    """Run Celery tasks in-process (CELERY_TASK_ALWAYS_EAGER) for the duration of a test."""
    from config.celery import app

    previous = app.conf.task_always_eager
    app.conf.task_always_eager = True
    yield
    app.conf.task_always_eager = previous
